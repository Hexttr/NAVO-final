from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import News
from config import settings
from pathlib import Path
from services.news_service import fetch_news_from_rss
from services.groq_service import generate_news_text
from services.tts_service import text_to_speech

router = APIRouter(prefix="/news", tags=["news"])


class NewsCreate(BaseModel):
    text: str


class NewsUpdate(BaseModel):
    text: str | None = None


@router.get("")
def list_news(db: Session = Depends(get_db)):
    return db.query(News).order_by(News.id.desc()).all()


@router.get("/{news_id}/audio")
def get_news_audio(news_id: int, db: Session = Depends(get_db)):
    n = db.query(News).get(news_id)
    if not n or not n.audio_path:
        raise HTTPException(404, "Audio not found")
    path = Path(n.audio_path)
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="audio/mpeg")


@router.post("")
def create_news(data: NewsCreate, db: Session = Depends(get_db)):
    n = News(text=data.text)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.post("/generate")
async def generate_news(db: Session = Depends(get_db)):
    items = await fetch_news_from_rss(limit=15)
    if not items:
        raise HTTPException(500, "Не удалось получить новости из источников")
    news_texts = [f"{x['title']}. {x['summary']}" for x in items]
    text = await generate_news_text(news_texts)
    n = News(text=text)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.post("/{news_id}/tts")
async def generate_news_audio(news_id: int, voice: str = "ru-RU-DmitryNeural", db: Session = Depends(get_db)):
    n = db.query(News).get(news_id)
    if not n or not n.text:
        raise HTTPException(400, "News or text not found")
    audio_dir = Path(settings.upload_dir) / "news"
    audio_dir.mkdir(parents=True, exist_ok=True)
    path = audio_dir / f"news_{news_id}.mp3"
    await text_to_speech(n.text, path, voice)
    n.audio_path = str(path)
    db.commit()
    return {"audio_path": n.audio_path}


@router.patch("/{news_id}")
def update_news(news_id: int, data: NewsUpdate, db: Session = Depends(get_db)):
    n = db.query(News).get(news_id)
    if not n:
        raise HTTPException(404, "News not found")
    if data.text is not None:
        n.text = data.text
    db.commit()
    db.refresh(n)
    return n


@router.delete("/{news_id}")
def delete_news(news_id: int, db: Session = Depends(get_db)):
    n = db.query(News).get(news_id)
    if not n:
        raise HTTPException(404, "News not found")
    db.delete(n)
    db.commit()
    return {"ok": True}
