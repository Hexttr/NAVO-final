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
        from services.streamer_service import moscow_seconds_now
        now_sec = moscow_seconds_now()
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


@router.get("/diagnostics/now-playing")
def diagnostics_now_playing(
    d: date | None = Query(None, description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Полная диагностика «Сейчас играет» — для отладки рассинхрона.
    Показывает: время МСК, stream_position.json, ответ now-playing, слот по расписанию (БД и реальные длительности).
    """
    from services.streamer_service import moscow_date, moscow_seconds_now, get_playlist_with_times, _find_track_at_position
    from services.stream_position import read_now_playing, read_stream_position, _get_path
    from services.broadcast_service import get_entity_meta
    import time
    import json

    broadcast_date = d or moscow_date()
    ensure_broadcast_for_date(db, broadcast_date)
    now_sec = moscow_seconds_now()
    h, m, s = now_sec // 3600, (now_sec % 3600) // 60, now_sec % 60
    moscow_time_str = f"{h:02d}:{m:02d}:{s:02d}"

    # 1. stream_position.json
    sp_path = _get_path()
    sp_raw = None
    sp_age_sec = None
    if sp_path and sp_path.exists():
        try:
            data = json.loads(sp_path.read_text(encoding="utf-8"))
            sp_raw = data
            sp_age_sec = round(time.time() - data.get("timestamp", 0), 1)
        except Exception as e:
            sp_raw = {"error": str(e)}

    # 2. read_now_playing()
    np_from_file = read_now_playing()

    # 3. read_stream_position()
    stream_pos = read_stream_position()

    # 4. Что вернёт now-playing (полная логика)
    position_used = stream_pos if stream_pos is not None else now_sec
    playlist = get_playlist_with_times(db, broadcast_date)
    slot_by_db = _find_track_at_position(playlist, position_used) if playlist else None

    # 5. Слот по расписанию (БД) — детали
    slot_db_detail = None
    if playlist:
        for item in playlist:
            start_sec, dur = item[1], item[2]
            if start_sec <= position_used < start_sec + dur:
                slot_db_detail = {
                    "entity_type": item[3],
                    "entity_id": item[4],
                    "title": item[5] if len(item) > 5 else "—",
                    "start_sec": start_sec,
                    "end_sec": start_sec + dur,
                    "duration_db": dur,
                }
                break

    # 6. Слот по реальным длительностям
    playlist_real = get_playlist_with_times(db, broadcast_date, use_real_durations=True)
    slot_real = _find_track_at_position(playlist_real, position_used) if playlist_real else None
    slot_real_detail = None
    if playlist_real:
        cum = 0
        for item in playlist_real:
            start_sec, dur = item[1], item[2]
            end_sec = start_sec + dur
            if start_sec <= position_used < end_sec:
                slot_real_detail = {
                    "entity_type": item[3],
                    "entity_id": item[4],
                    "title": item[5] if len(item) > 5 else "—",
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "duration_real": dur,
                }
                break
            cum = end_sec

    # 7. Итоговый ответ now-playing (что видит пользователь)
    now_playing_response = None
    if np_from_file and "entity_type" in np_from_file:
        now_playing_response = {
            "source": "stream_position",
            "entityType": np_from_file.get("entity_type"),
            "entityId": np_from_file.get("entity_id"),
            "title": np_from_file.get("title"),
            "currentTime": np_from_file.get("currentTime"),
        }
    else:
        # Fallback
        slot = slot_real_detail or slot_db_detail
        if slot:
            title = slot.get("title")
            if not title:
                try:
                    title = get_entity_meta(db, slot["entity_type"], slot["entity_id"])
                except Exception:
                    title = "—"
            now_playing_response = {
                "source": "fallback",
                "entityType": slot["entity_type"],
                "entityId": slot["entity_id"],
                "title": title,
                "currentTime": moscow_time_str,
            }

    # 8. Icecast
    icecast_status = "unknown"
    try:
        from urllib.request import urlopen, Request
        req = Request("http://127.0.0.1:8001/live", method="HEAD")
        with urlopen(req, timeout=2) as r:
            icecast_status = f"live_{r.status}"
    except Exception as e:
        icecast_status = f"error_{type(e).__name__}"

    return {
        "moscow_time": moscow_time_str,
        "moscow_sec": now_sec,
        "broadcast_date": str(broadcast_date),
        "stream_position_file": {
            "path": str(sp_path) if sp_path else None,
            "exists": sp_path.exists() if sp_path else False,
            "age_sec": sp_age_sec,
            "raw": sp_raw,
        },
        "position_used": position_used,
        "position_source": "stream_position" if stream_pos is not None else "moscow_seconds_now",
        "now_playing_response": now_playing_response,
        "slot_by_db": slot_db_detail,
        "slot_by_real_durations": slot_real_detail,
        "icecast": icecast_status,
        "playlist_count": len(playlist) if playlist else 0,
    }


@router.get("/now-playing-debug")
def now_playing_debug(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    position: float | None = Query(None),
    db: Session = Depends(get_db),
):
    """Отладка now-playing: now_sec, источник, первые 5 слотов, слот вокруг now_sec."""
    from services.streamer_service import moscow_seconds_now

    ensure_broadcast_for_date(db, d)
    stream_pos = None
    try:
        from services.stream_position import read_stream_position
        stream_pos = read_stream_position()
    except Exception:
        pass

    if stream_pos is not None:
        now_sec = float(stream_pos)
        source = "stream_position"
    elif position is not None and position >= 0:
        now_sec = float(position)
        source = "client_position"
    else:
        now_sec = moscow_seconds_now()
        source = "moscow_seconds_now"

    now_sec = max(0, min(86400, now_sec))
    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == d,
            BroadcastItem.entity_type != "empty",
        )
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    slots = []
    for it in items[:5]:
        parts = (it.start_time or "00:00:00").split(":")
        start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if len(parts) == 3 else 0
        end_sec = start_sec + float(it.duration_seconds or 0)
        slots.append({"start": it.start_time, "end": it.end_time, "type": it.entity_type, "start_sec": start_sec, "end_sec": end_sec})

    around = []
    for it in items:
        parts = (it.start_time or "00:00:00").split(":")
        start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if len(parts) == 3 else 0
        end_sec = start_sec + float(it.duration_seconds or 0)
        if start_sec - 60 <= now_sec <= end_sec + 60:
            around.append({"start": it.start_time, "end": it.end_time, "type": it.entity_type, "id": it.entity_id, "start_sec": start_sec, "end_sec": end_sec, "match": start_sec <= now_sec < end_sec})
    return {"now_sec": now_sec, "source": source, "items_count": len(items), "first_slots": slots, "slots_around_now": around}


@router.get("/debug-time")
def debug_time(
    d: date | None = Query(None, description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Отладка: время сервера и текущий элемент."""
    from services.streamer_service import moscow_date, moscow_seconds_now

    now_sec = moscow_seconds_now()
    h, m, s = now_sec // 3600, (now_sec % 3600) // 60, now_sec % 60
    broadcast_date = d or moscow_date()
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
        "server_time": f"{h:02d}:{m:02d}:{s:02d}",
        "server_date": str(broadcast_date),
        "now_sec": now_sec,
        "current_item": current,
        "items_count": len(items),
    }


@router.get("/now-playing")
def get_now_playing(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    position: float | None = Query(None, description="Секунды от полуночи МСК — для HLS (позиция в потоке)"),
    db: Session = Depends(get_db),
):
    """Текущий трек. Простой путь: источник стрима пишет что играет в файл — API просто читает.
    Fallback: position от HLS или вычисление по расписанию."""
    from fastapi.responses import JSONResponse
    from services.stream_position import read_now_playing, read_stream_position
    from services.streamer_service import moscow_seconds_now
    import json
    import logging

    logger = logging.getLogger(__name__)
    empty_fallback = {"entityType": None, "entityId": None, "currentTime": "00:00:00", "title": None}
    cache_headers = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    try:
        ensure_broadcast_for_date(db, d)
        broadcast_date = d

        # 1. Источник стрима (Icecast) пишет что играет — читаем без вычислений
        np = read_now_playing()
        if np and "entity_type" in np:
            return JSONResponse(
                content={
                    "entityType": np["entity_type"],
                    "entityId": np["entity_id"],
                    "currentTime": np["currentTime"],
                    "title": np.get("title", "—"),
                },
                headers=cache_headers,
            )

        # 2. Fallback: position от HLS или stream_position
        stream_pos = read_stream_position()
        if position is not None and position >= 0:
            now_sec = float(position)
        elif stream_pos is not None:
            now_sec = float(stream_pos)
        else:
            now_sec = moscow_seconds_now()
        now_sec = max(0, min(86400, now_sec))
        h, m, s = int(now_sec) // 3600, (int(now_sec) % 3600) // 60, int(now_sec) % 60
        current_time = f"{h:02d}:{m:02d}:{s:02d}"

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
            return JSONResponse(content=empty, headers=cache_headers)
        for i, it in enumerate(items):
            parts = (it.start_time or "00:00:00").split(":")
            start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if len(parts) == 3 else 0
            dur_db = float(it.duration_seconds or 0)
            end_sec = start_sec + dur_db
            if start_sec <= now_sec < end_sec:
                # Уточнение: файл может быть короче, чем в БД — тогда мы уже в следующем треке
                from services.streamer_service import get_entity_duration_from_file
                try:
                    real_dur = get_entity_duration_from_file(db, it.entity_type, it.entity_id)
                    if real_dur > 0 and real_dur < dur_db - 1 and now_sec >= start_sec + real_dur and i + 1 < len(items):
                        it = items[i + 1]
                except Exception:
                    pass
                title = None
                if it.metadata_json:
                    try:
                        meta = json.loads(it.metadata_json)
                        title = meta.get("title", "")
                    except (json.JSONDecodeError, TypeError):
                        pass
                if not title:
                    try:
                        title = get_entity_meta(db, it.entity_type, it.entity_id)
                    except Exception:
                        title = "—"
                return JSONResponse(
                    content={
                        "entityType": it.entity_type,
                        "entityId": it.entity_id,
                        "currentTime": current_time,
                        "title": title or "—",
                    },
                    headers=cache_headers,
                )
        return JSONResponse(content=empty, headers=cache_headers)
    except Exception as e:
        logger.exception("now-playing error: %s", e)
        return JSONResponse(content=empty_fallback, headers=cache_headers, status_code=200)


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
    from services.streamer_service import _mark_broadcast_deleted

    deleted = db.query(BroadcastItem).filter(BroadcastItem.broadcast_date == d).delete()
    db.commit()
    _mark_broadcast_deleted(db, d, deleted=True)
    return {"date": str(d), "deleted": deleted, "message": "Эфир удалён"}


@router.post("/recalc-durations")
def recalc_all_durations(db: Session = Depends(get_db)):
    """Пересчитать длительность всех аудио из файлов (ffprobe). Обновляет сущности и BroadcastItem — точное совпадение админки и эфира."""
    from services.broadcast_service import recalc_all_durations as recalc_svc

    try:
        updated = recalc_svc(db)
        total = sum(updated.values())
        return {"updated": updated, "total": total, "message": f"Обновлено: {updated['songs']} песен, {updated['podcasts']} подкастов, {updated['intros']} интро, {updated['news']} новостей, {updated['weather']} погод, {updated['broadcast_items']} слотов эфира"}
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e)[:200])


