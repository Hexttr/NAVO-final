from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Weather
from config import settings
from pathlib import Path
from services.weather_service import fetch_weather_forecast
from services.groq_service import generate_weather_text
from services.tts_service import text_to_speech

router = APIRouter(prefix="/weather", tags=["weather"])


class WeatherCreate(BaseModel):
    text: str


class WeatherUpdate(BaseModel):
    text: str | None = None


@router.get("")
def list_weather(db: Session = Depends(get_db)):
    return db.query(Weather).order_by(Weather.id.desc()).all()


@router.post("")
def create_weather(data: WeatherCreate, db: Session = Depends(get_db)):
    w = Weather(text=data.text)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@router.post("/generate")
async def generate_weather(db: Session = Depends(get_db)):
    raw = await fetch_weather_forecast()
    text = await generate_weather_text(raw)
    w = Weather(text=text)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@router.post("/{weather_id}/tts")
async def generate_weather_audio(weather_id: int, voice: str = "ru-RU-DmitryNeural", db: Session = Depends(get_db)):
    w = db.query(Weather).get(weather_id)
    if not w or not w.text:
        raise HTTPException(400, "Weather or text not found")
    audio_dir = Path(settings.upload_dir) / "weather"
    audio_dir.mkdir(parents=True, exist_ok=True)
    path = audio_dir / f"weather_{weather_id}.mp3"
    await text_to_speech(w.text, path, voice)
    w.audio_path = str(path)
    db.commit()
    return {"audio_path": w.audio_path}


@router.patch("/{weather_id}")
def update_weather(weather_id: int, data: WeatherUpdate, db: Session = Depends(get_db)):
    w = db.query(Weather).get(weather_id)
    if not w:
        raise HTTPException(404, "Weather not found")
    if data.text is not None:
        w.text = data.text
    db.commit()
    db.refresh(w)
    return w


@router.delete("/{weather_id}")
def delete_weather(weather_id: int, db: Session = Depends(get_db)):
    w = db.query(Weather).get(weather_id)
    if not w:
        raise HTTPException(404, "Weather not found")
    db.delete(w)
    db.commit()
    return {"ok": True}
