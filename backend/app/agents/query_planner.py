"""Query planner agent: turns the parsed profile into job-search queries."""
from .. import llm

PLANNER_SYSTEM = """You generate job search queries for an Indian job portal scraper.
Given a candidate profile, return ONLY JSON: {"queries": [3 to 4 short job-title queries]}.
Queries must match the candidate's experience level (junior/mid, never senior/lead/staff unless they have 6+ years).
Focus on their domain. Example for an AI Engineer with Python/LLM skills:
{"queries": ["AI Engineer", "Machine Learning Engineer", "GenAI Engineer", "Python Developer"]}"""


def plan_queries(profile: dict, overrides: list[str] | None = None) -> list[str]:
    if overrides:
        return overrides[:4]
    targets = profile.get("target_roles") or []
    if targets:
        return targets[:4]
    parsed = llm.chat_json(PLANNER_SYSTEM,
                           f"Profile: role={profile.get('current_role')}, "
                           f"experience={profile.get('experience_years')} years, "
                           f"skills={', '.join((profile.get('skills') or [])[:20])}",
                           prefer="local")
    if parsed and isinstance(parsed.get("queries"), list):
        queries = [str(q).strip() for q in parsed["queries"] if str(q).strip()]
        if queries:
            return queries[:4]
    role = (profile.get("current_role") or "AI Engineer").strip()
    defaults = [role, "Machine Learning Engineer", "AI Engineer"]
    seen, out = set(), []
    for q in defaults:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out