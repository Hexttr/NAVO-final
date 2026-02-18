import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import BroadcastItem, Song, News, Weather
from services.broadcast_generator import generate_broadcast
from services.broadcast_service import recalc_times, get_entity_duration, get_entity_meta
from config import settings

router = APIRouter(prefix="/broadcast", tags=["broadcast"])


class BroadcastItemSwap(BaseModel):
    from_index: int
    to_index: int


class InsertEntity(BaseModel):
    entity_type: str
    entity_id: int


@router.get("/playlist-urls")
def get_playlist_urls(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    sync: bool = Query(True, description="Синхронизация по Москве"),
    db: Session = Depends(get_db),
):
    """Плейлист для последовательного воспроизведения на фронте. Возвращает {items, startIndex}."""
    from datetime import datetime, timezone, timedelta

    # Относительные URL — браузер использует тот же протокол, что и страница (HTTPS)
    base = "/api"

    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == d,
            BroadcastItem.entity_type != "empty",
        )
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    result = []
    for it in items:
        rec = {"url": "", "type": it.entity_type, "entity_id": it.entity_id}
        if it.entity_type == "song":
            rec["url"] = f"{base}/songs/{it.entity_id}/audio"
        elif it.entity_type == "dj":
            rec["url"] = f"{base}/songs/{it.entity_id}/dj-audio"
        elif it.entity_type == "news":
            rec["url"] = f"{base}/news/{it.entity_id}/audio"
        elif it.entity_type == "weather":
            rec["url"] = f"{base}/weather/{it.entity_id}/audio"
        elif it.entity_type == "podcast":
            rec["url"] = f"{base}/podcasts/{it.entity_id}/audio"
        elif it.entity_type == "intro":
            rec["url"] = f"{base}/intros/{it.entity_id}/audio"
        if rec["url"]:
            result.append(rec)
    start_index = 0
    if sync and result:
        now = datetime.now(timezone(timedelta(hours=3)))
        now_sec = now.hour * 3600 + now.minute * 60 + now.second
        for i, it in enumerate(items):
            parts = (it.start_time or "00:00:00").split(":")
            start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if len(parts) == 3 else 0
            end_sec = start_sec + int(it.duration_seconds or 0)
            if start_sec <= now_sec < end_sec:
                start_index = i
                break
            if now_sec < start_sec:
                start_index = i
                break
    return {"date": str(d), "items": result, "startIndex": start_index}


