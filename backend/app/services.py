"""Shared service layer used by both the FastAPI routers and the MCP server."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import APPLICATION_STATUSES, Application, Job, Profile, SearchRun, utcnow


def get_profile(db: Session) -> Profile | None:
    return db.get(Profile, 1)


def upsert_profile(db: Session, data: dict, raw_text: str = "", filename: str = "") -> Profile:
    p = db.get(Profile, 1)
    if not p:
        p = Profile(id=1)
        db.add(p)
    for key in ("name", "email", "phone", "current_role", "experience_years", "skills",
                "work_history", "education", "projects", "certifications"):
        if key in data and data[key] is not None:
            setattr(p, key, data[key])
    if raw_text:
        p.raw_text = raw_text
    if filename:
        p.resume_filename = filename
    if not p.target_roles:
        p.target_roles = [data.get("current_role") or "AI Engineer"]
    if not p.preferred_locations:
        p.preferred_locations = ["Bengaluru", "Hyderabad", "Pune", "Remote"]
    p.updated_at = utcnow()
    db.commit()
    db.refresh(p)
    return p


def create_search_run(db: Session, params: dict) -> SearchRun:
    run = SearchRun(params=params, status="running", progress="starting")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def set_application_status(db: Session, job_id: int, status: str,
                           current_round: str | None = None, notes: str | None = None) -> Application:
    if status not in APPLICATION_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {APPLICATION_STATUSES}")
    job = db.get(Job, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    app = db.query(Application).filter(Application.job_id == job_id).first()
    if not app:
        app = Application(job_id=job_id, status="saved", status_history=[])
        db.add(app)
        db.flush()
    old = app.status
    app.status = status
    if current_round is not None:
        app.current_round = current_round
    elif status != "in_process":
        app.current_round = ""
    if notes is not None:
        app.notes = notes
    if status == "applied" and not app.applied_at:
        app.applied_at = utcnow()
    history = list(app.status_history or [])
    history.append({"from": old, "to": status, "round": app.current_round,
                    "at": utcnow().isoformat(), "note": notes or ""})
    app.status_history = history
    app.updated_at = utcnow()
    db.commit()
    db.refresh(app)
    return app


def tracker_stats(db: Session) -> dict:
    counts = {s: 0 for s in APPLICATION_STATUSES}
    rows = db.query(Application.status, func.count()).group_by(Application.status).all()
    for status, count in rows:
        counts[status] = count
    total_jobs = db.query(func.count(Job.id)).filter(Job.hidden == False).scalar() or 0  # noqa: E712
    avg_score = db.query(func.avg(Job.match_score)).filter(Job.hidden == False).scalar() or 0.0  # noqa: E712
    by_source = dict(db.query(Job.source, func.count()).filter(Job.hidden == False).group_by(Job.source).all())  # noqa: E712
    by_round = dict(db.query(Application.current_round, func.count())
                    .filter(Application.status == "in_process", Application.current_round != "")
                    .group_by(Application.current_round).all())
    applied_total = counts["applied"] + counts["in_process"] + counts["offer"] + counts["rejected"] + counts["ghosted"]
    responses = counts["in_process"] + counts["offer"] + counts["rejected"]
    response_rate = round(100 * responses / applied_total, 1) if applied_total else 0.0
    recent = (db.query(Application).order_by(Application.updated_at.desc()).limit(10).all())
    activity = [{"job_id": a.job_id, "title": a.job.title if a.job else "",
                 "company": a.job.company if a.job else "", "status": a.status,
                 "round": a.current_round, "at": a.updated_at.isoformat()} for a in recent]
    return {
        "total_jobs": total_jobs, **counts,
        "response_rate": response_rate, "avg_match_score": round(float(avg_score), 1),
        "by_source": by_source, "by_round": by_round, "recent_activity": activity,
    }