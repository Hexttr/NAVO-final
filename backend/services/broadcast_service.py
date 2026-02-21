"""
Broadcast schedule editing: recalc times, empty slots.
Anchor events (news, weather, podcast, intro) keep fixed start_time.
Fillers (song, dj, empty) get start_time from previous end_time.
"""
from datetime import date
from sqlalchemy.orm import Session
from models import BroadcastItem, Song, News, Weather, Podcast, Intro
from services.streamer_service import get_entity_duration_from_file


ANCHOR_TYPES = {"news", "weather", "podcast", "intro"}


def _time_str(h: int, m: int, s: int = 0) -> str:
    return f"{h:02d}:{m:02d}:{s:02d}"


def _parse_time(t: str) -> int:
    """Parse HH:MM:SS to seconds of day."""
    parts = t.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]) if len(parts) == 3 else 0


def _sec_to_hms(sec: int) -> tuple[int, int, int]:
    h = int(sec) // 3600
    m = (int(sec) % 3600) // 60
    s = int(sec) % 60
    return h, m, s


def recalc_times(db: Session, broadcast_date, items: list[BroadcastItem]) -> None:
    """Recalculate start_time/end_time for all items. Anchors keep start_time."""
    items = sorted(items, key=lambda x: x.sort_order)
    prev_end_sec = 0
    for item in items:
        dur = float(item.duration_seconds or 0)
        if item.entity_type in ANCHOR_TYPES:
            start_sec = _parse_time(item.start_time)
        else:
            start_sec = prev_end_sec
        end_sec = start_sec + int(dur)
        h, m, s = _sec_to_hms(start_sec)
        item.start_time = _time_str(h, m, s)
        eh, em, es = _sec_to_hms(end_sec)
        item.end_time = _time_str(eh, em, es)
        prev_end_sec = end_sec


def get_entity_duration(db: Session, entity_type: str, entity_id: int) -> float:
    """Get duration in seconds for entity. При duration_seconds=0 — реальная длительность из файла (ffprobe)."""
    if entity_type == "song":
        s = db.query(Song).filter(Song.id == entity_id, Song.file_path != "").first()
        if not s:
            raise ValueError("Song not found")
        dur = float(s.duration_seconds or 0)
        if dur <= 0:
            dur = get_entity_duration_from_file(db, "song", entity_id)
        return dur if dur > 0 else 180.0
    if entity_type == "dj":
        s = db.query(Song).filter(Song.id == entity_id, Song.dj_audio_path != "").first()
        if not s:
            raise ValueError("Song with DJ audio not found")
        dur = get_entity_duration_from_file(db, "dj", entity_id)
        return dur if dur > 0 else 45.0
    if entity_type == "news":
        n = db.query(News).filter(News.id == entity_id, News.audio_path != "").first()
        if not n:
            raise ValueError("News with audio not found")
        dur = float(n.duration_seconds or 0)
        if dur <= 0:
            dur = get_entity_duration_from_file(db, "news", entity_id)
        return dur if dur > 0 else 120.0
    if entity_type == "weather":
        w = db.query(Weather).filter(Weather.id == entity_id, Weather.audio_path != "").first()
        if not w:
            raise ValueError("Weather with audio not found")
        dur = float(w.duration_seconds or 0)
        if dur <= 0:
            dur = get_entity_duration_from_file(db, "weather", entity_id)
        return dur if dur > 0 else 90.0
    if entity_type == "podcast":
        p = db.query(Podcast).get(entity_id)
        if not p:
            raise ValueError("Podcast not found")
        dur = float(p.duration_seconds or 0)
        if dur <= 0:
            dur = get_entity_duration_from_file(db, "podcast", entity_id)
            if dur > 0:
                p.duration_seconds = round(dur, 1)
                db.commit()
        return dur if dur > 0 else 1800.0
    if entity_type == "intro":
        i = db.query(Intro).get(entity_id)
        if not i:
            raise ValueError("Intro not found")
        dur = float(i.duration_seconds or 0)
        if dur <= 0:
            dur = get_entity_duration_from_file(db, "intro", entity_id)
            if dur > 0:
                i.duration_seconds = round(dur, 1)
                db.commit()
        return dur if dur > 0 else 30.0
    raise ValueError(f"Unknown entity type: {entity_type}")


