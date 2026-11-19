"""LangGraph multi-agent pipeline: plan -> search -> dedupe -> rank -> enrich -> persist."""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypedDict

from langgraph.graph import END, StateGraph

from .. import rag
from ..db import SessionLocal
from ..models import Job, Profile, SearchRun, utcnow
from ..sources import ats_source, hirist, jobspy_source, naukri, wellfound
from ..sources.base import NormalizedJob
from . import matcher
from .enricher import enrich_top_jobs
from .query_planner import plan_queries

logger = logging.getLogger(__name__)


class SearchState(TypedDict, total=False):
    run_id: int
    params: dict
    profile: dict
    queries: list[str]
    raw_jobs: list[dict]
    ranked_jobs: list[dict]
    stats: dict
    errors: list[str]


def _progress(run_id: int, text: str, stats: dict | None = None):
    with SessionLocal() as db:
        run = db.get(SearchRun, run_id)
        if run:
            run.progress = text
            if stats is not None:
                run.stats = stats
            db.commit()


def _profile_dict(p: Profile) -> dict:
    return {
        "current_role": p.current_role, "experience_years": p.experience_years,
        "skills": p.skills or [], "target_roles": p.target_roles or [],
        "preferred_locations": p.preferred_locations or [], "remote_ok": p.remote_ok,
        "exp_stretch": p.exp_stretch, "raw_text": p.raw_text,
        "work_history": p.work_history or [], "projects": p.projects or [],
    }


def plan_node(state: SearchState) -> SearchState:
    params = state["params"]
    with SessionLocal() as db:
        p = db.get(Profile, 1)
        profile = _profile_dict(p) if p else {"experience_years": params.get("experience") or 1.2,
                                              "skills": [], "exp_stretch": 1.8}
    if params.get("experience") is not None:
        profile["experience_years"] = params["experience"]
    queries = plan_queries(profile, params.get("keywords"))
    _progress(state["run_id"], f"planned queries: {', '.join(queries)}")
    return {"profile": profile, "queries": queries, "stats": {}, "errors": []}


