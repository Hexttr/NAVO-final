import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from sqlalchemy.orm import Session
from database import get_db
from models import Intro
from config import settings

router = APIRouter(prefix="/intros", tags=["intros"])

UPLOAD_DIR = Path(settings.upload_dir) / "intros"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("")
def list_intros(db: Session = Depends(get_db)):
    return db.query(Intro).order_by(Intro.id.desc()).all()


@router.post("")
async def create_intro(title: str = Form(...), file: UploadFile = UploadFile(...), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix or ".mp3"
    if ext.lower() != ".mp3":
        ext = ".mp3"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(await file.read())
    i = Intro(title=title, file_path=str(path), duration_seconds=0)
    db.add(i)
    db.commit()
    db.refresh(i)
    return i


@router.delete("/{intro_id}")
def delete_intro(intro_id: int, db: Session = Depends(get_db)):
    i = db.query(Intro).get(intro_id)
    if not i:
        raise HTTPException(404, "Intro not found")
    db.delete(i)
    db.commit()
    return {"ok": True}
