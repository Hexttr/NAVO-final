import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Podcast
from config import settings

router = APIRouter(prefix="/podcasts", tags=["podcasts"])

UPLOAD_DIR = Path(settings.upload_dir) / "podcasts"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/{podcast_id}/audio")
def get_podcast_audio(podcast_id: int, db: Session = Depends(get_db)):
    p = db.query(Podcast).get(podcast_id)
    if not p or not p.file_path:
        raise HTTPException(404, "Podcast audio not found")
    path = Path(p.file_path)
    if not path.exists():
        path = UPLOAD_DIR / Path(p.file_path).name
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("")
def list_podcasts(db: Session = Depends(get_db)):
    return db.query(Podcast).order_by(Podcast.id.desc()).all()


@router.post("")
async def create_podcast(title: str = Form(...), file: UploadFile = UploadFile(...), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix or ".mp3"
    if ext.lower() != ".mp3":
        ext = ".mp3"
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(await file.read())
    p = Podcast(title=title, file_path=str(path), duration_seconds=0)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{podcast_id}")
def delete_podcast(podcast_id: int, db: Session = Depends(get_db)):
    p = db.query(Podcast).get(podcast_id)
    if not p:
        raise HTTPException(404, "Podcast not found")
    db.delete(p)
    db.commit()
    return {"ok": True}
