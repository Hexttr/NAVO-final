import asyncio
import json
import random
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Song
from config import settings
from services.jamendo import JamendoService, search_tracks, download_track
from services.groq_service import generate_dj_text
from services.tts_service import text_to_speech

router = APIRouter(prefix="/songs", tags=["songs"])

UPLOAD_DIR = Path(settings.upload_dir) / "songs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class SongCreate(BaseModel):
    title: str
    artist: str
    album: str = ""


class SongUpdate(BaseModel):
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    dj_text: str | None = None


@router.get("")
def list_songs(db: Session = Depends(get_db)):
    return db.query(Song).order_by(Song.id.desc()).all()


@router.get("/{song_id}/audio")
def get_song_audio(song_id: int, db: Session = Depends(get_db)):
    song = db.query(Song).get(song_id)
    if not song or not song.file_path:
        raise HTTPException(404, "Audio not found")
    path = Path(song.file_path)
    if not path.exists():
        path = UPLOAD_DIR / path.name
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/{song_id}/dj-audio")
def get_song_dj_audio(song_id: int, db: Session = Depends(get_db)):
    song = db.query(Song).get(song_id)
    if not song or not song.dj_audio_path:
        raise HTTPException(404, "DJ audio not found")
    path = Path(song.dj_audio_path)
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="audio/mpeg")


@router.post("")
async def create_song(data: SongCreate, db: Session = Depends(get_db)):
    # Manual create - need file via separate upload
    song = Song(title=data.title, artist=data.artist, album=data.album, file_path="")
    db.add(song)
    db.commit()
    db.refresh(song)
    return song


@router.post("/upload/{song_id}")
async def upload_song_file(song_id: int, file: UploadFile, db: Session = Depends(get_db)):
    song = db.query(Song).get(song_id)
    if not song:
        raise HTTPException(404, "Song not found")
    ext = Path(file.filename or "").suffix or ".mp3"
    if ext.lower() != ".mp3":
        ext = ".mp3"
    path = UPLOAD_DIR / f"{song_id}_{uuid.uuid4().hex}{ext}"
    path.write_bytes(await file.read())
    song.file_path = str(path)
    db.commit()
    return {"file_path": song.file_path}


@router.post("/jamendo/generate")
async def generate_from_jamendo(db: Session = Depends(get_db)):
    tracks = await JamendoService.search_and_get_tracks(limit_per_query=20)
    if not tracks:
        raise HTTPException(502, "Jamendo API не вернул треки. Проверьте запрос или попробуйте позже.")
    created = []
    for t in tracks:
        tid = t.get("id")
        if not tid:
            continue
        tid = str(tid)
        url = t.get("audiodownload") or t.get("audio") or f"https://prod-1.storage.jamendo.com/download/track/{tid}/mp32/"
        title = t.get("name", "Unknown")
        artist = t.get("artist_name", "Unknown")
        album = t.get("album_name", "")
        song = Song(title=title, artist=artist, album=album, file_path="")
        db.add(song)
        db.commit()
        db.refresh(song)
        try:
            path = UPLOAD_DIR / f"{song.id}_{uuid.uuid4().hex}.mp3"
            await download_track(url, path)
            song.file_path = str(path)
            song.duration_seconds = float(t.get("duration", 0))
            db.commit()
            created.append({"id": song.id, "title": title, "artist": artist})
        except Exception as e:
            db.delete(song)
            db.commit()
            import logging
            logging.warning(f"Jamendo download failed for {tid}: {e}")
    return {"created": len(created), "songs": created}


