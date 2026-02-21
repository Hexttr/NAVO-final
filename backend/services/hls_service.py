"""
HLS generation for broadcast. Concat + re-encode → segments.
Единый формат, без обрезки треков, совпадение с расписанием.
Генерирует metadata.json — привязка «Сейчас играет» к реальной позиции в потоке.
"""
import json
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from config import settings
from services.streamer_service import (
    get_playlist_with_times,
    get_broadcast_schedule_hash,
    _create_concat_file,
)
from services.broadcast_service import get_entity_meta
from models import BroadcastItem


from utils.time_utils import parse_time

HLS_DIR = "hls"
HLS_SEGMENT_DURATION = 10  # секунд на сегмент

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _inject_daterange_into_m3u8(m3u8_path: Path, tracks: list[dict], broadcast_date: date) -> None:
    """
    Вставляет #EXT-X-DATERANGE с X-TITLE перед сегментами, где начинаются треки.
    hls.js мапит DATERANGE в TextTrack cues — фронт слушает cuechange.
    """
    import re
    text = m3u8_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out = []
    cum_sec = 0.0
    track_idx = 0
    for line in lines:
        m = re.match(r"#EXTINF:([\d.]+)", line)
        if m:
            dur = float(m.group(1))
            # Треки, чей start попадает в этот сегмент [cum_sec, cum_sec+dur)
            while track_idx < len(tracks) and cum_sec <= tracks[track_idx]["start"] < cum_sec + dur:
                t = tracks[track_idx]
                title = (t.get("title") or "—").replace('"', "'").replace("\\", "/")
                h, m_, s = int(t["start"] // 3600), int((t["start"] % 3600) // 60), int(t["start"] % 60)
                iso = f"{broadcast_date}T{h:02d}:{m_:02d}:{s:02d}Z"
                out.append(f'#EXT-X-DATERANGE:ID="track-{track_idx}",START-DATE="{iso}",CLASS="song",X-TITLE="{title}"')
                track_idx += 1
            cum_sec += dur
        out.append(line)
    m3u8_path.write_text("\n".join(out), encoding="utf-8")


def _get_hls_dir() -> Path:
    """Базовая директория для HLS (uploads/hls)."""
    return PROJECT_ROOT / settings.upload_dir / HLS_DIR


def get_hls_path(broadcast_date: date, schedule_hash: str) -> Path:
    """Путь к директории HLS для даты и версии расписания."""
    return _get_hls_dir() / str(broadcast_date) / schedule_hash


def get_hls_stream_duration_sec(m3u8_path: Path) -> float | None:
    """Сумма длительностей сегментов из m3u8. None если не удалось прочитать."""
    import re
    try:
        text = m3u8_path.read_text(encoding="utf-8")
        total = 0.0
        for m in re.finditer(r"#EXTINF:([\d.]+)", text):
            total += float(m.group(1))
        return total if total > 0 else None
    except (OSError, ValueError):
        return None


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
    concat_path = _create_concat_file(playlist, out_dir=out_dir)
    if not concat_path or not concat_path.exists():
        return {"ok": False, "error": "Не удалось создать concat (нет файлов)"}

    bitrate = getattr(settings, "stream_bitrate", "256k") or "256k"
    # libmp3lame может вызывать проблемы с hls.js (воспроизведение без звука), используем aac
    args = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-f", "concat", "-safe", "0", "-i", str(concat_path),
        "-c:a", "aac", "-b:a", bitrate, "-ar", "44100", "-ac", "2",
        "-f", "hls", "-hls_time", str(HLS_SEGMENT_DURATION),
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", segment_pattern,
        str(m3u8_path),
    ]

    # 877 слотов × ~100 сек ≈ 24 ч. FFmpeg ~20–40× быстрее → 40–70 мин. Таймаут 2 ч.
    HLS_TIMEOUT = 7200
    _log(f"Running ffmpeg (40–70 мин для суток, timeout={HLS_TIMEOUT//60} мин)...")
    try:
        r = subprocess.run(args, capture_output=True, timeout=HLS_TIMEOUT, check=False)
        if r.returncode != 0:
            err = (r.stderr or b"").decode(errors="replace")[-1000:]
            return {"ok": False, "error": f"FFmpeg: {err}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Таймаут генерации (>{HLS_TIMEOUT//60} мин)"}
    except FileNotFoundError:
        return {"ok": False, "error": "FFmpeg не найден"}
    finally:
        try:
            concat_path.unlink(missing_ok=True)
        except OSError:
            pass

    if not m3u8_path.exists():
        return {"ok": False, "error": "m3u8 не создан"}

    # metadata.json — привязка позиции в потоке к названию (для «Сейчас играет»)
    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == broadcast_date,
            BroadcastItem.entity_type != "empty",
        )
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    tracks = []
    for it in items:
        start_sec = parse_time(it.start_time or "00:00:00")
        dur = float(it.duration_seconds or 0)
        end_sec = start_sec + dur
        title = None
        if it.metadata_json:
            try:
                meta = json.loads(it.metadata_json)
                title = meta.get("title", "")
            except (json.JSONDecodeError, TypeError):
                pass
        if not title:
            title = get_entity_meta(db, it.entity_type, it.entity_id)
        tracks.append({"start": start_sec, "end": end_sec, "title": title or "—"})
    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps({"tracks": tracks}, ensure_ascii=False, indent=0), encoding="utf-8")

    # EXT-X-DATERANGE в m3u8 — timed metadata для «Сейчас играет» (hls.js → TextTrack → cuechange)
    _inject_daterange_into_m3u8(m3u8_path, tracks, broadcast_date)

    # URL для фронта (относительный, nginx раздаёт /hls/)
    url = f"/hls/{broadcast_date}/{schedule_hash}/stream.m3u8"
    return {"ok": True, "url": url, "schedule_hash": schedule_hash}


