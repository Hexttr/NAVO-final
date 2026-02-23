import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from database import get_db
from models import Intro
from config import settings
from services.streamer_service import get_entity_duration_from_file
from utils.upload_utils import read_with_limit
from utils.audio_utils import apply_volume_boost

router = APIRouter(prefix="/intros", tags=["intros"])

UPLOAD_DIR = Path(settings.upload_dir) / "intros"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/{intro_id}/audio")
def get_intro_audio(intro_id: int, db: Session = Depends(get_db)):
    i = db.get(Intro,intro_id)
    if not i or not i.file_path:
        raise HTTPException(404, "Intro audio not found")
    path = Path(i.file_path)
    if not path.exists():
        path = UPLOAD_DIR / Path(i.file_path).name
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("")
def list_intros(db: Session = Depends(get_db)):
    return db.query(Intro).order_by(Intro.id.desc()).all()


@router.post("")
async def create_intro(title: str = Form(...), file: UploadFile = UploadFile(...), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix or ".mp3"
    if ext.lower() != ".mp3":
        ext = ".mp3"
    max_bytes = getattr(settings, "upload_max_bytes", 0) or 52428800  # 50 MB
    content = await read_with_limit(file, max_bytes)
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(content)
    boost = getattr(settings, "podcast_intro_volume_boost", 1.0) or 1.0
    if boost > 1.01:
        apply_volume_boost(path, float(boost))
    i = Intro(title=title, file_path=str(path), duration_seconds=0)
    db.add(i)
    db.commit()
    db.refresh(i)
    dur = get_entity_duration_from_file(db, "intro", i.id)
    if dur > 0:
        i.duration_seconds = round(dur, 1)
        db.commit()
        db.refresh(i)
    return i


@router.post("/apply-volume-boost")
def apply_intro_volume_boost(db: Session = Depends(get_db)):
    """Усилить громкость всех интро (PODCAST_INTRO_VOLUME_BOOST). Для уже загруженных."""
    boost = getattr(settings, "podcast_intro_volume_boost", 1.0) or 1.0
    if boost <= 1.01:
        return {"updated": 0, "message": "PODCAST_INTRO_VOLUME_BOOST не задан или 1.0"}
    updated = 0
    for i in db.query(Intro).filter(Intro.file_path != "").all():
        path = Path(i.file_path)
        if path.exists() and apply_volume_boost(path, float(boost)):
            updated += 1
    return {"updated": updated, "message": f"Громкость усилена у {updated} интро"}


@router.post("/recalc-durations")
def recalc_intro_durations(db: Session = Depends(get_db)):
    """Пересчитать длительность всех интро из файлов (ffprobe)."""
    updated = 0
    for i in db.query(Intro).filter(Intro.file_path != "").all():
        dur = get_entity_duration_from_file(db, "intro", i.id)
        if dur > 0 and (not i.duration_seconds or abs(i.duration_seconds - dur) > 1):
            i.duration_seconds = round(dur, 1)
            updated += 1
    db.commit()
    return {"updated": updated, "message": f"Обновлено {updated} интро"}


@router.delete("/{intro_id}")
def delete_intro(intro_id: int, db: Session = Depends(get_db)):
    i = db.get(Intro,intro_id)
    if not i:
        raise HTTPException(404, "Intro not found")
    db.delete(i)
    db.commit()
    return {"ok": True}