@router.post("/generate")
def generate(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    from services.streamer_service import _mark_broadcast_deleted

    for attempt in range(5):
        try:
            db.rollback()
            items = generate_broadcast(db, d)
            for item in items:
                db.add(item)
            db.commit()
            _mark_broadcast_deleted(db, d, deleted=False)
            from services.broadcast_service import recalc_broadcast_for_date
            recalc_broadcast_for_date(db, d)
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
    """Запускает генерацию HLS в отдельном процессе. Возвращает PID или None при ошибке.
    Создаёт lock-файл — не запускает второй процесс для той же даты."""
    try:
        backend_dir = Path(__file__).resolve().parent.parent
        project_root = backend_dir.parent
        run_script = backend_dir / "run_hls.py"
        log_path = project_root / "uploads" / "hls_generation.log"
        lock_path = _hls_generating_lock_path(d)
        if not run_script.exists():
            return None
        if lock_path.exists():
            return None  # Уже запущена — run_hls удалит lock по завершении
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_path.write_text(f"pid={os.getpid()}", encoding="utf-8")
        except OSError:
            return None
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
    """Return stream URL for frontend player. Относительный /stream или полный из STREAM_URL."""
    url = getattr(settings, "stream_url", None) or "/stream"
    if url.startswith(("http://", "https://")):
        return {"url": url}
    base = settings.base_url.rstrip("/")
    return {"url": f"{base}/{url.lstrip('/')}"}


@router.get("/playlist-metadata")
def playlist_metadata(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Метаданные для «Сейчас играет»: {tracks: [{start, end, title}]}. Fallback когда metadata.json 404."""
    from services.hls_service import get_playlist_metadata

    ensure_broadcast_for_date(db, d)
    return get_playlist_metadata(db, d)


@router.get("/hls-url")
def hls_url(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """URL HLS если готов, иначе null. startPosition — секунды от полуночи МСК для seek, ограничено длительностью потока."""
    from services.streamer_service import moscow_seconds_now
    from services.hls_service import get_hls_stream_duration_sec, _get_hls_dir

    ensure_broadcast_for_date(db, d)
    url = get_hls_url(db, d)
    now_sec = moscow_seconds_now()
    start_position = now_sec
    hls_duration_sec = None
    if url and url.startswith("/hls/"):
        parts = url.split("/")
        if len(parts) >= 5:
            hls_date, hls_hash = parts[2], parts[3]
            m3u8_path = _get_hls_dir() / hls_date / hls_hash / "stream.m3u8"
            if m3u8_path.exists():
                dur = get_hls_stream_duration_sec(m3u8_path)
                if dur is not None:
                    hls_duration_sec = round(dur, 1)
                    if now_sec > dur:
                        start_position = max(0, int(dur) - 10)
                    # HLS закончится через <60 сек — лучше сразу /stream (бесконечный)
                    if now_sec > dur - 60:
                        url = None
                else:
                    start_position = 0
    return {"url": url, "hasHls": url is not None, "startPosition": start_position, "hlsDurationSec": hls_duration_sec}


def _hls_generating_lock_path(d: date) -> Path:
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / "uploads" / f"hls_generating_{d}.lock"


@router.get("/hls-status")
def hls_status(
    d: date = Query(..., description="Date YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """Статус HLS. hasHls=true если есть любой доступный HLS. generation_in_progress=true если run_hls ещё работает."""
    from services.streamer_service import get_broadcast_schedule_hash
    from services.hls_service import get_hls_path, get_hls_url

    ensure_broadcast_for_date(db, d)
    playlist = get_playlist_with_times(db, d)
    if not playlist:
        return {"ok": False, "error": "Нет эфира на дату", "hasHls": False, "generation_in_progress": False}

    url = get_hls_url(db, d)
    schedule_hash = get_broadcast_schedule_hash(db, d)
    out_dir = get_hls_path(d, schedule_hash)
    m3u8_path = out_dir / "stream.m3u8"
    date_dir = out_dir.parent
    existing_hashes = []
    if date_dir.exists():
        existing_hashes = [p.name for p in date_dir.iterdir() if p.is_dir() and (p / "stream.m3u8").exists()]

    generation_in_progress = _hls_generating_lock_path(d).exists()

    return {
        "ok": True,
        "hasHls": url is not None,
        "generation_in_progress": generation_in_progress,
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
        lock_path = _hls_generating_lock_path(d)

        if lock_path.exists():
            raise HTTPException(409, "Генерация HLS уже запущена. Подождите завершения (~10–30 мин).")

        if not run_script.exists():
            raise HTTPException(500, "run_hls.py не найден")

        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            lock_path.write_text(f"pid={os.getpid()}", encoding="utf-8")
        except OSError:
            pass
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

    from services.streamer_service import moscow_seconds_now
    now_sec = moscow_seconds_now()
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
