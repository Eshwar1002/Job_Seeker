from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application
from ..schemas import ApplicationOut, ApplicationUpdate, StatsOut
from ..serializers import app_out
from ..services import set_application_status, tracker_stats

router = APIRouter(prefix="/api", tags=["tracker"])


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(status: str = "", db: Session = Depends(get_db)):
    query = db.query(Application)
    if status:
        query = query.filter(Application.status == status)
    apps = query.order_by(Application.updated_at.desc()).all()
    return [app_out(a, include_job=True) for a in apps]


@router.patch("/applications/{app_id}", response_model=ApplicationOut)
def update_application(app_id: int, body: ApplicationUpdate, db: Session = Depends(get_db)):
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    try:
        app = set_application_status(
            db, app.job_id, body.status or app.status,
            current_round=body.current_round, notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return app_out(app, include_job=True)


@router.delete("/applications/{app_id}")
def delete_application(app_id: int, db: Session = Depends(get_db)):
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    db.delete(app)
    db.commit()
    return {"ok": True}


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    return tracker_stats(db)