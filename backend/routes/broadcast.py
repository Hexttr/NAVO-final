import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import BroadcastItem, Song, News, Weather
from services.broadcast_generator import generate_broadcast
from services.broadcast_service import recalc_times, get_entity_duration, get_entity_meta
from services.streamer_service import get_entity_duration_from_file, get_playlist_with_times, ensure_broadcast_for_date
from services.hls_service import generate_hls, get_hls_url
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
    """Плейлист для последовательного воспроизведения на фронте. Возвращает {items, startIndex}. Если на дату нет эфира — копируется с последнего дня."""
    from datetime import datetime, timezone, timedelta

    ensure_broadcast_for_date(db, d)
    broadcast_date = d
    # Относительные URL — браузер использует тот же протокол, что и страница (HTTPS)
    base = "/api"

    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == broadcast_date,
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
    return {"date": str(broadcast_date), "items": result, "startIndex": start_index}


@router.get("/debug-time")
def debug_time(
    d: date | None = Query(None, description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Отладка: время сервера и текущий элемент. Сервер должен быть в Europe/Moscow."""
    from datetime import datetime, timezone, timedelta

    MOSCOW_TZ = timezone(timedelta(hours=3))
    now = datetime.now(MOSCOW_TZ)
    now_sec = now.hour * 3600 + now.minute * 60 + now.second
    broadcast_date = d or now.date()
    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == broadcast_date,
            BroadcastItem.entity_type != "empty",
        )
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    current = None
    for it in items:
        parts = (it.start_time or "00:00:00").split(":")
        start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if len(parts) == 3 else 0
        end_sec = start_sec + int(it.duration_seconds or 0)
        if start_sec <= now_sec < end_sec:
            current = {"entity_type": it.entity_type, "entity_id": it.entity_id, "start_time": it.start_time}
            break
    return {
        "server_time": now.strftime("%H:%M:%S"),
        "server_date": str(broadcast_date),
        "now_sec": now_sec,
        "current_item": current,
        "items_count": len(items),
    }


@router.get("/now-playing")
def get_now_playing(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Текущий трек по расписанию (Москва UTC+3). Возвращает title для отображения «Сейчас играет». Если на дату нет эфира — копируется с последнего дня."""
    from datetime import datetime, timezone, timedelta
    from fastapi.responses import JSONResponse
    import json

    ensure_broadcast_for_date(db, d)
    broadcast_date = d
    MOSCOW_TZ = timezone(timedelta(hours=3))
    now = datetime.now(MOSCOW_TZ)
    now_sec = now.hour * 3600 + now.minute * 60 + now.second
    current_time = now.strftime("%H:%M:%S")

    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == broadcast_date,
            BroadcastItem.entity_type != "empty",
        )
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    empty = {"entityType": None, "entityId": None, "currentTime": current_time, "title": None}
    if not items:
        return JSONResponse(content=empty, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})
    for it in items:
        parts = (it.start_time or "00:00:00").split(":")
        start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if len(parts) == 3 else 0
        end_sec = start_sec + int(it.duration_seconds or 0)
        if start_sec <= now_sec < end_sec:
            title = None
            if it.metadata_json:
                try:
                    meta = json.loads(it.metadata_json)
                    title = meta.get("title", "")
                except (json.JSONDecodeError, TypeError):
                    pass
            if not title:
                title = get_entity_meta(db, it.entity_type, it.entity_id)
            return JSONResponse(
                content={
                    "entityType": it.entity_type,
                    "entityId": it.entity_id,
                    "currentTime": current_time,
                    "title": title or "—",
                },
                headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
            )
    return JSONResponse(content=empty, headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})


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


@router.post("/recalc-durations")
def recalc_all_durations(db: Session = Depends(get_db)):
    """Пересчитать длительность всех аудио из файлов (ffprobe). Обновляет сущности и BroadcastItem — точное совпадение админки и эфира."""
    from services.broadcast_service import recalc_all_durations as recalc_svc

    updated = recalc_svc(db)
    total = sum(updated.values())
    return {"updated": updated, "total": total, "message": f"Обновлено: {updated['songs']} песен, {updated['podcasts']} подкастов, {updated['intros']} интро, {updated['news']} новостей, {updated['weather']} погод, {updated['broadcast_items']} слотов эфира"}