def _search_task(source: str, query: str, params: dict, profile: dict) -> tuple[str, list[NormalizedJob], str]:
    locations = params.get("locations") or profile.get("preferred_locations") or []
    location = locations[0] if locations else "India"
    hours_old = params.get("hours_old", 168)
    results = params.get("results_per_site", 30)
    try:
        if source == "naukri":
            jobs = naukri.search(query, location="" if location == "India" else location,
                                 experience=profile.get("experience_years") or 1,
                                 job_age_days=max(1, hours_old // 24), results=results)
        elif source in jobspy_source.SUPPORTED:
            jobs = jobspy_source.search([source], query, location=location,
                                        results=results, hours_old=hours_old)
        else:
            return source, [], f"unknown source {source}"
        return source, jobs, ""
    except Exception as e:
        logger.warning("Search failed [%s/%s]: %s", source, query, e)
        return source, [], str(e)


def _list_source_task(source: str, fn, *args) -> tuple[str, list, str]:
    try:
        return source, fn(*args), ""
    except Exception as e:
        logger.warning("Search failed [%s]: %s", source, e)
        return source, [], str(e)


def search_node(state: SearchState) -> SearchState:
    params, profile = state["params"], state["profile"]
    platforms = params.get("platforms") or ["naukri", "indeed", "linkedin", "glassdoor", "company_site", "wellfound", "hirist"]
    queries = state["queries"][:3]
    locations = params.get("locations") or profile.get("preferred_locations")
    tasks = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for source in platforms:
            if source == "company_site":
                tasks.append(pool.submit(_list_source_task, source, ats_source.search,
                                         queries, locations, profile.get("remote_ok", True), 40))
            elif source == "wellfound":
                tasks.append(pool.submit(_list_source_task, source, wellfound.search,
                                         queries, locations, profile.get("remote_ok", True), 40))
            elif source == "hirist":
                tasks.append(pool.submit(_list_source_task, source, hirist.search, queries, locations, 30))
            else:
                for q in queries[:2]:
                    tasks.append(pool.submit(_search_task, source, q, params, profile))
        raw, errors, by_source = [], [], {}
        for fut in as_completed(tasks):
            try:
                source, jobs, err = fut.result()
                raw.extend(j.to_dict() | {"dedupe_key": j.dedupe_key} for j in jobs)
                by_source[source] = by_source.get(source, 0) + len(jobs)
                if err:
                    errors.append(f"{source}: {err}")
            except Exception as e:
                errors.append(str(e))
    _progress(state["run_id"], f"fetched {len(raw)} jobs from {len(by_source)} sources",
              {"fetched": len(raw), "by_source": by_source, "errors": errors})
    return {"raw_jobs": raw, "errors": errors, "stats": {"fetched": len(raw), "by_source": by_source}}


def dedupe_node(state: SearchState) -> SearchState:
    seen, unique = set(), []
    for job in state.get("raw_jobs", []):
        key = job.get("dedupe_key") or ""
        if not key or key in seen or not job.get("title"):
            continue
        seen.add(key)
        unique.append(job)
    stats = state.get("stats", {})
    stats["duplicates_removed"] = len(state.get("raw_jobs", [])) - len(unique)
    _progress(state["run_id"], f"{len(unique)} unique jobs after dedupe", stats)
    return {"raw_jobs": unique, "stats": stats}


def rank_node(state: SearchState) -> SearchState:
    ranked = matcher.rank_jobs(state.get("raw_jobs", []), state["profile"],
                               include_out_of_range=state["params"].get("include_out_of_range", False))
    stats = state.get("stats", {})
    stats["out_of_range_filtered"] = len(state.get("raw_jobs", [])) - len(ranked)
    stats["ranked"] = len(ranked)
    _progress(state["run_id"], f"ranked {len(ranked)} jobs by match score", stats)
    return {"ranked_jobs": ranked, "stats": stats}


def enrich_node(state: SearchState) -> SearchState:
    jobs = enrich_top_jobs(state.get("ranked_jobs", []), state["profile"], top_n=10)
    _progress(state["run_id"], "generated match insights for top jobs", state.get("stats"))
    return {"ranked_jobs": jobs}


def persist_node(state: SearchState) -> SearchState:
    stats = state.get("stats", {})
    new_count = updated_count = 0
    to_index = []
    with SessionLocal() as db:
        for j in state.get("ranked_jobs", []):
            existing = db.query(Job).filter(Job.dedupe_key == j["dedupe_key"]).first()
            if existing:
                existing.match_score = j.get("match_score", 0)
                existing.score_breakdown = j.get("score_breakdown", {})
                if j.get("insights"):
                    existing.insights = j["insights"]
                    existing.enriched = True
                existing.search_run_id = state["run_id"]
                updated_count += 1
                to_index.append({"id": existing.id, **j})
            else:
                job = Job(
                    source=j.get("source", ""), source_id=j.get("source_id", ""),
                    dedupe_key=j["dedupe_key"], title=j.get("title", ""),
                    company=j.get("company", ""), location=j.get("location", ""),
                    is_remote=j.get("is_remote", False), salary=j.get("salary", ""),
                    exp_min=j.get("exp_min"), exp_max=j.get("exp_max"),
                    experience_text=j.get("experience_text", ""),
                    description=j.get("description", ""), skills=j.get("skills", []),
                    url=j.get("url", ""), posted_text=j.get("posted_text", ""),
                    posted_at=j.get("posted_at"), match_score=j.get("match_score", 0),
                    score_breakdown=j.get("score_breakdown", {}),
                    insights=j.get("insights", {}), enriched=j.get("enriched", False),
                    search_run_id=state["run_id"],
                )
                db.add(job)
                db.flush()
                new_count += 1
                to_index.append({"id": job.id, **j})
        run = db.get(SearchRun, state["run_id"])
        stats |= {"new_jobs": new_count, "updated_jobs": updated_count}
        if run:
            run.status = "completed"
            run.progress = "done"
            run.stats = stats
            run.finished_at = utcnow()
        db.commit()
    rag.index_jobs(to_index)
    return {"stats": stats}


def build_graph():
    g = StateGraph(SearchState)
    g.add_node("plan", plan_node)
    g.add_node("search", search_node)
    g.add_node("dedupe", dedupe_node)
    g.add_node("rank", rank_node)
    g.add_node("enrich", enrich_node)
    g.add_node("persist", persist_node)
    g.set_entry_point("plan")
    for a, b in [("plan", "search"), ("search", "dedupe"), ("dedupe", "rank"),
                 ("rank", "enrich"), ("enrich", "persist")]:
        g.add_edge(a, b)
    g.add_edge("persist", END)
    return g.compile()


graph = build_graph()


def run_search(run_id: int):
    with SessionLocal() as db:
        run = db.get(SearchRun, run_id)
        if not run:
            return
        params = run.params or {}
    try:
        graph.invoke({"run_id": run_id, "params": params})
    except Exception as e:
        logger.exception("Search run %s failed", run_id)
        with SessionLocal() as db:
            run = db.get(SearchRun, run_id)
            if run:
                run.status = "failed"
                run.error = str(e)
                run.finished_at = utcnow()
                db.commit()