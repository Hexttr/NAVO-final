"""
Stream broadcast playlist as continuous MP3.
Синхронизация по московскому времени: воспроизведение с текущего момента эфира.
"""
import asyncio
import tempfile
from datetime import date, datetime, timezone, timedelta

from pathlib import Path

from sqlalchemy.orm import Session

from config import settings
from models import BroadcastItem, Song, News, Weather, Podcast, Intro

# Москва UTC+3 (без перехода на летнее время с 2011)
MOSCOW_TZ = timezone(timedelta(hours=3))


def _moscow_now() -> datetime:
    return datetime.now(MOSCOW_TZ)


def moscow_date() -> date:
    """Текущая дата по Москве (UTC+3). Для выбора эфира и синхронизации."""
    return _moscow_now().date()


def _parse_time(t: str) -> int:
    """Parse HH:MM:SS to seconds since midnight."""
    parts = t.split(":")
    if len(parts) != 3:
        return 0
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

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


CHUNK_SIZE = 32 * 1024  # 32 KB


def get_playlist_with_times(db: Session, broadcast_date: date) -> list[tuple[Path, int, float, str]]:
    """
    Get playlist: list of (path, start_sec, duration_sec, entity_type).
    start_sec = seconds since midnight (Moscow).
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
    for item in items:
        p = _get_audio_path(db, item.entity_type, item.entity_id)
        if p:
            start_sec = _parse_time(item.start_time)
            dur = float(item.duration_seconds or 0)
            result.append((p, start_sec, dur, item.entity_type))
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
        now = _moscow_now()
        now_sec = now.hour * 3600 + now.minute * 60 + now.second
        start_idx, seek_sec = _find_current_position(playlist, now_sec)
    idx = start_idx
    first_round = True
    while True:
        try:
            item = playlist[idx]
            path = item[0]
            duration_sec = item[2]
            if not path.exists():
                idx += 1
                if idx >= len(playlist):
                    idx = 0
                    first_round = False
                continue
            skip_bytes = 0
            if first_round and idx == start_idx and seek_sec > 0 and duration_sec > 0:
                try:
                    size = path.stat().st_size
                    skip_bytes = int((seek_sec / duration_sec) * size)
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
                        if not (first_round and idx == start_idx):
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


def _create_concat_file(playlist: list[tuple]) -> Path | None:
    """
    Создаёт временный concat-файл для FFmpeg.
    Повторяем плейлист 2 раза для бесшовного перехода в полночь.
    """
    lines = ["ffconcat version 1.0", ""]
    for path, _, _, _ in playlist:
        if path.exists():
            abs_path = str(path.resolve()).replace("'", "'\\''")
            lines.append(f"file '{abs_path}'")
    if len(lines) <= 2:
        return None
    # Дублируем плейлист для зацикливания (2 суток)
    for path, _, _, _ in playlist:
        if path.exists():
            abs_path = str(path.resolve()).replace("'", "'\\''")
            lines.append(f"file '{abs_path}'")
    fd, p = tempfile.mkstemp(suffix=".concat", prefix="navo_")
    with open(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return Path(p)


async def stream_broadcast_ffmpeg_concat(playlist: list[tuple], sync_to_moscow: bool = True):
    """
    Один FFmpeg с concat — бесшовные переходы, без пауз между треками.
    Критично для Icecast: пауза >1 сек вызывает отключение источника.
    """
    if not playlist:
        return
    now_sec = 0
    if sync_to_moscow:
        now = _moscow_now()
        now_sec = now.hour * 3600 + now.minute * 60 + now.second
    start_idx, seek_sec = _find_current_position(playlist, now_sec)
    # Seek в concat = сумма длительностей существующих файлов до start_idx + seek_sec
    total_seek = 0
    for i in range(start_idx):
        if playlist[i][0].exists():
            total_seek += int(playlist[i][2])
    if start_idx < len(playlist) and playlist[start_idx][0].exists():
        total_seek += seek_sec
    concat_path = _create_concat_file(playlist)
    if not concat_path or not concat_path.exists():
        return
    chunk_size = 32 * 1024
    try:
        args = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(total_seek),
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-c", "copy", "-f", "mp3", "pipe:1",
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            while True:
                chunk = await proc.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
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
        now = _moscow_now()
        now_sec = now.hour * 3600 + now.minute * 60 + now.second
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
            if not path.exists():
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
