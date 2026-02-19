"""
Generate broadcast schedule for a day (Moscow time).
Slots and intro minute from settings (editable in admin).
"""
from datetime import date
import random
from sqlalchemy import or_
from sqlalchemy.orm import Session
from models import Song, News, Weather, Podcast, Intro, BroadcastItem
from services.streamer_service import get_entity_duration_from_file
from services.settings_service import get_json, get

DEFAULT_SLOTS = [
    (9, 0, "news"), (10, 0, "weather"), (11, 0, "podcast"),
    (12, 0, "news"), (13, 0, "weather"), (14, 0, "podcast"),
    (15, 0, "news"), (16, 0, "weather"), (17, 0, "podcast"),
    (18, 0, "news"), (19, 0, "weather"), (20, 0, "podcast"),
    (21, 0, "news"), (22, 0, "weather"), (23, 0, "podcast"),
]
DEFAULT_INTRO_MINUTE = 55


def _time_str(h: int, m: int, s: int = 0) -> str:
    return f"{h:02d}:{m:02d}:{s:02d}"


def _sec_to_hms(sec: int) -> tuple[int, int, int]:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return h, m, s


def generate_broadcast(db: Session, broadcast_date: date) -> list[BroadcastItem]:
    """Generate full day broadcast. Replaces existing items for date."""
    db.query(BroadcastItem).filter(BroadcastItem.broadcast_date == broadcast_date).delete()

    raw_slots = get_json(db, "broadcast_slots") or DEFAULT_SLOTS
    intro_min = int(get(db, "broadcast_intro_minute") or DEFAULT_INTRO_MINUTE)
    fixed_slots = [(int(s[0]), int(s[1]), str(s[2])) for s in raw_slots if len(s) >= 3 and s[2] in ("news", "weather", "podcast")]
    if not fixed_slots:
        fixed_slots = DEFAULT_SLOTS

    songs = list(db.query(Song).filter(Song.file_path != "").all())
    # Новости и погода: для даты X — только записи с broadcast_date=X или null (обратная совместимость)
    news_list = list(
        db.query(News)
        .filter(News.audio_path != "")
        .filter(or_(News.broadcast_date == broadcast_date, News.broadcast_date.is_(None)))
        .all()
    )
    weather_list = list(
        db.query(Weather)
        .filter(Weather.audio_path != "")
        .filter(or_(Weather.broadcast_date == broadcast_date, Weather.broadcast_date.is_(None)))
        .all()
    )
    podcasts = list(db.query(Podcast).all())
    intros = list(db.query(Intro).all())

    if not songs:
        raise ValueError("Нет песен. Добавьте хотя бы одну песню.")

    random.shuffle(songs)
    random.shuffle(news_list)
    random.shuffle(weather_list)
    random.shuffle(podcasts)
    random.shuffle(intros)

    def cycle(lst):
        i = 0
        while lst:
            yield lst[i % len(lst)]
            i += 1

    news_it = cycle(news_list)
    weather_it = cycle(weather_list)
    podcast_it = cycle(podcasts)
    intro_it = cycle(intros)
    song_it = cycle(songs)

    # Timed events: (second of day, entity_type, entity_id, duration_sec, meta)
    timed_events = []

    for h, m, et in fixed_slots:
        t_sec = h * 3600 + m * 60
        if et == "news" and news_list:
            n = next(news_it)
            dur = int(get_entity_duration_from_file(db, "news", n.id))
            if dur <= 0:
                dur = int(n.duration_seconds or 120)
            if dur > 0 and (not n.duration_seconds or abs(n.duration_seconds - dur) > 1):
                n.duration_seconds = round(dur, 1)
                db.commit()
            dur = dur if dur > 0 else 120
            timed_events.append((t_sec, "news", n.id, dur, "Новости"))
        elif et == "weather" and weather_list:
            w = next(weather_it)
            dur = int(get_entity_duration_from_file(db, "weather", w.id))
            if dur <= 0:
                dur = int(w.duration_seconds or 90)
            if dur > 0 and (not w.duration_seconds or abs(w.duration_seconds - dur) > 1):
                w.duration_seconds = round(dur, 1)
                db.commit()
            dur = dur if dur > 0 else 90
            timed_events.append((t_sec, "weather", w.id, dur, "Погода"))
        elif et == "podcast" and podcasts:
            p = next(podcast_it)
            dur = int(get_entity_duration_from_file(db, "podcast", p.id))
            if dur <= 0:
                dur = int(p.duration_seconds or 1800)
            if dur > 0 and (not p.duration_seconds or abs(p.duration_seconds - dur) > 1):
                p.duration_seconds = round(dur, 1)
                db.commit()
            dur = dur if dur > 0 else 1800
            timed_events.append((t_sec, "podcast", p.id, dur, p.title))

    for h in range(24):
        t_sec = h * 3600 + intro_min * 60
        if intros:
            i = next(intro_it)
            dur = int(get_entity_duration_from_file(db, "intro", i.id))
            if dur <= 0:
                dur = int(i.duration_seconds or 30)
            if dur > 0 and (not i.duration_seconds or abs(i.duration_seconds - dur) > 1):
                i.duration_seconds = round(dur, 1)
                db.commit()
            dur = dur if dur > 0 else 30
            timed_events.append((t_sec, "intro", i.id, dur, i.title))

    timed_events.sort(key=lambda x: x[0])

    # Build ordered blocks: fill gaps with song+DJ
    blocks = []
    song_idx = [0]

    def next_song():
        s = songs[song_idx[0] % len(songs)]
        song_idx[0] += 1
        return s

    current_sec = 0
    day_end = 24 * 3600

    def try_add_song(remaining_sec: int) -> bool:
        """Add a song that fits in remaining_sec. Returns True if added."""
        nonlocal current_sec
        for _ in range(len(songs)):
            s = next_song()
            dj = 45 if s.dj_audio_path else 0
            dur = int(get_entity_duration_from_file(db, "song", s.id))
            if dur <= 0:
                dur = int(s.duration_seconds or 180)
            if dur > 0 and (not s.duration_seconds or abs(s.duration_seconds - dur) > 1):
                s.duration_seconds = round(dur, 1)
                db.commit()
            dur = dur if dur > 0 else 180
            total = dj + dur
            if total <= remaining_sec:
                if s.dj_audio_path:
                    blocks.append((current_sec, "dj", s.id, dj, f"DJ: {s.artist} - {s.title}"))
                    current_sec += dj
                blocks.append((current_sec, "song", s.id, dur, f"{s.artist} - {s.title}"))
                current_sec += dur
                return True
        return False

    for t_sec, et, eid, dur_sec, meta in timed_events:
        gap = t_sec - current_sec
        while gap > 90 and try_add_song(gap):
            gap = t_sec - current_sec
        blocks.append((t_sec, et, eid, dur_sec, meta))
        current_sec = t_sec + dur_sec

    # Fill remaining time after last event — ищем песню, которая влезает
    while current_sec < day_end - 60:
        remaining = day_end - current_sec
        if not try_add_song(remaining):
            break

    blocks.sort(key=lambda x: x[0])

    items = []
    for order, (start_sec, et, eid, dur_sec, meta) in enumerate(blocks):
        h, m, s = _sec_to_hms(int(start_sec))
        start = _time_str(h, m, s)
        eh, em, es = _sec_to_hms(int(start_sec + dur_sec))
        end = _time_str(eh, em, es)
        safe_meta = meta.replace('"', "'")[:200]
        items.append(BroadcastItem(
            broadcast_date=broadcast_date,
            entity_type=et,
            entity_id=eid,
            start_time=start,
            end_time=end,
            duration_seconds=float(dur_sec),
            sort_order=order,
            metadata_json=f'{{"title":"{safe_meta}"}}',
        ))

    return items
