from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from database import get_db
from services.streamer_service import get_playlist_with_times, stream_broadcast

from database import engine, Base, get_db
from routes import (
    admin_router,
    songs_router,
    news_router,
    weather_router,
    podcasts_router,
    intros_router,
    broadcast_router,
)
from config import settings
from services.tts_service import list_voices


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="NAVO RADIO API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/api")
app.include_router(songs_router, prefix="/api")
app.include_router(news_router, prefix="/api")
app.include_router(weather_router, prefix="/api")
app.include_router(podcasts_router, prefix="/api")
app.include_router(intros_router, prefix="/api")
app.include_router(broadcast_router, prefix="/api")


@app.get("/api/tts/voices")
async def get_tts_voices():
    return {"voices": await list_voices()}


# Serve uploaded files
uploads_path = Path(settings.upload_dir)
if uploads_path.exists():
    app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")


@app.get("/")
def root():
    return {"message": "NAVO RADIO API", "docs": "/docs"}


@app.get("/stream")
async def stream_audio(
    d: date | None = Query(None, description="Date YYYY-MM-DD, default today"),
    from_start: bool = Query(False, description="С начала дня (иначе — с текущего времени по Москве)"),
):
    """Stream broadcast as continuous MP3. Синхронизация по Москве (UTC+3)."""
    from datetime import date as dt

    broadcast_date = d or dt.today()
    db = next(get_db())
    try:
        playlist = get_playlist_with_times(db, broadcast_date)
    finally:
        db.close()
    if not playlist:
        raise HTTPException(404, "Нет эфира на эту дату. Сгенерируйте сетку в админке.")
    return StreamingResponse(
        stream_broadcast(playlist, sync_to_moscow=not from_start),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )
