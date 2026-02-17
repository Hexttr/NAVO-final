"""
Broadcast schedule editing: recalc times, empty slots.
Anchor events (news, weather, podcast, intro) keep fixed start_time.
Fillers (song, dj, empty) get start_time from previous end_time.
"""
from sqlalchemy.orm import Session
from models import BroadcastItem, Song, News, Weather, Podcast, Intro


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
    """Get duration in seconds for entity. Raises ValueError if not found."""
    if entity_type == "song":
        s = db.query(Song).filter(Song.id == entity_id, Song.file_path != "").first()
        if not s:
            raise ValueError("Song not found")
        return float(s.duration_seconds or 180)
    if entity_type == "dj":
        s = db.query(Song).filter(Song.id == entity_id, Song.dj_audio_path != "").first()
        if not s:
            raise ValueError("Song with DJ audio not found")
        return 45.0
    if entity_type == "news":
        n = db.query(News).filter(News.id == entity_id, News.audio_path != "").first()
        if not n:
            raise ValueError("News with audio not found")
        return 120.0
    if entity_type == "weather":
        w = db.query(Weather).filter(Weather.id == entity_id, Weather.audio_path != "").first()
        if not w:
            raise ValueError("Weather with audio not found")
        return 90.0
    if entity_type == "podcast":
        p = db.query(Podcast).get(entity_id)
        if not p:
            raise ValueError("Podcast not found")
        return float(p.duration_seconds or 1800)
    if entity_type == "intro":
        i = db.query(Intro).get(entity_id)
        if not i:
            raise ValueError("Intro not found")
        return float(i.duration_seconds or 30)
    raise ValueError(f"Unknown entity type: {entity_type}")


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