def recalc_all_durations(db: Session) -> dict:
    """
    Пересчитать длительность всех аудио из файлов (ffprobe).
    Обновляет сущности и BroadcastItem — синхронизация админки и эфира.
    Вызывать при старте Icecast source и после замены файлов.
    """
    updated = {"songs": 0, "podcasts": 0, "intros": 0, "news": 0, "weather": 0, "broadcast_items": 0}
    for s in db.query(Song).filter(Song.file_path != "").all():
        dur = get_entity_duration_from_file(db, "song", s.id)
        if dur > 0 and (not s.duration_seconds or abs(s.duration_seconds - dur) > 1):
            s.duration_seconds = round(dur, 1)
            updated["songs"] += 1
    for p in db.query(Podcast).filter(Podcast.file_path != "").all():
        dur = get_entity_duration_from_file(db, "podcast", p.id)
        if dur > 0 and (not p.duration_seconds or abs(p.duration_seconds - dur) > 1):
            p.duration_seconds = round(dur, 1)
            updated["podcasts"] += 1
    for i in db.query(Intro).filter(Intro.file_path != "").all():
        dur = get_entity_duration_from_file(db, "intro", i.id)
        if dur > 0 and (not i.duration_seconds or abs(i.duration_seconds - dur) > 1):
            i.duration_seconds = round(dur, 1)
            updated["intros"] += 1
    for n in db.query(News).filter(News.audio_path != "").all():
        dur = get_entity_duration_from_file(db, "news", n.id)
        if dur > 0 and (not n.duration_seconds or abs(n.duration_seconds - dur) > 1):
            n.duration_seconds = round(dur, 1)
            updated["news"] += 1
    for w in db.query(Weather).filter(Weather.audio_path != "").all():
        dur = get_entity_duration_from_file(db, "weather", w.id)
        if dur > 0 and (not w.duration_seconds or abs(w.duration_seconds - dur) > 1):
            w.duration_seconds = round(dur, 1)
            updated["weather"] += 1
    for item in db.query(BroadcastItem).filter(BroadcastItem.entity_type != "empty").all():
        try:
            dur = get_entity_duration(db, item.entity_type, item.entity_id)
            if dur > 0 and (not item.duration_seconds or abs(item.duration_seconds - dur) > 0.5):
                item.duration_seconds = round(dur, 1)
                updated["broadcast_items"] += 1
        except Exception:
            pass
    db.commit()
    dates = {r[0] for r in db.query(BroadcastItem.broadcast_date).distinct().all()}
    for d in dates:
        items = db.query(BroadcastItem).filter(BroadcastItem.broadcast_date == d).order_by(BroadcastItem.sort_order).all()
        recalc_times(db, d, items)
    db.commit()
    return updated


def recalc_broadcast_for_date(db: Session, broadcast_date: date) -> int:
    """
    Пересчитать duration_seconds только для BroadcastItem на указанную дату.
    Использует реальные длительности из файлов (ffprobe) — синхрон с эфиром.
    Вызывается при старте Icecast source.
    """
    items = db.query(BroadcastItem).filter(
        BroadcastItem.broadcast_date == broadcast_date,
        BroadcastItem.entity_type != "empty",
    ).order_by(BroadcastItem.sort_order).all()
    if not items:
        return 0
    count = 0
    for item in items:
        dur = get_entity_duration_from_file(db, item.entity_type, item.entity_id)
        if dur <= 0 and item.entity_type == "dj":
            dur = 45.0  # DJ fallback
        if dur > 0 and (not item.duration_seconds or abs(item.duration_seconds - dur) > 0.5):
            item.duration_seconds = round(dur, 1)
            count += 1
    if count > 0:
        recalc_times(db, broadcast_date, items)
        db.commit()
    return count


def get_entity_meta(db: Session, entity_type: str, entity_id: int) -> str:
    """Get display title for entity."""
    if entity_type == "song":
        s = db.query(Song).get(entity_id)
        return f"{s.artist} - {s.title}" if s else "—"
    if entity_type == "dj":
        s = db.query(Song).get(entity_id)
        return f"DJ: {s.artist} - {s.title}" if s else "—"
    if entity_type == "news":
        return "Новости"
    if entity_type == "weather":
        return "Погода"
    if entity_type == "podcast":
        p = db.query(Podcast).get(entity_id)
        return p.title if p else "—"
    if entity_type == "intro":
        i = db.query(Intro).get(entity_id)
        return i.title if i else "—"
    return "—"
