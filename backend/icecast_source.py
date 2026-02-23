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
from utils.time_utils import sec_to_hms, time_str
from services.streamer_service import (
    get_playlist_with_times,
    stream_broadcast_async,
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
        max_retry_delay = 60
        consecutive_failures = 0
        max_consecutive_failures = 10
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
                consecutive_failures += 1
                _log(f"Ошибка загрузки эфира ({consecutive_failures}/{max_consecutive_failures}): {e}")
                if consecutive_failures >= max_consecutive_failures:
                    _log("Превышен лимит попыток. Пауза 60 сек перед сбросом счётчика.")
                    await asyncio.sleep(max_retry_delay)
                    consecutive_failures = 0
                else:
                    await asyncio.sleep(min(retry_delay, max_retry_delay))
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                continue
            retry_delay = 5
            consecutive_failures = 0

            if not playlist:
                _log(f"Нет эфира на {today}. Админка → выберите дату с эфиром → «Скопировать эфир на завтра». Ожидание 60 сек...")
                await asyncio.sleep(60)
                continue

            try:
                now_sec = moscow_seconds_now()
                start_idx, seek_sec = _find_current_position(playlist, now_sec)
            except Exception as e:
                _log(f"Ошибка определения позиции: {e}")
                await asyncio.sleep(10)
                continue

            _log(f"Стриминг эфира в Icecast ({len(playlist)} треков), старт: idx={start_idx} seek={seek_sec}s ({time_str(*sec_to_hms(now_sec))} МСК)")
            icecast_url = f"icecast://source:{ICECAST_SOURCE_PASSWORD}@{ICECAST_HOST}:{ICECAST_PORT}/{ICECAST_MOUNT}"
            try:
                from urllib.request import urlopen
                with urlopen(f"http://{ICECAST_HOST}:{ICECAST_PORT}/", timeout=2) as r:
                    _log(f"Icecast доступен (HTTP {r.status})")
            except Exception as e:
                _log(f"ВНИМАНИЕ: Icecast не отвечает на {ICECAST_HOST}:{ICECAST_PORT} — {e}. Запустите dev\\start_icecast.bat")
            bitrate = "256k"
            try:
                from config import settings
                bitrate = getattr(settings, "stream_bitrate", "256k") or "256k"
            except Exception:
                pass
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-re", "-f", "mp3", "-i", "pipe:0",
                "-c:a", "libmp3lame", "-b:a", bitrate, "-ar", "44100", "-ac", "2",
                "-content_type", "audio/mpeg", "-f", "mp3", icecast_url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            async def log_ffmpeg_stderr():
                """Логировать stderr FFmpeg в реальном времени (ошибки подключения к Icecast)."""
                if proc.stderr:
                    try:
                        while True:
                            line = await proc.stderr.readline()
                            if not line:
                                break
                            msg = line.decode(errors="replace").strip()
                            if msg:
                                _log(f"FFmpeg: {msg}")
                    except Exception:
                        pass

            asyncio.create_task(log_ffmpeg_stderr())

            # playlist — по расписанию (start_time из БД), иначе _find_current_position даёт неверный слот
            async def stream_chunks():
                gen = stream_broadcast_async(
                    playlist,
                    sync_to_moscow=True,
                    on_track_switch=write_stream_position,
                )
                async for chunk in gen:
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
                checker_task.cancel()
                try:
                    await checker_task
                except asyncio.CancelledError:
                    pass
                try:
                    proc.stdin.close()
                    if shutdown and proc.returncode is None:
                        proc.terminate()
                    exit_code = await proc.wait()
                    if exit_code != 0 and not shutdown:
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
