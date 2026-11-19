from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import rag
from ..agents.resume_parser import parse_resume
from ..db import get_db
from ..schemas import ProfileOut, ProfileUpdate
from ..services import get_profile, upsert_profile

router = APIRouter(prefix="/api/profile", tags=["profile"])

MAX_RESUME_BYTES = 5 * 1024 * 1024


@router.get("", response_model=ProfileOut | None)
def read_profile(db: Session = Depends(get_db)):
    return get_profile(db)


@router.post("/resume", response_model=ProfileOut)
async def upload_resume(file: UploadFile, db: Session = Depends(get_db)):
    filename = file.filename or "resume"
    if not filename.lower().endswith((".pdf", ".docx", ".txt")):
        raise HTTPException(400, "Upload a PDF, DOCX or TXT resume")
    data = await file.read()
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(400, "Resume must be under 5 MB")
    try:
        text, parsed = parse_resume(filename, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(422, f"Could not parse resume: {e}")
    profile = upsert_profile(db, parsed, raw_text=text, filename=filename)
    rag.index_profile({**parsed, "raw_text": text})
    return profile


@router.put("", response_model=ProfileOut)
def update_profile(body: ProfileUpdate, db: Session = Depends(get_db)):
    p = get_profile(db)
    if not p:
        raise HTTPException(404, "Upload a resume first")
    for key, val in body.model_dump(exclude_none=True).items():
        setattr(p, key, val)
    db.commit()
    db.refresh(p)
    return p