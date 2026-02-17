import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import BroadcastItem
from services.broadcast_generator import generate_broadcast
from services.broadcast_service import recalc_times, get_entity_duration, get_entity_meta

router = APIRouter(prefix="/broadcast", tags=["broadcast"])


class BroadcastItemSwap(BaseModel):
    from_index: int
    to_index: int


class InsertEntity(BaseModel):
    entity_type: str
    entity_id: int


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