def get_playlist_metadata(db: Session, broadcast_date: date) -> dict:
    """
    Возвращает {tracks: [{start, end, title}]} для «Сейчас играет».
    Источник истины — БД. Fallback когда metadata.json 404 (старый HLS или nginx).
    """
    from services.broadcast_service import get_entity_meta

    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == broadcast_date,
            BroadcastItem.entity_type != "empty",
        )
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    tracks = []
    for it in items:
        start_sec = parse_time(it.start_time or "00:00:00")
        dur = float(it.duration_seconds or 0)
        end_sec = start_sec + dur
        title = None
        if it.metadata_json:
            try:
                meta = json.loads(it.metadata_json)
                title = meta.get("title", "")
            except (json.JSONDecodeError, TypeError):
                pass
        if not title:
            title = get_entity_meta(db, it.entity_type, it.entity_id)
        tracks.append({"start": start_sec, "end": end_sec, "title": title or "—"})
    return {"tracks": tracks}


def get_hls_url(db: Session, broadcast_date: date) -> str | None:
    """
    Возвращает URL HLS если готов, иначе None.
    1) Точное совпадение: HLS для даты и хеша расписания.
    2) Fallback: расписание на дату изменилось, но есть HLS от прошлой генерации.
    3) Копия эфира: дата без HLS, но эфир скопирован — отдаём HLS от источника (вчера и т.д.).
    """
    playlist = get_playlist_with_times(db, broadcast_date)
    if not playlist:
        return None

    schedule_hash = get_broadcast_schedule_hash(db, broadcast_date)
    m3u8_path = get_hls_path(broadcast_date, schedule_hash) / "stream.m3u8"
    if m3u8_path.exists():
        return f"/hls/{broadcast_date}/{schedule_hash}/stream.m3u8"

    # Fallback 1: расписание изменилось, но есть HLS от предыдущей генерации для этой даты
    date_dir = _get_hls_dir() / str(broadcast_date)
    if date_dir.exists():
        best_url, best_mtime = None, 0
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
        if best_url:
            return best_url

    # Fallback 2: эфир скопирован с другой даты — ищем HLS у источника (до 7 дней назад)
    for days_back in range(1, 8):
        src_date = broadcast_date - timedelta(days=days_back)
        src_hash = get_broadcast_schedule_hash(db, src_date)
        if src_hash != schedule_hash:
            continue
        src_m3u8 = get_hls_path(src_date, src_hash) / "stream.m3u8"
        if src_m3u8.exists():
            return f"/hls/{src_date}/{src_hash}/stream.m3u8"
    return None
