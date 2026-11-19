"""Matching agent: scores jobs against the profile (semantic + skills + experience fit)."""
import logging
import re

import numpy as np

from .. import rag
from .resume_parser import SKILL_ALIASES, detect_skills

logger = logging.getLogger(__name__)


def _canonical(skill: str) -> str:
    s = skill.lower().strip()
    for canonical, aliases in SKILL_ALIASES.items():
        if s == canonical or s in aliases:
            return canonical
    return s


def job_skills(job: dict) -> set[str]:
    skills = {_canonical(s) for s in (job.get("skills") or []) if s}
    skills.discard("")
    if len(skills) < 3:
        text = f"{job.get('title', '')} {job.get('description', '')[:4000]}"
        skills.update(detect_skills(text))
    return skills


def skill_score(profile_skills: list[str], job: dict) -> tuple[float, list[str], list[str]]:
    pset = {_canonical(s) for s in profile_skills if s}
    jset = job_skills(job)
    if not jset:
        return 0.5, [], []
    matched = sorted(pset & jset)
    missing = sorted(jset - pset)
    coverage = len(matched) / len(jset)
    return min(1.0, coverage), matched, missing


_SENIOR_RE = re.compile(r"\b(senior|sr\.?|lead|staff|principal|head|manager|architect)\b", re.I)


def experience_fit(user_years: float, stretch: float, job: dict) -> tuple[float, str]:
    jmin, jmax = job.get("exp_min"), job.get("exp_max")
    if jmin is None:
        if _SENIOR_RE.search(job.get("title") or "") and user_years < 4:
            return 0.35, "senior_unknown"
        return 0.6, "unknown"
    if jmin <= user_years:
        if jmax is not None and jmax < user_years - 1.5:
            return 0.85, "fit"
        return 1.0, "fit"
    if jmin <= user_years + stretch:
        return 0.65, "stretch"
    return 0.1, "out_of_range"


def rank_jobs(jobs: list[dict], profile: dict, include_out_of_range: bool = False) -> list[dict]:
    if not jobs:
        return []
    user_years = float(profile.get("experience_years") or 0)
    stretch = float(profile.get("exp_stretch") if profile.get("exp_stretch") is not None else 1.8)
    profile_skills = profile.get("skills") or []

    p_vec = None
    j_vecs = None
    vecs = rag.embed_texts([rag.profile_text(profile)] + [rag.job_text(j) for j in jobs])
    if vecs is not None and len(vecs) == len(jobs) + 1:
        p_vec, j_vecs = vecs[0], vecs[1:]

    ranked = []
    for i, job in enumerate(jobs):
        if p_vec is not None:
            cos = rag.cosine(p_vec, j_vecs[i])
            sem = max(0.0, min(1.0, (cos - 0.30) / 0.45))
        else:
            sem = 0.5
        skills_s, matched, missing = skill_score(profile_skills, job)
        exp_s, exp_label = experience_fit(user_years, stretch, job)
        if exp_label == "out_of_range" and not include_out_of_range:
            continue
        score = round(100 * (0.40 * sem + 0.35 * skills_s + 0.25 * exp_s), 1)
        job["match_score"] = score
        job["score_breakdown"] = {
            "semantic": round(sem, 3),
            "skills": round(skills_s, 3),
            "experience": round(exp_s, 3),
            "exp_fit": exp_label,
            "matched_skills": matched[:12],
            "missing_skills": missing[:8],
        }
        ranked.append(job)
    ranked.sort(key=lambda j: j["match_score"], reverse=True)
    return ranked