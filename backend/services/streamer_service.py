"""
Stream broadcast playlist as continuous MP3.
Синхронизация по московскому времени: воспроизведение с текущего момента эфира.
"""
import asyncio
import json
import subprocess
import tempfile
import time
from datetime import date, datetime, timezone, timedelta

from pathlib import Path

from sqlalchemy.orm import Session

from config import settings


def _generate_silence_mp3(duration_sec: float):
    """Генерирует MP3-тишину через ffmpeg. Yields chunks."""
    if duration_sec <= 0:
        return
    try:
        proc = subprocess.Popen(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
                "-t", str(int(duration_sec) + 1),
                "-q:a", "9", "-acodec", "libmp3lame", "-f", "mp3", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        while True:
            chunk = proc.stdout.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
        proc.wait()
    except (FileNotFoundError, OSError):
        pass


def _get_file_duration_sec(path: Path) -> float:
    """Реальная длительность файла через ffprobe. Fallback — из playlist."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0 and r.stdout:
            return float(r.stdout.decode().strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return 0.0


from models import BroadcastItem, Song, News, Weather, Podcast, Intro


# Сервер должен быть в Europe/Moscow. Используем local time напрямую.
MOSCOW_TZ = timezone(timedelta(hours=3))


def _moscow_now() -> datetime:
    """Текущее время по Москве. Сервер в Europe/Moscow — используем local time."""
    return datetime.now(MOSCOW_TZ)


def moscow_date() -> date:
    """Текущая дата по Москве. Из API при use_external_time, иначе системное время."""
    if getattr(settings, "use_external_time", True):
        from services.time_service import moscow_date_from_api
        d = moscow_date_from_api()
        if d is not None:
            return d
    return _moscow_now().date()


def moscow_seconds_now() -> int:
    """Секунды от полуночи МСК. Из API при use_external_time, иначе системное."""
    base = None
    if getattr(settings, "use_external_time", True):
        from services.time_service import moscow_seconds_from_api
        base = moscow_seconds_from_api()
    if base is None:
        now = _moscow_now()
        base = now.hour * 3600 + now.minute * 60 + now.second
    offset = getattr(settings, "sync_offset_seconds", 0) or 0
    return max(0, min(86400 - 1, base + offset))


from utils.time_utils import parse_time as _parse_time

# Project root for resolving relative paths (backend/services -> backend -> project)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _find_mp3_frame_sync(f, start_offset: int) -> int:
    """Find next MP3 frame sync (0xFF 0xFB/0xFA/0xF3...) from start_offset. Returns byte position."""
    f.seek(max(0, start_offset))
    data = f.read(8192)
    for i in range(len(data) - 1):
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:  # MP3 sync
            return start_offset + i
    return start_offset  # fallback


def _skip_id3_and_find_sync(f) -> None:
    """If file starts with ID3 tag, seek past it to first MP3 frame. Modifies f position."""
    header = f.read(10)
    if len(header) < 10:
        f.seek(0)
        return
    if header[:3] == b"ID3":
        size = (header[6] & 0x7F) << 21 | (header[7] & 0x7F) << 14 | (header[8] & 0x7F) << 7 | (header[9] & 0x7F)
        f.seek(10 + size)
        data = f.read(8192)
        for i in range(len(data) - 1):
            if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
                f.seek(10 + size + i)
                return
    f.seek(0)


def _resolve_path(p: Path, entity_type: str = "", entity_id: int = 0) -> Path | None:
    """Try to resolve path; return None if file doesn't exist."""
    p = Path(str(p).replace("\\", "/"))
    candidates = [
        p,
        PROJECT_ROOT / p,
        PROJECT_ROOT / settings.upload_dir / p.name,
        Path.cwd() / p,
    ]
    if len(p.parts) >= 2:
        candidates.append(PROJECT_ROOT / settings.upload_dir / p.parts[-2] / p.name)
        candidates.append(Path.cwd() / settings.upload_dir / p.parts[-2] / p.name)
    if entity_type == "dj" and entity_id:
        for root in (PROJECT_ROOT / settings.upload_dir, Path.cwd() / settings.upload_dir):
            candidates.append(root / "dj" / f"dj_{entity_id}.mp3")
    if entity_type == "podcast":
        for root in (PROJECT_ROOT / settings.upload_dir, Path.cwd() / settings.upload_dir):
            candidates.append(root / "podcasts" / p.name)
    if entity_type == "intro":
        for root in (PROJECT_ROOT / settings.upload_dir, Path.cwd() / settings.upload_dir):
            candidates.append(root / "intros" / p.name)
    for alt in candidates:
        try:
            if alt and alt.exists():
                return alt
        except OSError:
            pass
    return None


def _get_audio_path(db: Session, entity_type: str, entity_id: int) -> Path | None:
    """Resolve audio file path for entity. Returns None if not found."""
    base = Path(settings.upload_dir)
    if entity_type == "song":
        s = db.query(Song).filter(Song.id == entity_id, Song.file_path != "").first()
        if not s:
            return None
        p = Path(s.file_path)
    elif entity_type == "dj":
        s = db.query(Song).filter(Song.id == entity_id, Song.dj_audio_path != "").first()
        if not s:
            return None
        p = Path(s.dj_audio_path)
    elif entity_type == "news":
        n = db.query(News).filter(News.id == entity_id, News.audio_path != "").first()
        if not n:
            return None
        p = Path(n.audio_path)
    elif entity_type == "weather":
        w = db.query(Weather).filter(Weather.id == entity_id, Weather.audio_path != "").first()
        if not w:
            return None
        p = Path(w.audio_path)
    elif entity_type == "podcast":
        p_ent = db.query(Podcast).filter(Podcast.id == entity_id).first()
        if not p_ent or not p_ent.file_path:
            return None
        p = Path(p_ent.file_path)
    elif entity_type == "intro":
        i = db.query(Intro).filter(Intro.id == entity_id).first()
        if not i or not i.file_path:
            return None
        p = Path(i.file_path)
    else:
        return None
    return _resolve_path(p, entity_type, entity_id)


def get_entity_duration_from_file(db: Session, entity_type: str, entity_id: int) -> float:
    """
    Реальная длительность аудиофайла через ffprobe.
    Возвращает 0.0 если файл не найден или ffprobe недоступен.
    """
    path = _get_audio_path(db, entity_type, entity_id)
    if not path:
        return 0.0
    return _get_file_duration_sec(path)


CHUNK_SIZE = 32 * 1024  # 32 KB


def resolve_broadcast_date(db: Session, requested_date: date) -> date:
    """
    Возвращает последнюю дату с эфиром (включая requested_date).
    Сканирует назад до 7 дней.
    """
    for days_back in range(8):
        d = requested_date - timedelta(days=days_back)
        has_items = (
            db.query(BroadcastItem)
            .filter(
                BroadcastItem.broadcast_date == d,
                BroadcastItem.entity_type != "empty",
            )
            .first()
        )
        if has_items:
            return d
    return requested_date


def _is_date_explicitly_deleted(db: Session, d: date) -> bool:
    """Дата в списке явно удалённых — не восстанавливать копированием."""
    from models import Setting
    row = db.query(Setting).filter(Setting.key == "deleted_broadcast_dates").first()
    if not row or not row.value:
        return False
    try:
        dates = json.loads(row.value)
        return str(d) in (dates if isinstance(dates, list) else [])
    except (json.JSONDecodeError, TypeError):
        return False


def _mark_broadcast_deleted(db: Session, d: date, deleted: bool) -> None:
    """Добавить/убрать дату из списка явно удалённых."""
    from models import Setting
    row = db.query(Setting).filter(Setting.key == "deleted_broadcast_dates").first()
    dates = []
    if row and row.value:
        try:
            dates = json.loads(row.value)
            if not isinstance(dates, list):
                dates = []
        except (json.JSONDecodeError, TypeError):
            dates = []
    ds = str(d)
    if deleted:
        if ds not in dates:
            dates.append(ds)
    else:
        dates = [x for x in dates if x != ds]
    if row:
        row.value = json.dumps(dates, ensure_ascii=False)
    else:
        db.add(Setting(key="deleted_broadcast_dates", value=json.dumps(dates, ensure_ascii=False)))
    db.commit()


def ensure_broadcast_for_date(db: Session, target_date: date) -> bool:
    """
    Если на target_date нет эфира — копируем с последней даты, где он есть.
    Не копируем, если дата явно удалена админом (ждём новую генерацию).
    Возвращает True если была копия, False если эфир уже был или нечего копировать.
    """
    if _is_date_explicitly_deleted(db, target_date):
        return False
    has_items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == target_date,
            BroadcastItem.entity_type != "empty",
        )
        .first()
    )
    if has_items:
        return False

    source_date = resolve_broadcast_date(db, target_date)
    if source_date == target_date:
        return False  # нет источника для копирования

    source_items = (
        db.query(BroadcastItem)
        .filter(BroadcastItem.broadcast_date == source_date)
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    if not source_items:
        return False

    for item in source_items:
        db.add(BroadcastItem(
            broadcast_date=target_date,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            start_time=item.start_time,
            end_time=item.end_time,
            duration_seconds=item.duration_seconds,
            sort_order=item.sort_order,
            metadata_json=item.metadata_json or "{}",
        ))
    db.commit()
    # Пересчёт длительностей из файлов — тайминги сразу по расписанию
    from services.broadcast_service import recalc_broadcast_for_date
    recalc_broadcast_for_date(db, target_date)
    return True


def get_broadcast_schedule_hash(db: Session, broadcast_date: date) -> str:
    """Хеш эфирной сетки для обнаружения изменений. При смене расписания — перезагрузка стрима."""
    items = (
        db.query(BroadcastItem)
        .filter(
            BroadcastItem.broadcast_date == broadcast_date,
            BroadcastItem.entity_type != "empty",
        )
        .order_by(BroadcastItem.sort_order)
        .all()
    )
    parts = [f"{i.sort_order}:{i.entity_type}:{i.entity_id}:{i.start_time}:{i.duration_seconds}" for i in items]
    return str(hash(tuple(parts)))


def get_playlist_with_times(db: Session, broadcast_date: date, use_real_durations: bool = False) -> list[tuple]:
    """
    Get playlist: (path|None, start_sec, duration_sec, entity_type, entity_id, title).
    use_real_durations: границы по реальным длительностям файлов (для точного now-playing).
    """
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
    cum_start = 0
    for item in items:
        p = _get_audio_path(db, item.entity_type, item.entity_id)
        dur = float(item.duration_seconds or 0)
        if use_real_durations and p and p.exists():
            real_dur = _get_file_duration_sec(p)
            if real_dur > 0:
                dur = real_dur
        start_sec = cum_start if use_real_durations else _parse_time(item.start_time)
        cum_start += int(dur)
        title = None
        if item.metadata_json:
            try:
                meta = json.loads(item.metadata_json)
                title = meta.get("title", "")
            except (json.JSONDecodeError, TypeError):
                pass
        if not title:
            from services.broadcast_service import get_entity_meta
            title = get_entity_meta(db, item.entity_type, item.entity_id)
        result.append((p, start_sec, dur, item.entity_type, item.entity_id, title or "—"))
    return result


def _find_current_position(playlist: list[tuple], now_sec: int) -> tuple[int, int]:
    """
    Find (playlist_index, seek_sec) for current Moscow time.
    seek_sec = seconds to skip within the current file (0 if at start).
    """
    for i, item in enumerate(playlist):
        start_sec, dur = item[1], item[2]
        end_sec = start_sec + int(dur)
        if start_sec <= now_sec < end_sec:
            seek_sec = now_sec - start_sec
            return i, seek_sec
        if now_sec < start_sec:
            return i, 0  # будущий элемент — начинаем с него (или предыдущего?)
    # После последнего — начинаем с конца (пустой поток) или с последнего
    if playlist:
        return len(playlist) - 1, int(playlist[-1][2])  # конец последнего
    return 0, 0


def _find_track_at_position(playlist: list[tuple], pos_sec: float, total_sec: float | None = None) -> tuple[str, int, str] | None:
    """Трек в позиции pos_sec. total_sec: для cumulative — wrap при loop; иначе pos % 86400."""
    if total_sec and total_sec > 0 and pos_sec >= total_sec:
        pos_sec = pos_sec % total_sec
    elif not total_sec and pos_sec >= 86400:
        pos_sec = pos_sec % 86400
    pos = pos_sec
    for item in playlist:
        start_sec, dur = item[1], item[2]
        if start_sec <= pos < start_sec + dur:
            return (item[3], item[4], item[5] if len(item) > 5 else "—")
    return None


def stream_broadcast(playlist: list[tuple], sync_to_moscow: bool = True):
    """
    Async generator: yields MP3 bytes. Бесконечный цикл — поток не обрывается.
    If sync_to_moscow=True, starts from current Moscow time position.
    """
    if not playlist:
        return
    start_idx = 0
    seek_sec = 0
    if sync_to_moscow:
        now_sec = moscow_seconds_now()
        start_idx, seek_sec = _find_current_position(playlist, now_sec)
    idx = start_idx
    first_round = True
    while True:
        try:
            item = playlist[idx]
            path = item[0]
            duration_sec = item[2]
            # Файл отсутствует или не найден — генерируем тишину (сохраняем синхронизацию с расписанием)
            if path is None or not path.exists():
                silence_dur = duration_sec
                if first_round and idx == start_idx and seek_sec > 0:
                    silence_dur = max(0, duration_sec - seek_sec)
                for chunk in _generate_silence_mp3(silence_dur):
                    yield chunk
                idx += 1
                if idx >= len(playlist):
                    idx = 0
                    first_round = False
                continue
            skip_bytes = 0
            if first_round and idx == start_idx and seek_sec > 0:
                try:
                    size = path.stat().st_size
                    actual_dur = _get_file_duration_sec(path)
                    dur = actual_dur if actual_dur > 0 else duration_sec
                    if dur > 0:
                        skip_bytes = int((seek_sec / dur) * size)
                        skip_bytes = min(skip_bytes, max(0, size - CHUNK_SIZE))
                except OSError:
                    pass
            try:
                size = path.stat().st_size
                if size < 100:  # Пустой/битый файл — пропускаем
                    raise OSError("skip")
            except OSError:
                idx += 1
                if idx >= len(playlist):
                    idx = 0
                    first_round = False
                continue
            else:
                with open(path, "rb") as f:
                    if skip_bytes:
                        skip_bytes = _find_mp3_frame_sync(f, skip_bytes)
                        f.seek(skip_bytes)
                    else:
                        # Всегда пропускать ID3 при чтении с начала — иначе первый файл без seek мог отдавать ID3 как аудио
                        _skip_id3_and_find_sync(f)
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        yield chunk
        except (StopIteration, GeneratorExit):
            raise
        except Exception:
            pass
        idx += 1
        if idx >= len(playlist):
            idx = 0
            first_round = False


def _get_or_create_silence_1sec() -> Path | None:
    """Создаёт 1-секундный MP3 тишины для concat. Кэшируется в temp."""
    cache = Path(tempfile.gettempdir()) / "navo_silence_1s.mp3"
    if cache.exists():
        return cache
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "1", "-q:a", "9", "-acodec", "libmp3lame",
                str(cache),
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return cache if cache.exists() else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _get_or_create_silence_mp3(duration_sec: int) -> Path | None:
    """
    Создаёт MP3 тишины заданной длительности. Кэш по секундам.
    Директива duration в ffconcat ненадёжна — используем реальные файлы.
    """
    if duration_sec <= 0:
        return _get_or_create_silence_1sec()
    cache_dir = Path(tempfile.gettempdir()) / "navo_silence"
    cache_dir.mkdir(exist_ok=True)
    cache = cache_dir / f"silence_{duration_sec}s.mp3"
    if cache.exists():
        return cache
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", str(duration_sec), "-q:a", "9", "-acodec", "libmp3lame",
                str(cache),
            ],
            capture_output=True,
            timeout=max(10, duration_sec + 5),
            check=False,
        )
        return cache if cache.exists() else _get_or_create_silence_1sec()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return _get_or_create_silence_1sec()


