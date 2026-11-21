"""Resume tailoring endpoints, gated to jobs with match_score >= 75."""
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..agents import resume_tailor as rt
from ..db import get_db
from ..models import Job, TailoredResume
from ..schemas import TailorSave, TailoredResumeOut
from ..serializers import tailor_out
from ..services import get_profile

router = APIRouter(prefix="/api", tags=["tailor"])


def _get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


def _gate(job: Job):
    if job.match_score < rt.TAILOR_MIN_SCORE:
        raise HTTPException(
            403,
            f"Resume tailoring unlocks at {rt.TAILOR_MIN_SCORE:.0f}% match "
            f"(this job is {job.match_score:.0f}%). Pick a closer role first.",
        )


def _profile(db: Session) -> dict:
    p = get_profile(db)
    if not p:
        raise HTTPException(400, "Upload a resume first")
    return {"skills": p.skills or [], "raw_text": p.raw_text,
            "experience_years": p.experience_years, "current_role": p.current_role}


def _jobdict(job: Job) -> dict:
    return {"title": job.title, "company": job.company,
            "skills": job.skills, "description": job.description}


@router.get("/jobs/{job_id}/tailor")
def get_tailor(job_id: int, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _gate(job)
    profile = _profile(db)
    jd = _jobdict(job)
    gaps = rt.classify_gaps(profile, jd)
    base = rt.ats_score(profile["raw_text"], jd)
    return {
        "job_id": job.id, "match_score": job.match_score, "min_score": rt.TAILOR_MIN_SCORE,
        "master_content": profile["raw_text"], "gaps": gaps, "base_ats": base,
        "tailored": tailor_out(job.tailored).model_dump(mode="json") if job.tailored else None,
    }


@router.post("/jobs/{job_id}/tailor/score")
def score_tailor(job_id: int, body: TailorSave, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _gate(job)
    return rt.ats_score(body.content, _jobdict(job))


@router.post("/jobs/{job_id}/tailor/draft")
def draft_tailor(job_id: int, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _gate(job)
    profile = _profile(db)
    jd = _jobdict(job)
    gaps = rt.classify_gaps(profile, jd)
    return rt.build_draft(profile, jd, gaps)


@router.post("/jobs/{job_id}/tailor", response_model=TailoredResumeOut)
def save_tailor(job_id: int, body: TailorSave, db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _gate(job)
    profile = _profile(db)
    jd = _jobdict(job)
    gaps = rt.classify_gaps(profile, jd)
    base = rt.ats_score(profile["raw_text"], jd)
    cur = rt.ats_score(body.content, jd)
    t = job.tailored
    if not t:
        t = TailoredResume(job_id=job.id)
        db.add(t)
    t.content = body.content
    t.base_ats_score = base["score"]
    t.ats_score = cur["score"]
    t.keywords_added = sorted(set(base["missing_keywords"]) - set(cur["missing_keywords"]))
    t.gaps = gaps
    db.commit()
    db.refresh(t)
    return tailor_out(t)


@router.get("/jobs/{job_id}/tailor/export")
def export_tailor(job_id: int, format: str = Query("txt", pattern="^(txt|docx)$"),
                  db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    _gate(job)
    p = get_profile(db)
    content = job.tailored.content if job.tailored else (p.raw_text if p else "")
    fname = f"tailored_resume_job{job.id}"
    if format == "docx":
        import docx

        document = docx.Document()
        for line in content.splitlines():
            document.add_paragraph(line)
        buf = io.BytesIO()
        document.save(buf)
        return Response(
            buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{fname}.docx"'},
        )
    return Response(content, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{fname}.txt"'})


@router.get("/tailored", response_model=list[TailoredResumeOut])
def list_tailored(db: Session = Depends(get_db)):
    rows = db.query(TailoredResume).order_by(TailoredResume.updated_at.desc()).all()
    return [tailor_out(t) for t in rows]