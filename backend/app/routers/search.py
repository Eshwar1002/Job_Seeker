from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents.graph import run_search
from ..db import get_db
from ..models import SearchRun
from ..schemas import SearchRequest, SearchRunOut
from ..services import create_search_run, get_profile

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchRunOut)
def start_search(body: SearchRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    if not get_profile(db):
        raise HTTPException(400, "Upload your resume first (Profile tab)")
    active = db.query(SearchRun).filter(SearchRun.status == "running").first()
    if active:
        raise HTTPException(409, f"Search run {active.id} is already in progress")
    run = create_search_run(db, body.model_dump())
    background.add_task(run_search, run.id)
    return run


@router.get("/runs", response_model=list[SearchRunOut])
def list_runs(db: Session = Depends(get_db)):
    return db.query(SearchRun).order_by(SearchRun.started_at.desc()).limit(20).all()


@router.get("/runs/{run_id}", response_model=SearchRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(SearchRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run