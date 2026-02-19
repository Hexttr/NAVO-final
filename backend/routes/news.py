import uuid
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import News, BroadcastItem
from config import settings
from pathlib import Path
from services.news_service import fetch_news_from_rss
from services.llm_service import generate_news_text
from services.settings_service import get, NEWS_REGIONS
from services.tts_service import text_to_speech

router = APIRouter(prefix="/news", tags=["news"])


class NewsCreate(BaseModel):
    text: str
    broadcast_date: date | None = None


class NewsUpdate(BaseModel):
    text: str | None = None


@router.get("/rss-test")
async def rss_test(db: Session = Depends(get_db)):
    """Проверка: что возвращают RSS-источники. Для отладки."""
    from services.news_service import fetch_news_from_rss
    region = get(db, "news_region") or "tajikistan"
    rss_urls = NEWS_REGIONS.get(region, NEWS_REGIONS["tajikistan"])
    items = await fetch_news_from_rss(limit=10, rss_urls=rss_urls)
    return {"count": len(items), "items": [{"title": x["title"], "summary": (x["summary"] or "")[:100]} for x in items]}


@router.get("")
def list_news(
    d: date | None = Query(None, description="Фильтр по дате YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    q = db.query(News).order_by(News.id.desc())
    if d is not None:
        from sqlalchemy import or_
        q = q.filter(or_(News.broadcast_date == d, News.broadcast_date.is_(None)))
    return q.all()


@router.get("/{news_id}")
def get_news(news_id: int, db: Session = Depends(get_db)):
    n = db.query(News).get(news_id)
    if not n:
        raise HTTPException(404, "News not found")
    return n


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
    text = data.text
    bd = data.broadcast_date
    n = News(text=text, broadcast_date=bd)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.post("/generate")
async def generate_news(
    d: date | None = Query(None, description="Дата для новой записи YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    region = get(db, "news_region") or "tajikistan"
    rss_urls = NEWS_REGIONS.get(region, NEWS_REGIONS["tajikistan"])
    items = await fetch_news_from_rss(limit=15, rss_urls=rss_urls)
    if not items:
        raise HTTPException(500, "Не удалось получить новости из RSS. Проверьте доступность источников.")
    news_texts = [f"{x['title']}. {x['summary']}" for x in items]
    try:
        text = await generate_news_text(db, news_texts)
    except ValueError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Ошибка LLM: {str(e)[:200]}")
    n = News(text=text, broadcast_date=d)
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@router.post("/{news_id}/regenerate")
async def regenerate_news(
    news_id: int,
    d: date | None = Query(None, description="Дата эфира — создаётся новая запись на этот день"),
    broadcast_item_id: int | None = Query(None, description="ID слота в эфире — обновить ссылку"),
    db: Session = Depends(get_db),
):
    """Перегенерировать: создаёт НОВУЮ запись на дату d, обновляет слот. Иначе — перезаписывает текущую."""
    region = get(db, "news_region") or "tajikistan"
    rss_urls = NEWS_REGIONS.get(region, NEWS_REGIONS["tajikistan"])
    items = await fetch_news_from_rss(limit=10, rss_urls=rss_urls)
    if not items:
        raise HTTPException(500, "Не удалось получить новости из RSS. Проверьте доступность источников.")
    news_texts = [f"{x['title']}. {x['summary']}" for x in items]
    try:
        text = await generate_news_text(db, news_texts)
    except ValueError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Ошибка LLM: {str(e)[:200]}")

    if d is not None:
        # Создаём новую запись на дату d (не трогаем старую)
        n = News(text=text, broadcast_date=d)
        db.add(n)
        db.commit()
        db.refresh(n)
        if broadcast_item_id is not None:
            slot = db.query(BroadcastItem).filter(
                BroadcastItem.id == broadcast_item_id,
                BroadcastItem.entity_type == "news",
            ).first()
            if slot:
                slot.entity_id = n.id
                db.commit()
        return n
    else:
        # Старое поведение: перезапись
        n = db.query(News).get(news_id)
        if not n:
            raise HTTPException(404, "News not found")
        n.text = text
        n.audio_path = ""
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
    path = audio_dir / f"news_{news_id}_{uuid.uuid4().hex}.mp3"
    await text_to_speech(n.text, path, voice, db=db)
    n.audio_path = str(path)
    db.commit()
    return {"audio_path": n.audio_path}


@router.post("/{news_id}/upload-tts")
async def upload_news_tts(news_id: int, file: UploadFile, db: Session = Depends(get_db)):
    n = db.query(News).get(news_id)
    if not n:
        raise HTTPException(404, "News not found")
    audio_dir = Path(settings.upload_dir) / "news"
    audio_dir.mkdir(parents=True, exist_ok=True)
    path = audio_dir / f"news_{news_id}_{uuid.uuid4().hex}.mp3"
    path.write_bytes(await file.read())
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
