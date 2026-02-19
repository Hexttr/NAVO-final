from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from database import get_db
from services.settings_service import get_all, update_batch

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """All editable settings for admin panel."""
    return get_all(db)


@router.put("")
def put_settings(data: dict = Body(...), db: Session = Depends(get_db)):
    """Update settings. Pass {key: value} for each key to change."""
    return update_batch(db, data)
