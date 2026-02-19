"""
HLS generation for broadcast. Concat + re-encode → segments.
Единый формат, без обрезки треков, совпадение с расписанием.
"""
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from config import settings
from services.streamer_service import (
    get_playlist_with_times,
    get_broadcast_schedule_hash,
    _create_concat_file,
)


HLS_DIR = "hls"
HLS_SEGMENT_DURATION = 10  # секунд на сегмент


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_hls_dir() -> Path:
    """Базовая директория для HLS (uploads/hls)."""
    return PROJECT_ROOT / settings.upload_dir / HLS_DIR


def get_hls_path(broadcast_date: date, schedule_hash: str) -> Path:
    """Путь к директории HLS для даты и версии расписания."""
    return _get_hls_dir() / str(broadcast_date) / schedule_hash


def generate_hls(db: Session, broadcast_date: date) -> dict:
    """
    Генерирует HLS для даты. Возвращает {ok, url, error, duration_sec}.
    Запускается в фоне — может занять 10-30 мин для суток эфира.
    """
    import sys
    _log = lambda msg: (print(f"[hls] {msg}", flush=True) or sys.stdout.flush())
    _log(f"generate_hls start: {broadcast_date}")

    playlist = get_playlist_with_times(db, broadcast_date)
    if not playlist:
        return {"ok": False, "error": "Нет эфира на дату"}

    schedule_hash = get_broadcast_schedule_hash(db, broadcast_date)
    out_dir = get_hls_path(broadcast_date, schedule_hash)
    _log(f"mkdir {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    m3u8_path = out_dir / "stream.m3u8"
    segment_pattern = str(out_dir / "seg_%04d.ts")

    _log(f"Creating concat for {len(playlist)} items (may take a few min)...")
    concat_path = _create_concat_file(playlist)
    if not concat_path or not concat_path.exists():
        return {"ok": False, "error": "Не удалось создать concat (нет файлов)"}

    bitrate = getattr(settings, "stream_bitrate", "256k") or "256k"
    # libmp3lame — всегда доступен; AAC может отсутствовать в минимальных сборках
    args = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-f", "concat", "-safe", "0", "-i", str(concat_path),
        "-c:a", "libmp3lame", "-b:a", bitrate, "-ar", "44100", "-ac", "2",
        "-f", "hls", "-hls_time", str(HLS_SEGMENT_DURATION),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", segment_pattern,
        str(m3u8_path),
    ]

    _log("Running ffmpeg (10-30 min for full day)...")
    try:
        r = subprocess.run(args, capture_output=True, timeout=3600, check=False)
        if r.returncode != 0:
            err = (r.stderr or b"").decode(errors="replace")[-1000:]
            return {"ok": False, "error": f"FFmpeg: {err}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Таймаут генерации (>1ч)"}
    except FileNotFoundError:
        return {"ok": False, "error": "FFmpeg не найден"}
    finally:
        try:
            concat_path.unlink(missing_ok=True)
        except OSError:
            pass

    if not m3u8_path.exists():
        return {"ok": False, "error": "m3u8 не создан"}

    # URL для фронта (относительный, nginx раздаёт /hls/)
    url = f"/hls/{broadcast_date}/{schedule_hash}/stream.m3u8"
    return {"ok": True, "url": url, "schedule_hash": schedule_hash}


def get_hls_url(db: Session, broadcast_date: date) -> str | None:
    """
    Возвращает URL HLS если готов, иначе None.
    Сначала проверяет точное совпадение с текущим расписанием;
    если расписание изменилось — возвращает любой доступный HLS для даты (fallback).
    """
    playlist = get_playlist_with_times(db, broadcast_date)
    if not playlist:
        return None

    schedule_hash = get_broadcast_schedule_hash(db, broadcast_date)
    m3u8_path = get_hls_path(broadcast_date, schedule_hash) / "stream.m3u8"
    if m3u8_path.exists():
        return f"/hls/{broadcast_date}/{schedule_hash}/stream.m3u8"

    # Fallback: расписание изменилось, но есть HLS от предыдущей генерации
    date_dir = _get_hls_dir() / str(broadcast_date)
    if not date_dir.exists():
        return None
    best_url = None
    best_mtime = 0
    for subdir in date_dir.iterdir():
        if subdir.is_dir():
            m3u8 = subdir / "stream.m3u8"
            if m3u8.exists():
                try:
                    mtime = m3u8.stat().st_mtime
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best_url = f"/hls/{broadcast_date}/{subdir.name}/stream.m3u8"
                except OSError:
                    pass
    return best_url
