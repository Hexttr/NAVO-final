from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from database import get_db
from services.streamer_service import get_playlist_with_times, ensure_broadcast_for_date, stream_broadcast_ffmpeg_concat
from services.stream_position import write_stream_position

from database import engine, Base, get_db
from routes import (
    admin_router,
    songs_router,
    news_router,
    weather_router,
    podcasts_router,
    intros_router,
    broadcast_router,
    settings_router,
)
from config import settings
from services.tts_service import list_voices


def _run_migrations():
    """Add broadcast_date and duration_seconds to news/weather if missing."""
    from sqlalchemy import text
    migrations = [
        ("news", "broadcast_date", "DATE"),
        ("weather", "broadcast_date", "DATE"),
        ("news", "duration_seconds", "REAL"),
        ("weather", "duration_seconds", "REAL"),
    ]
    for table, col, col_type in migrations:
        try:
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
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
app.include_router(settings_router, prefix="/api")


@app.get("/api/tts/voices")
async def get_tts_voices(db = Depends(get_db)):
    return {"voices": await list_voices(db)}


# Serve uploaded files
uploads_path = Path(settings.upload_dir)
if uploads_path.exists():
    app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")


@app.get("/")
def root():
    return {"message": "NAVO RADIO API", "docs": "/docs"}


@app.get("/api/diagnostics")
def diagnostics(db=Depends(get_db)):
    """Диагностика: статус БД, эфир, HLS, stream, Icecast. Для отладки проблем воспроизведения."""
    from datetime import datetime, timezone
    from urllib.request import urlopen
    from urllib.error import URLError, HTTPError

    from services.streamer_service import moscow_date, get_playlist_with_times, ensure_broadcast_for_date
    from services.hls_service import get_hls_url

    result = {"ok": True, "ts": datetime.now(timezone.utc).isoformat(), "checks": {}}
    try:
        today = moscow_date()
        result["moscow_date"] = str(today)

        # ensure broadcast for today (copy if needed)
        try:
            copied = ensure_broadcast_for_date(db, today)
            result["checks"]["broadcast_copied"] = copied
        except Exception as e:
            result["checks"]["broadcast_ensure"] = f"ERROR: {e}"
            result["ok"] = False

        # broadcast items count
        try:
            playlist = get_playlist_with_times(db, today)
            result["checks"]["broadcast_items"] = len(playlist) if playlist else 0
            result["checks"]["broadcast_ready"] = bool(playlist and len(playlist) > 0)
            if not playlist or len(playlist) == 0:
                result["ok"] = False
        except Exception as e:
            result["checks"]["broadcast_playlist"] = f"ERROR: {e}"
            result["ok"] = False

        # HLS
        try:
            hls_url = get_hls_url(db, today)
            result["checks"]["hls_ready"] = bool(hls_url)
            result["checks"]["hls_url"] = hls_url
        except Exception as e:
            result["checks"]["hls"] = f"ERROR: {e}"
            result["ok"] = False

        # stream would work if we have playlist
        result["checks"]["stream_ready"] = result["checks"].get("broadcast_ready", False)

        # Icecast (backend runs on same host)
        try:
            with urlopen("http://127.0.0.1:8001/live", timeout=3) as r:
                result["checks"]["icecast_live"] = r.status
        except HTTPError as e:
            result["checks"]["icecast_live"] = e.code
        except (URLError, OSError) as e:
            result["checks"]["icecast_live"] = f"unreachable: {type(e).__name__}"

    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
    finally:
        db.close()
    return result


@app.get("/api/playback-hint")
def playback_hint():
    """Подсказка для плеера: использовать /stream напрямую, если Icecast не работает (404)."""
    from urllib.request import urlopen, Request
    from urllib.error import URLError, HTTPError

    try:
        req = Request("http://127.0.0.1:8001/live", method="HEAD")
        with urlopen(req, timeout=2) as r:
            return {"preferStream": False, "icecast": r.status}
    except HTTPError as e:
        return {"preferStream": True, "icecast": e.code}
    except (URLError, OSError):
        return {"preferStream": True, "icecast": "unreachable"}


@app.get("/stream-test")
def stream_test(
    d: date | None = Query(None, description="Date YYYY-MM-DD"),
    db=Depends(get_db),
):
    """Тест: один файл. Открой /stream-test?d=2026-02-17 — если играет, проблема в мульти-стриме."""
    from services.streamer_service import moscow_date

    req_date = d or moscow_date()
    ensure_broadcast_for_date(db, req_date)
    playlist = get_playlist_with_times(db, req_date)
    if not playlist:
        raise HTTPException(404, "Нет эфира")
    path = playlist[0][0]
    if path is None or not path.exists():
        raise HTTPException(404, f"Файл не найден: {path}")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/stream")
async def stream_audio(
    d: date | None = Query(None, description="Date YYYY-MM-DD, default today"),
    from_start: bool = Query(False, description="С начала дня (иначе — с текущего времени по Москве)"),
    db=Depends(get_db),
):
    """Stream broadcast as continuous MP3. FFmpeg subprocess — надёжный chunked encoding. Синхронизация по Москве (UTC+3)."""
    import shutil

    from services.streamer_service import moscow_date

    if not shutil.which("ffmpeg"):
        raise HTTPException(503, "FFmpeg не установлен. Установите: https://ffmpeg.org/download.html")
    req_date = d or moscow_date()
    ensure_broadcast_for_date(db, req_date)
    playlist = get_playlist_with_times(db, req_date)
    if not playlist:
        raise HTTPException(404, "Нет эфира на эту дату. Сгенерируйте сетку в админке.")
    return StreamingResponse(
        stream_broadcast_ffmpeg_concat(playlist, sync_to_moscow=not from_start, on_position=write_stream_position),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Accept-Ranges": "none",
        },
    )
