"""Enrichment agent: RAG-grounded match insights and application tips per job.

Uses retrieved resume chunks + job description. Strict no-fabrication rule
(only facts present in the resume may appear in suggestions)."""
import logging

from .. import llm, rag

logger = logging.getLogger(__name__)

ENRICH_SYSTEM = """You are a job-application coach for an Indian AI Engineer candidate.
Given the candidate's resume context and a job description, return ONLY JSON:
{
  "why_match": [3 short bullets citing concrete overlap],
  "gaps": [up to 3 honest gaps or stretch areas],
  "talking_points": [2-3 points to emphasize in application/interview],
  "resume_tips": [1-2 keyword/phrasing tweaks for ATS]
}
STRICT RULE: never invent experience, numbers, employers or skills the candidate doesn't have.
Be concise. Ground every claim in the provided resume context."""


def _fallback_insights(job: dict) -> dict:
    bd = job.get("score_breakdown") or {}
    matched = bd.get("matched_skills") or []
    missing = bd.get("missing_skills") or []
    return {
        "why_match": [f"Your skills overlap: {', '.join(matched[:6])}"] if matched else ["Role aligns with your target domain"],
        "gaps": [f"Consider highlighting or learning: {', '.join(missing[:4])}"] if missing else [],
        "talking_points": [f"Lead with your strongest {', '.join(matched[:3])} project experience"] if matched else [],
        "resume_tips": ["Mirror the job description's exact skill keywords in your resume summary"],
    }


def enrich_job(job: dict, profile: dict) -> dict:
    context = rag.retrieve_profile_context(f"{job.get('title')} {', '.join((job.get('skills') or [])[:8])}", k=3)
    if not context:
        context = [rag.profile_text(profile)]
    context_text = "\n---\n".join(context)[:4000]
    user = (f"RESUME CONTEXT:\n{context_text}\n\n"
            f"JOB: {job.get('title')} at {job.get('company')} ({job.get('location')})\n"
            f"Experience required: {job.get('experience_text') or 'unspecified'}\n"
            f"Description:\n{(job.get('description') or '')[:3500]}")
    parsed = llm.chat_json(ENRICH_SYSTEM, user, prefer="cloud")
    if parsed and isinstance(parsed.get("why_match"), list):
        return {k: parsed.get(k, []) for k in ("why_match", "gaps", "talking_points", "resume_tips")}
    return _fallback_insights(job)


def enrich_top_jobs(jobs: list[dict], profile: dict, top_n: int = 10) -> list[dict]:
    for job in jobs[:top_n]:
        try:
            job["insights"] = enrich_job(job, profile)
            job["enriched"] = True
        except Exception as e:
            logger.warning("Enrichment failed for %s: %s", job.get("title"), e)
            job["insights"] = _fallback_insights(job)
            job["enriched"] = True
    return jobs