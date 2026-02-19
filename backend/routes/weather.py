from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Weather, BroadcastItem
from config import settings
from pathlib import Path
from services.weather_service import fetch_weather_forecast
from services.settings_service import get, WEATHER_REGIONS
from services.llm_service import generate_weather_text
from services.tts_service import text_to_speech

router = APIRouter(prefix="/weather", tags=["weather"])


class WeatherCreate(BaseModel):
    text: str
    broadcast_date: date | None = None


class WeatherUpdate(BaseModel):
    text: str | None = None


@router.get("")
def list_weather(
    d: date | None = Query(None, description="Фильтр по дате YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    q = db.query(Weather).order_by(Weather.id.desc())
    if d is not None:
        q = q.filter(or_(Weather.broadcast_date == d, Weather.broadcast_date.is_(None)))
    return q.all()


@router.get("/{weather_id}/audio")
def get_weather_audio(weather_id: int, db: Session = Depends(get_db)):
    w = db.query(Weather).get(weather_id)
    if not w or not w.audio_path:
        raise HTTPException(404, "Audio not found")
    path = Path(w.audio_path)
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="audio/mpeg")


@router.post("")
def create_weather(data: WeatherCreate, db: Session = Depends(get_db)):
    w = Weather(text=data.text, broadcast_date=data.broadcast_date)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@router.post("/generate")
async def generate_weather(
    d: date | None = Query(None, description="Дата для новой записи YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    region = get(db, "weather_region") or "dushanbe"
    city = WEATHER_REGIONS.get(region, ("Душанбе", "Dushanbe"))[1]
    raw = await fetch_weather_forecast(city)
    text = await generate_weather_text(db, raw)
    w = Weather(text=text, broadcast_date=d)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@router.post("/{weather_id}/regenerate")
async def regenerate_weather(
    weather_id: int,
    d: date | None = Query(None, description="Дата эфира — создаётся новая запись на этот день"),
    broadcast_item_id: int | None = Query(None, description="ID слота в эфире — обновить ссылку"),
    db: Session = Depends(get_db),
):
    """Перегенерировать: создаёт НОВУЮ запись на дату d, обновляет слот. Иначе — перезаписывает текущую."""
    region = get(db, "weather_region") or "dushanbe"
    city = WEATHER_REGIONS.get(region, ("Душанбе", "Dushanbe"))[1]
    raw = await fetch_weather_forecast(city)
    text = await generate_weather_text(db, raw)

    if d is not None:
        w = Weather(text=text, broadcast_date=d)
        db.add(w)
        db.commit()
        db.refresh(w)
        if broadcast_item_id is not None:
            slot = db.query(BroadcastItem).filter(
                BroadcastItem.id == broadcast_item_id,
                BroadcastItem.entity_type == "weather",
            ).first()
            if slot:
                slot.entity_id = w.id
                db.commit()
        return w
    else:
        w = db.query(Weather).get(weather_id)
        if not w:
            raise HTTPException(404, "Weather not found")
        w.text = text
        w.audio_path = ""
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
    await text_to_speech(w.text, path, voice, db=db)
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
