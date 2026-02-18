#!/usr/bin/env python3
"""
NAVO RADIO — Source для Icecast.
Читает эфир из БД, стримит через FFmpeg в Icecast.
Один процесс = один поток = все слушатели слышат одно и то же.
"""
import asyncio
import os
import sys
import signal

# Запуск из backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from services.streamer_service import (
    get_playlist_with_times,
    stream_broadcast_async,
    stream_broadcast_ffmpeg_concat,
    moscow_date,
    _find_current_position,
    get_broadcast_schedule_hash,
)

ICECAST_HOST = os.environ.get("ICECAST_HOST", "127.0.0.1")
ICECAST_PORT = int(os.environ.get("ICECAST_PORT", "8001"))
ICECAST_MOUNT = os.environ.get("ICECAST_MOUNT", "live")
ICECAST_SOURCE_PASSWORD = os.environ.get("ICECAST_SOURCE_PASSWORD", "navo-icecast-source-2024")
# STREAM_MODE=ffmpeg_concat — единый формат, без обрезки на стыках; async — сырая конкатенация (обрезает DJ)
STREAM_MODE = os.environ.get("STREAM_MODE", "ffmpeg_concat").lower()
CHUNK_SIZE = 32 * 1024

shutdown = False


def main():
    global shutdown

    def sig_handler(signum, frame):
        global shutdown
        shutdown = True

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    async def run_source():
        from datetime import datetime, timezone, timedelta
        schedule_changed = False
        while not shutdown:
            db = SessionLocal()
            try:
                today = moscow_date()
                playlist = get_playlist_with_times(db, today)
                current_hash = get_broadcast_schedule_hash(db, today)
            finally:
                db.close()

            if not playlist:
                print("Нет эфира на сегодня. Ожидание 60 сек...")
                await asyncio.sleep(60)
                continue

            now = datetime.now(timezone(timedelta(hours=3)))
            now_sec = now.hour * 3600 + now.minute * 60 + now.second
            start_idx, seek_sec = _find_current_position(playlist, now_sec)
            print(f"Стриминг эфира в Icecast ({len(playlist)} треков, mode={STREAM_MODE}), старт: idx={start_idx} seek={seek_sec}s ({now.hour:02d}:{now.minute:02d}:{now.second:02d} МСК)")
            icecast_url = f"icecast://source:{ICECAST_SOURCE_PASSWORD}@{ICECAST_HOST}:{ICECAST_PORT}/{ICECAST_MOUNT}"
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-re", "-f", "mp3", "-i", "pipe:0",
                "-c", "copy", "-content_type", "audio/mpeg",
                "-f", "mp3", icecast_url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            stream_gen = stream_broadcast_ffmpeg_concat if STREAM_MODE == "ffmpeg_concat" else stream_broadcast_async

            async def stream_chunks():
                async for chunk in stream_gen(playlist, sync_to_moscow=True):
                    if shutdown:
                        return
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()

            stream_task = asyncio.create_task(stream_chunks())

            async def check_schedule():
                nonlocal schedule_changed
                while not shutdown and not stream_task.done():
                    await asyncio.sleep(30)
                    if shutdown or stream_task.done():
                        return
                    db2 = SessionLocal()
                    try:
                        new_hash = get_broadcast_schedule_hash(db2, moscow_date())
                        if new_hash != current_hash:
                            schedule_changed = True
                            stream_task.cancel()
                            return
                    finally:
                        db2.close()

            checker_task = asyncio.create_task(check_schedule())

            try:
                await stream_task
            except asyncio.CancelledError:
                if schedule_changed:
                    print("Эфирная сетка изменена — перезагрузка стрима...")
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                checker_task.cancel()
                try:
                    await checker_task
                except asyncio.CancelledError:
                    pass
                try:
                    proc.stdin.close()
                    await proc.wait()
                except Exception:
                    pass

            if shutdown:
                break
            if not schedule_changed:
                print("Переподключение к Icecast через 5 сек...")
                await asyncio.sleep(5)
            schedule_changed = False

    asyncio.run(run_source())


if __name__ == "__main__":
    main()
