from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import Song, News, Weather, Podcast, Intro

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Dashboard counters for all entities."""
    return {
        "songs": db.query(Song).count(),
        "news": db.query(News).count(),
        "weather": db.query(Weather).count(),
        "podcasts": db.query(Podcast).count(),
        "intros": db.query(Intro).count(),
    }
