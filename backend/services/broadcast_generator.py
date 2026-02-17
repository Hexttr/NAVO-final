"""
Generate broadcast schedule for a day (Moscow time).
Slots:
- News: 9, 12, 15, 18, 21
- Weather: 10, 13, 16, 19, 22
- Podcasts: 11, 14, 17, 20, 23
- INTRO: at XX:55 every hour
- Songs + DJ: fill the rest
"""
from datetime import date
import random
from sqlalchemy.orm import Session
from models import Song, News, Weather, Podcast, Intro, BroadcastItem


FIXED_SLOTS = [
    (9, 0, "news"),
    (10, 0, "weather"),
    (11, 0, "podcast"),
    (12, 0, "news"),
    (13, 0, "weather"),
    (14, 0, "podcast"),
    (15, 0, "news"),
    (16, 0, "weather"),
    (17, 0, "podcast"),
    (18, 0, "news"),
    (19, 0, "weather"),
    (20, 0, "podcast"),
    (21, 0, "news"),
    (22, 0, "weather"),
    (23, 0, "podcast"),
]

INTRO_MINUTE = 55


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

    songs = list(db.query(Song).filter(Song.file_path != "").all())
    news_list = list(db.query(News).filter(News.audio_path != "").all())
    weather_list = list(db.query(Weather).filter(Weather.audio_path != "").all())
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

    for h, m, et in FIXED_SLOTS:
        t_sec = h * 3600 + m * 60
        if et == "news" and news_list:
            n = next(news_it)
            timed_events.append((t_sec, "news", n.id, 120, "Новости"))
        elif et == "weather" and weather_list:
            w = next(weather_it)
            timed_events.append((t_sec, "weather", w.id, 90, "Погода"))
        elif et == "podcast" and podcasts:
            p = next(podcast_it)
            dur = int(p.duration_seconds or 1800)
            timed_events.append((t_sec, "podcast", p.id, dur, p.title))

    for h in range(24):
        t_sec = h * 3600 + INTRO_MINUTE * 60
        if intros:
            i = next(intro_it)
            dur = int(i.duration_seconds or 30)
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
            dur = int(s.duration_seconds or 180)
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
