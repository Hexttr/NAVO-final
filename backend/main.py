from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from database import get_db
from services.streamer_service import get_playlist_with_times, stream_broadcast, stream_broadcast_ffmpeg

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


def _run_migrations():
    """Add broadcast_date to news/weather if missing."""
    from sqlalchemy import text
    for table, col in [("news", "broadcast_date"), ("weather", "broadcast_date")]:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} DATE"))
                conn.commit()
        except Exception:
            pass  # column already exists


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="NAVO RADIO API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://navoradio.com",
        "https://www.navoradio.com",
        "http://navoradio.com",
        "http://www.navoradio.com",
    ],
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


@app.get("/stream-test")
def stream_test(
    d: date | None = Query(None, description="Date YYYY-MM-DD"),
):
    """Тест: один файл. Открой /stream-test?d=2026-02-17 — если играет, проблема в мульти-стриме."""
    from services.streamer_service import moscow_date

    broadcast_date = d or moscow_date()
    db = next(get_db())
    try:
        playlist = get_playlist_with_times(db, broadcast_date)
    finally:
        db.close()
    if not playlist:
        raise HTTPException(404, "Нет эфира")
    path = playlist[0][0]
    if not path.exists():
        raise HTTPException(404, f"Файл не найден: {path}")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/stream")
async def stream_audio(
    d: date | None = Query(None, description="Date YYYY-MM-DD, default today"),
    from_start: bool = Query(False, description="С начала дня (иначе — с текущего времени по Москве)"),
):
    """Stream broadcast as continuous MP3. FFmpeg subprocess — надёжный chunked encoding. Синхронизация по Москве (UTC+3)."""
    import shutil

    from services.streamer_service import moscow_date

    if not shutil.which("ffmpeg"):
        raise HTTPException(503, "FFmpeg не установлен. Установите: https://ffmpeg.org/download.html")
    broadcast_date = d or moscow_date()
    db = next(get_db())
    try:
        playlist = get_playlist_with_times(db, broadcast_date)
    finally:
        db.close()
    if not playlist:
        raise HTTPException(404, "Нет эфира на эту дату. Сгенерируйте сетку в админке.")
    return StreamingResponse(
        stream_broadcast_ffmpeg(playlist, sync_to_moscow=not from_start),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Accept-Ranges": "none",
        },
    )
