"""Resume tailoring agent: JD keyword gap analysis + weighted ATS scoring.

Borrowed from resume-matcher (weighted ATS formula, no-fabrication tailoring),
Beat-The-ATS (keyword + semantic hybrid) and ats-screener (parseability checks).
Missing keywords are split into two honest buckets:
  * add   - already evidenced somewhere in the master resume (different wording),
            safe to surface with the JD's exact term.
  * learn - not evidenced anywhere; a real gap to study, never auto-added.
"""
import logging
import re
from urllib.parse import quote_plus

from .. import llm
from .resume_parser import SKILL_ALIASES, detect_skills

logger = logging.getLogger(__name__)

TAILOR_MIN_SCORE = 75.0

LEARN_RESOURCES = {
    "python": "https://docs.python.org/3/tutorial/",
    "pytorch": "https://pytorch.org/tutorials/",
    "tensorflow": "https://www.tensorflow.org/tutorials",
    "kubernetes": "https://kubernetes.io/docs/tutorials/",
    "docker": "https://docs.docker.com/get-started/",
    "aws": "https://aws.amazon.com/training/",
    "gcp": "https://cloud.google.com/learn/training",
    "azure": "https://learn.microsoft.com/training/azure/",
    "sql": "https://sqlbolt.com/",
    "langchain": "https://python.langchain.com/docs/tutorials/",
    "langgraph": "https://langchain-ai.github.io/langgraph/tutorials/",
    "huggingface": "https://huggingface.co/learn",
    "vector database": "https://docs.trychroma.com/",
    "mlops": "https://mlflow.org/docs/latest/tutorials-and-examples/index.html",
    "fastapi": "https://fastapi.tiangolo.com/tutorial/",
    "react": "https://react.dev/learn",
}


def _learn_resource(keyword: str) -> str:
    curated = LEARN_RESOURCES.get(keyword)
    if curated:
        return curated
    return f"https://www.google.com/search?q={quote_plus(keyword + ' official documentation tutorial')}"

_SECTION_PATTERNS = {
    "summary": r"\b(summary|objective|profile|about me)\b",
    "experience": r"\b(experience|employment|work history)\b",
    "education": r"\b(education|academic|qualification)\b",
    "skills": r"\b(skills|technologies|tech stack|competencies)\b",
    "projects": r"\b(projects|portfolio)\b",
}
_DATE_RANGE_RE = re.compile(
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}\s*[-–—to]+\s*"
    r"(?:present|current|till date|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}|\d{4})",
    re.I,
)
_STOPWORDS = {"the", "and", "for", "with", "engineer", "developer", "senior", "junior", "lead", "ii", "iii", "i"}


def _canonical(skill: str) -> str:
    s = skill.lower().strip()
    for canonical, aliases in SKILL_ALIASES.items():
        if s == canonical or s in aliases:
            return canonical
    return s


def _aliases(keyword: str) -> list[str]:
    return SKILL_ALIASES.get(keyword, [keyword])


def _present(keyword: str, text: str) -> bool:
    low = text.lower()
    return any(a.lower() in low for a in _aliases(keyword))


def extract_jd_keywords(job: dict) -> list[str]:
    kws = {_canonical(s) for s in (job.get("skills") or []) if s}
    kws.discard("")
    kws.update(detect_skills(f"{job.get('title', '')} {job.get('description', '')}"))
    return sorted(kws)


def _evidence_line(keyword: str, text: str) -> str:
    for line in text.splitlines():
        if any(a.lower() in line.lower() for a in _aliases(keyword)):
            return line.strip()[:160]
    return ""


def classify_gaps(profile: dict, job: dict) -> dict:
    raw = profile.get("raw_text") or ""
    resume_skills = {_canonical(s) for s in (profile.get("skills") or []) if s}
    resume_skills.update(detect_skills(raw))
    jd = extract_jd_keywords(job)
    present = sorted(k for k in jd if k in resume_skills)
    missing = [k for k in jd if k not in resume_skills]
    add, learn = [], []
    for k in missing:
        if _present(k, raw):
            add.append({"keyword": k, "evidence": _evidence_line(k, raw)})
        else:
            learn.append({
                "keyword": k,
                "why": f"'{k}' appears in the job description but nowhere in your resume.",
                "resource": _learn_resource(k),
            })
    return {"jd_keywords": jd, "present": present, "add": add, "learn": learn}


def ats_score(resume_text: str, job: dict) -> dict:
    text = resume_text or ""
    jd = extract_jd_keywords(job)
    job_skills = sorted({_canonical(s) for s in (job.get("skills") or []) if s})

    keyword = (sum(_present(k, text) for k in jd) / len(jd)) if jd else 0.5
    skills = (sum(_present(k, text) for k in job_skills) / len(job_skills)) if job_skills else keyword

    title_tokens = [t for t in re.findall(r"[a-z0-9+#]+", (job.get("title") or "").lower())
                    if len(t) > 2 and t not in _STOPWORDS]
    low = text.lower()
    title = (sum(t in low for t in title_tokens) / len(title_tokens)) if title_tokens else 0.5

    sections_found = [name for name, pat in _SECTION_PATTERNS.items() if re.search(pat, low)]
    has_email = bool(re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))
    has_phone = bool(re.search(r"(?:\+91[\s-]?)?[6-9]\d{9}\b", text))
    section = (len(sections_found) + has_email + has_phone) / (len(_SECTION_PATTERNS) + 2)

    if _DATE_RANGE_RE.search(text):
        dates = 1.0
    elif re.search(r"\b(19|20)\d{2}\b", text):
        dates = 0.5
    else:
        dates = 0.0

    score = 100 * (0.40 * keyword + 0.20 * skills + 0.15 * title + 0.15 * section + 0.10 * dates)
    warnings = []
    if not has_email:
        warnings.append("No parseable contact email — ATS may drop your application.")
    if not has_phone:
        warnings.append("No parseable phone number found.")
    if len(text.strip()) < 200:
        warnings.append("Resume text is very short; ATS expects fuller content.")
    missing = [k for k in jd if not _present(k, text)]
    return {
        "score": round(score, 1),
        "components": {
            "keyword_match": round(keyword, 3), "skills_coverage": round(skills, 3),
            "title_match": round(title, 3), "section_completeness": round(section, 3),
            "date_consistency": round(dates, 3),
        },
        "sections_found": sections_found,
        "missing_keywords": missing,
        "parse_warnings": warnings,
    }


TAILOR_SYSTEM = """You are an ATS resume tailoring engine for an Indian AI Engineer.
Rewrite the master resume so it mirrors the job description's exact keywords.
STRICT RULES:
- Use ONLY facts, skills, employers, numbers and projects present in the master resume.
- You may rephrase and reorder, and surface the provided 'safe_to_add' keywords (they are
  already evidenced in the resume), but NEVER invent experience, tools, metrics or employers.
- Keep it concise, plain text with clear section headings (Summary, Skills, Experience,
  Projects, Education). Do not use markdown tables or graphics (ATS cannot parse them).
Return ONLY JSON: {"content": "<full tailored resume text>", "added_keywords": [...], "notes": [...]}"""


def build_draft(profile: dict, job: dict, gaps: dict) -> dict:
    master = profile.get("raw_text") or ""
    safe = [g["keyword"] for g in gaps.get("add", [])]
    user = (f"MASTER RESUME:\n{master[:9000]}\n\n"
            f"JOB: {job.get('title')} at {job.get('company')}\n"
            f"JD keywords: {', '.join(gaps.get('jd_keywords', []))}\n"
            f"safe_to_add (already in resume): {', '.join(safe) or 'none'}\n"
            f"true gaps (do NOT add): {', '.join(g['keyword'] for g in gaps.get('learn', [])) or 'none'}")
    parsed = llm.chat_json(TAILOR_SYSTEM, user, prefer="cloud")
    if parsed and isinstance(parsed.get("content"), str) and parsed["content"].strip():
        return {"content": parsed["content"], "added_keywords": parsed.get("added_keywords", safe),
                "notes": parsed.get("notes", []), "method": "llm"}
    lines = [master.rstrip()]
    if safe:
        lines.append(f"\nTARGETED SKILLS ({job.get('title', 'role')}): {', '.join(safe)}")
    return {"content": "\n".join(lines), "added_keywords": safe,
            "notes": ["Heuristic draft: appended a targeted-skills line using only keywords already in your resume."],
            "method": "heuristic"}