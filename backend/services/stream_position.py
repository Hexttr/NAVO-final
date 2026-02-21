"""
Позиция эфира в реальном времени. Icecast source пишет, API читает.
Позволяет показывать «Сейчас играет» синхронно с реальным потоком.
"""
import json
import time
from pathlib import Path

from config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STREAM_POSITION_FILE = "stream_position.json"
MAX_AGE_SEC = 20  # позиция считается устаревшей через 20 сек


def _get_path() -> Path:
    base = PROJECT_ROOT / settings.upload_dir
    base.mkdir(parents=True, exist_ok=True)
    return base / STREAM_POSITION_FILE


def write_stream_position(position_sec: float) -> None:
    """Записать текущую позицию потока (секунды от полуночи МСК)."""
    try:
        path = _get_path()
        data = {"position_sec": position_sec, "timestamp": time.time()}
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def read_stream_position() -> float | None:
    """
    Прочитать позицию потока. Возвращает position_sec если файл свежий (< MAX_AGE_SEC),
    иначе None.
    """
    try:
        path = _get_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = data.get("timestamp", 0)
        if time.time() - ts > MAX_AGE_SEC:
            return None
        return float(data.get("position_sec", 0))
    except (OSError, json.JSONDecodeError, (KeyError, TypeError, ValueError)):
        return None
