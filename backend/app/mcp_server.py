"""MCP server exposing JobPilot tools to external AI clients (Qoder, Claude Desktop, etc).

Run:  python -m app.mcp_server   (stdio transport)

Configure in your MCP client:
  { "mcpServers": { "jobpilot": { "command": "python", "args": ["-m", "app.mcp_server"],
                                  "cwd": "<path-to>/backend" } } }
"""
import json

from mcp.server.fastmcp import FastMCP

from . import rag
from .db import SessionLocal, init_db
from .models import Job
from .serializers import app_out, job_out
from .services import create_search_run, get_profile, set_application_status, tracker_stats

mcp = FastMCP("jobpilot")


@mcp.tool()
def get_profile() -> str:
    """Get the parsed candidate profile (skills, experience, target roles, locations)."""
    with SessionLocal() as db:
        p = get_profile(db)
        if not p:
            return json.dumps({"error": "No resume uploaded yet"})
        return json.dumps({"name": p.name, "current_role": p.current_role,
                           "experience_years": p.experience_years, "skills": p.skills,
                           "target_roles": p.target_roles, "preferred_locations": p.preferred_locations,
                           "exp_stretch": p.exp_stretch}, default=str)


@mcp.tool()
def search_jobs(keywords: str = "", locations: str = "", platforms: str = "naukri,indeed,linkedin,glassdoor,company_site") -> str:
    """Start a multi-agent job search. keywords/locations are comma-separated; empty = use profile.
    Returns a run_id; poll with get_search_run. Platforms: naukri, indeed, linkedin, glassdoor, company_site."""
    from .agents.graph import run_search

    with SessionLocal() as db:
        params = {"keywords": [k.strip() for k in keywords.split(",") if k.strip()] or None,
                  "locations": [l.strip() for l in locations.split(",") if l.strip()] or None,
                  "platforms": [p.strip() for p in platforms.split(",") if p.strip()],
                  "hours_old": 168, "results_per_site": 30}
        run = create_search_run(db, params)
        run_id = run.id
    run_search(run_id)
    with SessionLocal() as db:
        from .models import SearchRun
        run = db.get(SearchRun, run_id)
        return json.dumps({"run_id": run_id, "status": run.status, "stats": run.stats}, default=str)


@mcp.tool()
def get_search_run(run_id: int) -> str:
    """Check status/stats of a search run."""
    from .models import SearchRun

    with SessionLocal() as db:
        run = db.get(SearchRun, run_id)
        if not run:
            return json.dumps({"error": "run not found"})
        return json.dumps({"id": run.id, "status": run.status, "progress": run.progress,
                           "stats": run.stats, "error": run.error}, default=str)


@mcp.tool()
def top_matches(limit: int = 15, min_score: float = 0) -> str:
    """Get the highest-scoring matched jobs (title, company, score, experience fit, URL)."""
    with SessionLocal() as db:
        jobs = (db.query(Job).filter(Job.hidden == False, Job.match_score >= min_score)  # noqa: E712
                .order_by(Job.match_score.desc()).limit(limit).all())
        return json.dumps([job_out(j).model_dump(mode="json") for j in jobs], default=str)


@mcp.tool()
def semantic_job_search(query: str, k: int = 10) -> str:
    """RAG semantic search over all fetched jobs (e.g. 'LLM fine-tuning startup Bangalore')."""
    return json.dumps(rag.semantic_search(query, k=k), default=str)


@mcp.tool()
def update_application(job_id: int, status: str, current_round: str = "", notes: str = "") -> str:
    """Track an application. status: saved|applied|in_process|offer|rejected|ghosted.
    current_round (for in_process): Screening, Assessment, Technical Round 1/2/3, Managerial Round, HR Round."""
    with SessionLocal() as db:
        try:
            app = set_application_status(db, job_id, status,
                                         current_round=current_round or None, notes=notes or None)
        except ValueError as e:
            return json.dumps({"error": str(e)})
        return json.dumps(app_out(app).model_dump(mode="json"), default=str)


@mcp.tool()
def tracker_stats() -> str:
    """Job hunt funnel: applied/in-process/offer/rejected counts, response rate, rounds, recent activity."""
    with SessionLocal() as db:
        return json.dumps(tracker_stats(db), default=str)


if __name__ == "__main__":
    init_db()
    mcp.run()