@router.post("/generate")
def generate(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    for attempt in range(5):
        try:
            db.rollback()
            items = generate_broadcast(db, d)
            for item in items:
                db.add(item)
            db.commit()
            _spawn_hls_generation(d)
            return {"date": str(d), "count": len(items), "message": "Эфир сгенерирован. HLS генерируется в фоне (~10-30 мин)."}
        except ValueError as e:
            db.rollback()
            raise HTTPException(400, str(e))
        except sqlalchemy.exc.OperationalError as e:
            db.rollback()
            if "locked" in str(e).lower() and attempt < 4:
                time.sleep(2 * (attempt + 1))
                continue
            raise HTTPException(
                503 if "locked" in str(e).lower() else 500,
                "База занята (Icecast/HLS). Подождите 10–20 сек и повторите." if "locked" in str(e).lower() else str(e),
            )
        except Exception as e:
            db.rollback()
            import traceback
            traceback.print_exc()
            raise HTTPException(500, str(e))


def _spawn_hls_generation(d: date) -> int | None:
    """Запускает генерацию HLS в отдельном процессе. Возвращает PID или None при ошибке."""
    try:
        backend_dir = Path(__file__).resolve().parent.parent
        project_root = backend_dir.parent
        run_script = backend_dir / "run_hls.py"
        log_path = project_root / "uploads" / "hls_generation.log"
        if not run_script.exists():
            return None
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"\n=== HLS {d} (from schedule change) ===\n")
        log_file.flush()
        proc = subprocess.Popen(
            [sys.executable, str(run_script), str(d)],
            cwd=str(backend_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env={**os.environ},
            start_new_session=True,
        )
        log_file.write(f"PID: {proc.pid}\n")
        log_file.flush()
        log_file.close()
        return proc.pid
    except Exception:
        return None


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
    _spawn_hls_generation(d)
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
    _spawn_hls_generation(d)
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
    _spawn_hls_generation(d)
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
    _spawn_hls_generation(d)
    return {"ok": True}


@router.get("/stream-url")
def get_stream_url():
    """Return Icecast stream URL for frontend player."""
    return {"url": "http://localhost:8000/stream"}  # TODO: configure Icecast URL


@router.get("/hls-url")
def hls_url(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """URL HLS если готов, иначе null. startPosition — секунды от полуночи МСК для seek (всегда по серверу)."""
    from datetime import datetime, timezone, timedelta

    ensure_broadcast_for_date(db, d)
    url = get_hls_url(db, d)
    now = datetime.now(timezone(timedelta(hours=3)))
    start_position = now.hour * 3600 + now.minute * 60 + now.second
    return {"url": url, "hasHls": url is not None, "startPosition": start_position}


@router.get("/hls-status")
def hls_status(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Статус HLS. hasHls=true если есть любой доступный HLS (как get_hls_url, с fallback)."""
    from services.streamer_service import get_broadcast_schedule_hash
    from services.hls_service import get_hls_path, get_hls_url

    ensure_broadcast_for_date(db, d)
    playlist = get_playlist_with_times(db, d)
    if not playlist:
        return {"ok": False, "error": "Нет эфира на дату", "hasHls": False}

    url = get_hls_url(db, d)
    schedule_hash = get_broadcast_schedule_hash(db, d)
    out_dir = get_hls_path(d, schedule_hash)
    m3u8_path = out_dir / "stream.m3u8"
    date_dir = out_dir.parent
    existing_hashes = []
    if date_dir.exists():
        existing_hashes = [p.name for p in date_dir.iterdir() if p.is_dir() and (p / "stream.m3u8").exists()]

    return {
        "ok": True,
        "hasHls": url is not None,
        "url": url,
        "schedule_hash": schedule_hash,
        "m3u8_path": str(m3u8_path),
        "exact_ready": m3u8_path.exists(),
        "out_dir_exists": out_dir.exists(),
        "playlist_count": len(playlist),
        "existing_hashes": existing_hashes,
    }


@router.get("/hls-log")
def get_hls_log(lines: int = Query(200, description="Last N lines")):
    """Последние строки лога генерации HLS (для отладки)."""
    project_root = Path(__file__).resolve().parent.parent.parent
    log_path = project_root / "uploads" / "hls_generation.log"
    if not log_path.exists():
        return {"ok": True, "log": "(лог пуст или не создан)", "path": str(log_path)}
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        last = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {"ok": True, "log": "".join(last), "path": str(log_path), "total_lines": len(all_lines)}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(log_path)}


@router.post("/generate-hls")
def trigger_generate_hls(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Запустить генерацию HLS в отдельном процессе. 10-30 мин для суток эфира (857 треков)."""
    try:
        playlist = get_playlist_with_times(db, d)
        if not playlist:
            raise HTTPException(404, "Нет эфира на дату. Сгенерируйте сетку.")

        backend_dir = Path(__file__).resolve().parent.parent
        project_root = backend_dir.parent
        python_exe = Path(sys.executable)
        run_script = backend_dir / "run_hls.py"
        log_path = project_root / "uploads" / "hls_generation.log"

        if not run_script.exists():
            raise HTTPException(500, "run_hls.py не найден")

        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"\n=== HLS {d} started [code: concat-fix] (PID will follow) ===\n")
        log_file.flush()

        proc = subprocess.Popen(
            [str(python_exe), str(run_script), str(d)],
            cwd=str(backend_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env={**os.environ},
            start_new_session=True,
        )
        log_file.write(f"PID: {proc.pid}\n")
        log_file.flush()
        log_file.close()
        return {
            "ok": True,
            "message": f"Генерация HLS запущена (PID {proc.pid}). ~10-30 мин для {len(playlist)} треков. Лог: uploads/hls_generation.log",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/debug-concat")
def debug_concat(
    d: date | None = Query(None, description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Отладка ffmpeg_concat: создаёт concat, запускает ffmpeg на 3 сек, возвращает результат.
    Помогает понять, почему стрим не стартует (404).
    """
    from pathlib import Path
    from services.streamer_service import (
        get_playlist_with_times,
        moscow_date,
        _find_current_position,
        _create_concat_file,
        _get_file_duration_sec,
    )
    from datetime import datetime, timezone, timedelta

    broadcast_date = d or moscow_date()
    ensure_broadcast_for_date(db, broadcast_date)
    playlist = get_playlist_with_times(db, broadcast_date)
    if not playlist:
        return {"ok": False, "error": "Нет эфира на дату", "playlist_count": 0}

    concat_path = _create_concat_file(playlist)
    if not concat_path or not concat_path.exists():
        return {
            "ok": False,
            "error": "concat не создан (нет файлов или ffmpeg)",
            "playlist_count": len(playlist),
            "concat_path": str(concat_path) if concat_path else None,
        }

    # Читаем concat для отладки
    concat_content = ""
    try:
        concat_content = concat_path.read_text(encoding="utf-8", errors="replace")[:2000]
    except Exception as e:
        concat_content = str(e)

    now = datetime.now(timezone(timedelta(hours=3)))
    now_sec = now.hour * 3600 + now.minute * 60 + now.second
    start_idx, seek_sec = _find_current_position(playlist, now_sec)
    total_seek = 0.0
    for i in range(start_idx):
        path, _, dur = playlist[i][0], playlist[i][1], playlist[i][2]
        if path and path.exists():
            d = _get_file_duration_sec(path)
            total_seek += d if d > 0 else float(dur or 0)
        else:
            total_seek += float(dur or 0)
    if start_idx < len(playlist):
        item_path = playlist[start_idx][0]
        if item_path and item_path.exists():
            total_seek += seek_sec
        else:
            total_seek += min(seek_sec, float(playlist[start_idx][2] or 0))

    import subprocess
    bitrate = getattr(settings, "stream_bitrate", "256k") or "256k"
    try:
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "warning",
                "-ss", str(total_seek),
                "-f", "concat", "-safe", "0", "-i", str(concat_path),
                "-t", "3",
                "-c:a", "libmp3lame", "-b:a", bitrate, "-ar", "44100", "-ac", "2",
                "-f", "mp3", "pipe:1",
            ],
            capture_output=True,
            timeout=15,
        )
        out, err, ret = r.stdout, r.stderr, r.returncode
    except Exception as e:
        try:
            concat_path.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "ok": False,
            "error": str(e),
            "playlist_count": len(playlist),
            "concat_preview": concat_content[:500],
        }

    try:
        concat_path.unlink(missing_ok=True)
    except OSError:
        pass

    return {
        "ok": ret == 0,
        "playlist_count": len(playlist),
        "start_idx": start_idx,
        "seek_sec": seek_sec,
        "total_seek": total_seek,
        "concat_lines": len(concat_content.strip().splitlines()),
        "concat_preview": concat_content[:800],
        "ffmpeg_returncode": ret,
        "ffmpeg_stderr": err.decode(errors="replace")[:1000] if err else "",
        "first_chunk_bytes": len(out) if out else 0,
        "stream_bitrate": bitrate,
    }
