#!/usr/bin/env python3
"""
NAVO RADIO — Source для Icecast.
Читает эфир из БД, стримит через FFmpeg в Icecast.
Один процесс = один поток = все слушатели слышат одно и то же.
Пишет позицию в stream_position.json для синхронизации «Сейчас играет».
"""
import asyncio
import os
import sys
import signal
import time

# Запуск из backend/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from services.stream_position import write_stream_position
from services.streamer_service import (
    get_playlist_with_times,
    stream_broadcast_async,
    stream_broadcast_ffmpeg_concat,
    moscow_date,
    moscow_seconds_now,
    ensure_broadcast_for_date,
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


def _log(msg: str) -> None:
    print(f"[icecast-source] {msg}", flush=True)


def main():
    global shutdown

    def sig_handler(signum, frame):
        global shutdown
        shutdown = True

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    async def run_source():
        schedule_changed = False
        retry_delay = 5
        while not shutdown:
            try:
                db = SessionLocal()
                try:
                    today = moscow_date()
                    copied = ensure_broadcast_for_date(db, today)
                    if copied:
                        _log(f"Эфир скопирован на {today} (админ не сформировал)")
                    playlist = get_playlist_with_times(db, today)
                    current_hash = get_broadcast_schedule_hash(db, today)
                finally:
                    db.close()
            except Exception as e:
                _log(f"Ошибка загрузки эфира: {e}")
                await asyncio.sleep(min(retry_delay, 60))
                retry_delay = min(retry_delay * 2, 60)
                continue
            retry_delay = 5

            if not playlist:
                _log("Нет эфира (ни на сегодня, ни на предыдущие дни). Ожидание 60 сек...")
                await asyncio.sleep(60)
                continue

            try:
                now_sec = moscow_seconds_now()
                start_idx, seek_sec = _find_current_position(playlist, now_sec)
                stream_start_position = now_sec
                stream_start_wall_time = time.time()
            except Exception as e:
                _log(f"Ошибка определения позиции: {e}")
                await asyncio.sleep(10)
                continue

            h, m, s = now_sec // 3600, (now_sec % 3600) // 60, now_sec % 60
            _log(f"Стриминг эфира в Icecast ({len(playlist)} треков, mode={STREAM_MODE}), старт: idx={start_idx} seek={seek_sec}s ({h:02d}:{m:02d}:{s:02d} МСК)")
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

            use_ffmpeg_concat = STREAM_MODE == "ffmpeg_concat"
            # Плейлист с реальными длительностями — для точного «Сейчас играет». Строится в фоне.
            playlist_ref = [playlist]

            async def build_real_playlist():
                try:
                    db_real = SessionLocal()
                    pl = get_playlist_with_times(db_real, today, use_real_durations=True)
                    db_real.close()
                    playlist_ref[0] = pl
                    _log("Плейлист с реальными длительностями готов для now-playing")
                except Exception as e:
                    _log(f"Ошибка построения плейлиста с реальными длительностями: {e}")

            if use_ffmpeg_concat:
                asyncio.create_task(build_real_playlist())

            async def stream_chunks():
                if use_ffmpeg_concat:
                    gen = stream_broadcast_ffmpeg_concat(
                        playlist, sync_to_moscow=True, on_position=write_stream_position,
                        playlist_for_track_lookup=playlist_ref,
                    )
                else:
                    gen = stream_broadcast_async(playlist, sync_to_moscow=True)
                async for chunk in gen:
                    if shutdown:
                        return
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()

            stream_task = asyncio.create_task(stream_chunks())

            async def write_position_loop():
                """Позиция для async mode (ffmpeg_concat пишет через on_position)."""
                while not shutdown and not stream_task.done():
                    await asyncio.sleep(2)
                    if shutdown or stream_task.done():
                        return
                    pos = stream_start_position + (time.time() - stream_start_wall_time)
                    write_stream_position(pos)

            position_task = asyncio.create_task(write_position_loop()) if not use_ffmpeg_concat else None

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
                    except Exception as e:
                        _log(f"Ошибка проверки расписания: {e}")
                    finally:
                        db2.close()

            checker_task = asyncio.create_task(check_schedule())

            async def shutdown_watchdog():
                """При SIGTERM — отменить stream_task для быстрого выхода."""
                while not shutdown and not stream_task.done():
                    await asyncio.sleep(1)
                if shutdown and not stream_task.done():
                    stream_task.cancel()

            watchdog_task = asyncio.create_task(shutdown_watchdog())
            try:
                await stream_task
            except asyncio.CancelledError:
                if schedule_changed:
                    _log("Эфирная сетка изменена — перезагрузка стрима...")
            except (BrokenPipeError, ConnectionResetError) as e:
                _log(f"Соединение с Icecast разорвано: {e}")
            except Exception as e:
                _log(f"Ошибка стриминга: {e}")
            finally:
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass
                if position_task:
                    position_task.cancel()
                    try:
                        await position_task
                    except asyncio.CancelledError:
                        pass
                checker_task.cancel()
                try:
                    await checker_task
                except asyncio.CancelledError:
                    pass
                try:
                    proc.stdin.close()
                    exit_code = await proc.wait()
                    if exit_code != 0:
                        err = await proc.stderr.read() if proc.stderr else b""
                        if err:
                            _log(f"FFmpeg exit {exit_code}: {err.decode(errors='replace')[:500]}")
                except Exception as e:
                    _log(f"Ошибка при закрытии FFmpeg: {e}")

            if shutdown:
                break
            if not schedule_changed:
                _log("Переподключение к Icecast через 5 сек...")
                await asyncio.sleep(5)
            schedule_changed = False

    asyncio.run(run_source())


if __name__ == "__main__":
    main()
