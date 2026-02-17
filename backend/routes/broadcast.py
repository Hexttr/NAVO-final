from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import BroadcastItem, Song, News, Weather, Podcast, Intro
from services.broadcast_generator import generate_broadcast

router = APIRouter(prefix="/broadcast", tags=["broadcast"])


class BroadcastItemSwap(BaseModel):
    from_index: int
    to_index: int


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
    return {"date": str(d), "items": items}


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
    db.commit()
    return {"ok": True}


@router.get("/stream-url")
def get_stream_url():
    """Return Icecast stream URL for frontend player."""
    return {"url": "http://localhost:8000/stream"}  # TODO: configure Icecast URL