def _path_for_concat(p: Path) -> str:
    """Путь для ffconcat: forward slashes, экранирование кавычек."""
    return str(p.resolve()).replace("\\", "/").replace("'", "'\\''")


def _create_concat_file(playlist: list[tuple], out_dir: Path | None = None, start_from_idx: int = 0, loop_for_midnight: bool = True) -> Path | None:
    """
    Создаёт concat-файл для FFmpeg. path=None → реальный файл тишины.
    start_from_idx: начать с этого индекса (для быстрого seek — только seek_sec в первом файле).
    loop_for_midnight: дублировать плейлист для бесшовного перехода в полночь (стрим). Для HLS VOD — False.
    """
    lines = ["ffconcat version 1.0", ""]
    has_any = False
    # Элементы с start_from_idx до конца + с начала до start_from_idx (для зацикливания)
    indices = list(range(start_from_idx, len(playlist))) + list(range(0, start_from_idx))
    for idx in indices:
        item = playlist[idx]
        path, dur = item[0], item[2]  # (path, start_sec, dur, entity_type, entity_id, title)
        if path is not None and path.exists():
            lines.append(f"file '{_path_for_concat(path)}'")
            has_any = True
        elif dur > 0:
            silence_path = _get_or_create_silence_mp3(int(dur))
            if silence_path and silence_path.exists():
                lines.append(f"file '{_path_for_concat(silence_path)}'")
                has_any = True
    if not has_any or len(lines) <= 2:
        return None
    # Дублируем для зацикливания (только для live-стрима — не для HLS VOD)
    if loop_for_midnight:
        for idx in indices:
            item = playlist[idx]
            path, dur = item[0], item[2]
            if path is not None and path.exists():
                lines.append(f"file '{_path_for_concat(path)}'")
            elif dur > 0:
                silence_path = _get_or_create_silence_mp3(int(dur))
                if silence_path and silence_path.exists():
                    lines.append(f"file '{_path_for_concat(silence_path)}'")
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        concat_path = out_dir / "concat.list"
        concat_path.write_text("\n".join(lines), encoding="utf-8")
        return concat_path
    fd, p = tempfile.mkstemp(suffix=".concat", prefix="navo_")
    with open(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return Path(p)


async def stream_broadcast_ffmpeg_concat(
    playlist: list[tuple],
    sync_to_moscow: bool = True,
    on_position=None,
    playlist_for_track_lookup: list | None = None,
):
    """
    Один FFmpeg с concat + реэнкод 128k — единый формат, без обрывов при смене треков.
    Критично для Icecast: пауза >1 сек вызывает отключение источника.
    on_position: callback(position_sec) — вызывается каждые 2 сек для синхронизации «Сейчас играет».
    """
    if not playlist:
        return
    now_sec = moscow_seconds_now() if sync_to_moscow else 0
    start_idx, seek_sec = _find_current_position(playlist, now_sec)
    # Concat с start_from_idx — первый файл = текущий трек. Seek только seek_sec (0–300 сек), не 3+ часа.
    total_seek = 0.0
    stream_start_position_sec = 0.0  # для on_position: секунды от полуночи
    if start_idx < len(playlist):
        item_path = playlist[start_idx][0]
        start_sec = playlist[start_idx][1]
        if item_path is not None and item_path.exists():
            total_seek = float(seek_sec)
        else:
            total_seek = min(seek_sec, float(playlist[start_idx][2] or 0))
        stream_start_position_sec = float(start_sec) + total_seek
    concat_path = _create_concat_file(playlist, start_from_idx=start_idx)
    if not concat_path or not concat_path.exists():
        # Fallback: concat не создан (нет ffmpeg/silence) — сырой стрим
        async for chunk in stream_broadcast_async(playlist, sync_to_moscow):
            yield chunk
        return
    chunk_size = 32 * 1024
    try:
        # Реэнкод в единый формат — разные битрейты/сэмплрейты при concat вызывают
        # обрыв потока у Icecast и «обрезку» MP3 при переключении треков
        bitrate = getattr(settings, "stream_bitrate", "256k") or "256k"
        args = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-stream_loop", "-1",
            "-ss", str(total_seek),
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-c:a", "libmp3lame", "-b:a", bitrate, "-ar", "44100", "-ac", "2",
            "-f", "mp3", "pipe:1",
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stream_start = time.time()
        last_position_write = 0.0
        try:
            while True:
                chunk = await proc.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk
                if on_position and (time.time() - last_position_write) >= 1.0:
                    elapsed = time.time() - stream_start
                    lookup_pl = playlist_for_track_lookup[0] if playlist_for_track_lookup and len(playlist_for_track_lookup) > 0 else playlist
                    # Реальный плейлист: cumulative (сумма длительностей), без больших скачков.
                    # Расписание: фиксированные слоты (9:00, 10:00) — скачки > 600 сек.
                    use_cumulative = False
                    if lookup_pl and len(lookup_pl) > 1 and start_idx < len(lookup_pl):
                        if abs(lookup_pl[1][1] - (lookup_pl[0][1] + lookup_pl[0][2])) < 1:
                            gaps = [lookup_pl[i + 1][1] - lookup_pl[i][1] for i in range(min(20, len(lookup_pl) - 1))]
                            use_cumulative = not gaps or max(gaps) < 600
                    if use_cumulative:
                        lookup_pos = lookup_pl[start_idx][1] + total_seek + elapsed
                        total_dur = lookup_pl[-1][1] + lookup_pl[-1][2] if lookup_pl else None
                        track = _find_track_at_position(lookup_pl, lookup_pos, total_dur)
                    else:
                        track = _find_track_at_position(lookup_pl, stream_start_position_sec + elapsed)
                    pos_for_api = stream_start_position_sec + elapsed
                    try:
                        if track:
                            on_position(pos_for_api, track[0], track[1], track[2])
                        else:
                            on_position(pos_for_api)
                    except Exception:
                        pass
                    last_position_write = time.time()
        finally:
            err = await proc.stderr.read()
            if err:
                import sys
                print(f"[stream] FFmpeg: {err.decode(errors='replace')[:500]}", file=sys.stderr)
            await proc.wait()
    finally:
        try:
            concat_path.unlink(missing_ok=True)
        except OSError:
            pass


async def stream_broadcast_async(playlist: list[tuple], sync_to_moscow: bool = True):
    """
    Async wrapper для stream_broadcast. Мгновенные переходы между файлами — без пауз,
    в отличие от stream_broadcast_ffmpeg (где каждый файл = новый FFmpeg = задержка).
    Для Icecast критично: пауза >1 сек может вызвать отключение источника.
    """
    n = 0
    for chunk in stream_broadcast(playlist, sync_to_moscow):
        yield chunk
        n += 1
        if n % 8 == 0:
            await asyncio.sleep(0)


async def stream_broadcast_ffmpeg(playlist: list[tuple], sync_to_moscow: bool = True):
    """
    Async generator: streams MP3 через FFmpeg subprocess.
    Жёсткая привязка к таймингам эфирной сетки (Москва UTC+3).
    FFmpeg надёжно обрабатывает chunked encoding.
    """
    if not playlist:
        return
    start_idx = 0
    seek_sec = 0
    if sync_to_moscow:
        now_sec = moscow_seconds_now()
        start_idx, seek_sec = _find_current_position(playlist, now_sec)
    idx = start_idx
    first_round = True
    chunk_size = 32 * 1024
    while True:
        try:
            item = playlist[idx]
            path = item[0]
            duration_sec = item[2]
            skip = 0
            if first_round and idx == start_idx and seek_sec > 0:
                skip = min(int(seek_sec), int(duration_sec) - 1)
                skip = max(0, skip)
            if path is None or not path.exists():
                # Файл отсутствует — подставляем тишину (сохраняем синхронизацию)
                silence_path = _get_or_create_silence_mp3(int(duration_sec or 1))
                if silence_path and silence_path.exists():
                    path = silence_path
                    skip = 0
                else:
                    idx = (idx + 1) % len(playlist)
                    if idx == 0:
                        first_round = False
                    continue
            args = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(skip),
                "-i", str(path.resolve()),
                "-c", "copy", "-f", "mp3", "pipe:1",
            ]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            while True:
                chunk = await proc.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            await proc.wait()
        except (GeneratorExit, asyncio.CancelledError):
            raise
        except Exception:
            pass
        idx = (idx + 1) % len(playlist)
        if idx == 0:
            first_round = False
