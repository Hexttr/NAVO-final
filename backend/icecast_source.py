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
from services.streamer_service import get_playlist_with_times, stream_broadcast_ffmpeg, moscow_date

ICECAST_HOST = os.environ.get("ICECAST_HOST", "127.0.0.1")
ICECAST_PORT = int(os.environ.get("ICECAST_PORT", "8001"))
ICECAST_MOUNT = os.environ.get("ICECAST_MOUNT", "live")
ICECAST_SOURCE_PASSWORD = os.environ.get("ICECAST_SOURCE_PASSWORD", "navo-icecast-source-2024")
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
        while not shutdown:
            db = SessionLocal()
            try:
                today = moscow_date()
                playlist = get_playlist_with_times(db, today)
            finally:
                db.close()

            if not playlist:
                print("Нет эфира на сегодня. Ожидание 60 сек...")
                await asyncio.sleep(60)
                continue

            print(f"Стриминг эфира в Icecast ({len(playlist)} треков)...")
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
            try:
                async for chunk in stream_broadcast_ffmpeg(playlist, sync_to_moscow=True):
                    if shutdown:
                        break
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                try:
                    proc.stdin.close()
                    await proc.wait()
                except Exception:
                    pass

            if shutdown:
                break
            print("Переподключение к Icecast через 5 сек...")
            await asyncio.sleep(5)

    asyncio.run(run_source())


if __name__ == "__main__":
    main()