@router.get("/now-playing")
def get_now_playing(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Текущий трек по расписанию (Москва UTC+3). Для подсветки в сетке эфира."""
    from datetime import datetime, timezone, timedelta

    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == d,
            BroadcastItem.entity_type != "empty",
        )
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    if not items:
        return {"entityType": None, "entityId": None}
    now = datetime.now(timezone(timedelta(hours=3)))
    now_sec = now.hour * 3600 + now.minute * 60 + now.second
    for it in items:
        parts = (it.start_time or "00:00:00").split(":")
        start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if len(parts) == 3 else 0
        end_sec = start_sec + int(it.duration_seconds or 0)
        if start_sec <= now_sec < end_sec:
            return {"entityType": it.entity_type, "entityId": it.entity_id}
    return {"entityType": None, "entityId": None}


def _get_entity_text(db: Session, entity_type: str, entity_id: int) -> str | None:
    """Текст для DJ, новостей, погоды."""
    if entity_type == "dj":
        s = db.query(Song).filter(Song.id == entity_id).first()
        return s.dj_text if s else None
    if entity_type == "news":
        n = db.query(News).filter(News.id == entity_id).first()
        return n.text if n else None
    if entity_type == "weather":
        w = db.query(Weather).filter(Weather.id == entity_id).first()
        return w.text if w else None
    return None


@router.get("")
def get_broadcast(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    items = (
        db.query(BroadcastItem)
        .filter(BroadcastItem.broadcast_date == d)
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    result = []
    for it in items:
        rec = {
            "id": it.id,
            "entity_type": it.entity_type,
            "entity_id": it.entity_id,
            "start_time": it.start_time,
            "end_time": it.end_time,
            "duration_seconds": it.duration_seconds,
            "sort_order": it.sort_order,
            "metadata_json": it.metadata_json,
        }
        if it.entity_type in ("dj", "news", "weather"):
            rec["text"] = _get_entity_text(db, it.entity_type, it.entity_id) or ""
        else:
            rec["text"] = None
        result.append(rec)
    return {"date": str(d), "items": result}


@router.delete("")
def delete_broadcast(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Удалить весь эфир на дату."""
    deleted = db.query(BroadcastItem).filter(BroadcastItem.broadcast_date == d).delete()
    db.commit()
    return {"date": str(d), "deleted": deleted, "message": "Эфир удалён"}


@router.post("/generate")
def generate(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    try:
        items = generate_broadcast(db, d)
        for item in items:
            db.add(item)
        db.commit()
        return {"date": str(d), "count": len(items), "message": "Эфир сгенерирован"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/swap")
def swap_items(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    from_index: int = Query(...),
    to_index: int = Query(...),
    db: Session = Depends(get_db),
):
    items = (
        db.query(BroadcastItem)
        .filter(BroadcastItem.broadcast_date == d)
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    if not 0 <= from_index < len(items) or not 0 <= to_index < len(items):
        raise HTTPException(400, "Invalid indices")
    items[from_index].sort_order, items[to_index].sort_order = to_index, from_index
    for i, it in enumerate(items):
        it.sort_order = i
    recalc_times(db, d, items)
    db.commit()
    return {"ok": True}


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Replace item with empty slot (keeps position)."""
    item = db.query(BroadcastItem).filter(
        BroadcastItem.id == item_id,
        BroadcastItem.broadcast_date == d,
    ).first()
    if not item:
        raise HTTPException(404, "Item not found")
    item.entity_type = "empty"
    item.entity_id = 0
    item.duration_seconds = 0
    item.metadata_json = '{"title":"—"}'
    items = db.query(BroadcastItem).filter(BroadcastItem.broadcast_date == d).order_by(BroadcastItem.sort_order).all()
    recalc_times(db, d, items)
    db.commit()
    return {"ok": True}


@router.post("/items/{item_id}/insert")
def insert_into_slot(
    item_id: int,
    body: InsertEntity,
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Replace empty slot with entity."""
    item = db.query(BroadcastItem).filter(
        BroadcastItem.id == item_id,
        BroadcastItem.broadcast_date == d,
    ).first()
    if not item:
        raise HTTPException(404, "Item not found")
    if item.entity_type != "empty":
        raise HTTPException(400, "Slot is not empty")
    try:
        dur = get_entity_duration(db, body.entity_type, body.entity_id)
        meta = get_entity_meta(db, body.entity_type, body.entity_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    item.entity_type = body.entity_type
    item.entity_id = body.entity_id
    item.duration_seconds = dur
    item.metadata_json = json.dumps({"title": (meta or "—")[:200]})
    items = db.query(BroadcastItem).filter(BroadcastItem.broadcast_date == d).order_by(BroadcastItem.sort_order).all()
    recalc_times(db, d, items)
    db.commit()
    return {"ok": True}


@router.post("/move")
def move_item(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    from_index: int = Query(...),
    to_index: int = Query(...),
    db: Session = Depends(get_db),
):
    """Move item from from_index to to_index (for drag&drop)."""
    items = (
        db.query(BroadcastItem)
        .filter(BroadcastItem.broadcast_date == d)
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    if not 0 <= from_index < len(items) or not 0 <= to_index < len(items):
        raise HTTPException(400, "Invalid indices")
    if from_index == to_index:
        return {"ok": True}
    moved = items.pop(from_index)
    items.insert(to_index, moved)
    for i, it in enumerate(items):
        it.sort_order = i
    recalc_times(db, d, items)
    db.commit()
    return {"ok": True}


@router.get("/stream-url")
def get_stream_url():
    """Return Icecast stream URL for frontend player."""
    return {"url": "http://localhost:8000/stream"}  # TODO: configure Icecast URL