@router.get("/jamendo/generate-stream")
async def generate_from_jamendo_stream(db: Session = Depends(get_db)):
    """Streaming endpoint with progress updates via SSE."""

    async def event_generator():
        try:
            tracks = await JamendoService.search_and_get_tracks(limit_per_query=20)
            total = len(tracks)
            if total == 0:
                yield f"data: {json.dumps({'error': 'Нет треков', 'progress': 0})}\n\n"
                return
            yield f"data: {json.dumps({'progress': 0, 'current': 0, 'total': total, 'created': 0})}\n\n"
            created = 0
            for i, t in enumerate(tracks):
                tid = t.get("id")
                if not tid:
                    continue
                tid = str(tid)
                url = t.get("audiodownload") or t.get("audio") or f"https://prod-1.storage.jamendo.com/download/track/{tid}/mp32/"
                title = t.get("name", "Unknown")
                artist = t.get("artist_name", "Unknown")
                album = t.get("album_name", "")
                song = Song(title=title, artist=artist, album=album, file_path="")
                db.add(song)
                db.commit()
                db.refresh(song)
                try:
                    path = UPLOAD_DIR / f"{song.id}_{uuid.uuid4().hex}.mp3"
                    await download_track(url, path)
                    song.file_path = str(path)
                    song.duration_seconds = float(t.get("duration", 0))
                    db.commit()
                    created += 1
                except Exception:
                    db.delete(song)
                    db.commit()
                progress = int((i + 1) / total * 100)
                yield f"data: {json.dumps({'progress': progress, 'current': i + 1, 'total': total, 'created': created})}\n\n"
            yield f"data: {json.dumps({'progress': 100, 'done': True, 'created': created})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'progress': 0})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{song_id}/generate-dj")
async def generate_dj(song_id: int, db: Session = Depends(get_db)):
    song = db.query(Song).get(song_id)
    if not song:
        raise HTTPException(404, "Song not found")
    greeting_allowed = random.random() < 0.1
    text = await generate_dj_text(song.artist, song.title, song.album, greeting_allowed)
    song.dj_text = text
    song.dj_audio_path = ""  # сброс озвучки при смене текста
    db.commit()
    return {"dj_text": text}


@router.post("/{song_id}/tts")
async def generate_dj_audio(song_id: int, voice: str = "ru-RU-DmitryNeural", db: Session = Depends(get_db)):
    song = db.query(Song).get(song_id)
    if not song or not song.dj_text:
        raise HTTPException(400, "Song or DJ text not found")
    audio_dir = Path(settings.upload_dir) / "dj"
    audio_dir.mkdir(parents=True, exist_ok=True)
    path = audio_dir / f"dj_{song_id}.mp3"
    await text_to_speech(song.dj_text, path, voice)
    song.dj_audio_path = str(path)
    db.commit()
    return {"audio_path": song.dj_audio_path}


@router.post("/generate-dj-batch")
async def generate_dj_batch(song_ids: list[int] = Query(..., alias="song_ids"), db: Session = Depends(get_db)):
    from services.groq_service import RATE_LIMIT_DELAY

    results = []
    for i, sid in enumerate(song_ids):
        if i > 0:
            await asyncio.sleep(RATE_LIMIT_DELAY)
        song = db.query(Song).get(sid)
        if song:
            try:
                greeting_allowed = random.random() < 0.1
                text = await generate_dj_text(song.artist, song.title, song.album, greeting_allowed)
                song.dj_text = text
                song.dj_audio_path = ""
                db.commit()
                results.append({"id": sid, "dj_text": text})
            except Exception as e:
                results.append({"id": sid, "error": str(e)})
    return {"results": results}


@router.patch("/{song_id}")
def update_song(song_id: int, data: SongUpdate, db: Session = Depends(get_db)):
    song = db.query(Song).get(song_id)
    if not song:
        raise HTTPException(404, "Song not found")
    if data.title is not None:
        song.title = data.title
    if data.artist is not None:
        song.artist = data.artist
    if data.album is not None:
        song.album = data.album
    if data.dj_text is not None:
        song.dj_text = data.dj_text
    db.commit()
    db.refresh(song)
    return song


@router.delete("/{song_id}")
def delete_song(song_id: int, db: Session = Depends(get_db)):
    song = db.query(Song).get(song_id)
    if not song:
        raise HTTPException(404, "Song not found")
    db.delete(song)
    db.commit()
    return {"ok": True}
