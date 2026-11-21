"""Serialization helpers that avoid Job <-> Application recursion."""
from .models import Application, Job, TailoredResume
from .schemas import ApplicationOut, JobOut, TailoredResumeOut

_JOB_FIELDS = [
    "id", "source", "title", "company", "location", "is_remote", "salary",
    "exp_min", "exp_max", "experience_text", "description", "skills", "url",
    "posted_text", "posted_at", "fetched_at", "match_score", "score_breakdown",
    "insights", "enriched",
]


def app_out(app: Application, include_job: bool = False) -> ApplicationOut:
    out = ApplicationOut(
        id=app.id, job_id=app.job_id, status=app.status, current_round=app.current_round,
        notes=app.notes, status_history=app.status_history or [], applied_at=app.applied_at,
        created_at=app.created_at, updated_at=app.updated_at,
    )
    if include_job and app.job:
        out.job = job_out(app.job, include_application=False).model_dump(mode="json")
    return out


def job_out(job: Job, include_application: bool = True) -> JobOut:
    data = {f: getattr(job, f) for f in _JOB_FIELDS}
    data["application"] = None
    out = JobOut.model_validate(data)
    if include_application and job.application:
        out.application = app_out(job.application)
    return out


def tailor_out(t: TailoredResume) -> TailoredResumeOut:
    return TailoredResumeOut.model_validate(t)