from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import rag
from ..agents.enricher import enrich_job
from ..db import get_db
from ..models import Job
from ..schemas import ApplicationCreate, ApplicationOut, JobOut
from ..serializers import app_out, job_out
from ..services import get_profile, set_application_status

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    q: str = "", source: str = "", min_score: float = 0.0,
    status: str = "", exp_fit: str = "", sort: str = "score",
    limit: int = Query(default=100, le=500), offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Job).filter(Job.hidden == False)  # noqa: E712
    if q:
        like = f"%{q}%"
        query = query.filter((Job.title.ilike(like)) | (Job.company.ilike(like)) | (Job.location.ilike(like)))
    if source:
        query = query.filter(Job.source == source)
    if min_score:
        query = query.filter(Job.match_score >= min_score)
    if status == "untracked":
        query = query.filter(~Job.application.has())
    elif status:
        query = query.filter(Job.application.has(status=status))
    query = query.order_by(Job.match_score.desc() if sort == "score" else Job.fetched_at.desc())
    jobs = query.offset(offset).limit(limit).all()
    out = [job_out(j) for j in jobs]
    if exp_fit:
        out = [j for j in out if (j.score_breakdown or {}).get("exp_fit") == exp_fit]
    return out


@router.get("/semantic")
def semantic_jobs(q: str, k: int = 20, db: Session = Depends(get_db)):
    results = rag.semantic_search(q, k=k)
    out = []
    for r in results:
        job = db.get(Job, r["job_id"])
        if job and not job.hidden:
            data = job_out(job).model_dump(mode="json")
            data["semantic_distance"] = round(r["distance"], 4)
            out.append(data)
    return out


@router.post("/rerank")
def rerank_jobs(db: Session = Depends(get_db)):
    """Re-score all stored jobs against the current profile (e.g. after profile edit or embedding fix)."""
    from ..agents.matcher import rank_jobs

    p = get_profile(db)
    if not p:
        raise HTTPException(400, "Upload a resume first")
    profile = {"skills": p.skills or [], "experience_years": p.experience_years,
               "exp_stretch": p.exp_stretch, "current_role": p.current_role,
               "target_roles": p.target_roles or [], "raw_text": p.raw_text,
               "work_history": p.work_history or [], "projects": p.projects or []}
    jobs = db.query(Job).filter(Job.hidden == False).all()  # noqa: E712
    payload = [{"id": j.id, "title": j.title, "company": j.company, "skills": j.skills,
                "description": j.description, "exp_min": j.exp_min, "exp_max": j.exp_max} for j in jobs]
    ranked = rank_jobs(payload, profile, include_out_of_range=True)
    by_id = {r["id"]: r for r in ranked}
    for j in jobs:
        r = by_id.get(j.id)
        if r:
            j.match_score = r["match_score"]
            j.score_breakdown = r["score_breakdown"]
    db.commit()
    return {"reranked": len(by_id)}


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job_out(job)


@router.post("/{job_id}/save", response_model=ApplicationOut)
def save_job(job_id: int, db: Session = Depends(get_db)):
    try:
        app = set_application_status(db, job_id, "saved")
    except ValueError as e:
        raise HTTPException(404, str(e))
    return app_out(app)


@router.post("/{job_id}/track", response_model=ApplicationOut)
def track_job(job_id: int, body: ApplicationCreate, db: Session = Depends(get_db)):
    try:
        app = set_application_status(db, job_id, body.status)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return app_out(app)


@router.post("/{job_id}/hide")
def hide_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.hidden = True
    db.commit()
    return {"ok": True}


@router.post("/{job_id}/enrich", response_model=JobOut)
def enrich(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    p = get_profile(db)
    profile = {"skills": p.skills if p else [], "experience_years": p.experience_years if p else 1.2,
               "current_role": p.current_role if p else "", "raw_text": p.raw_text if p else ""}
    data = {"title": job.title, "company": job.company, "location": job.location,
            "skills": job.skills, "description": job.description,
            "experience_text": job.experience_text, "score_breakdown": job.score_breakdown}
    job.insights = enrich_job(data, profile)
    job.enriched = True
    db.commit()
    db.refresh(job)
    return job_out(job)