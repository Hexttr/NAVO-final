"""
Позиция эфира и текущий трек в реальном времени. Icecast source пишет, API читает.
Один источник правды: что играет — пишет тот, кто стримит.
"""
import json
import time
from pathlib import Path

from config import settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STREAM_POSITION_FILE = "stream_position.json"
MAX_AGE_SEC = 20  # данные считаются устаревшими через 20 сек
MAX_AGE_WHEN_TRACK_KNOWN = 45  # когда известен трек — дольше доверяем (стрим пишет каждые 2 сек)


def _get_path() -> Path | None:
    try:
        base = PROJECT_ROOT / settings.upload_dir
        base.mkdir(parents=True, exist_ok=True)
        return base / STREAM_POSITION_FILE
    except OSError:
        return None


def write_stream_position(
    position_sec: float,
    entity_type: str | None = None,
    entity_id: int | None = None,
    title: str | None = None,
) -> None:
    """Записать позицию и текущий трек. Источник стрима знает, что играет — без вычислений."""
    try:
        path = _get_path()
        if path is None:
            return
        data = {
            "position_sec": position_sec,
            "timestamp": time.time(),
        }
        if entity_type is not None and entity_id is not None:
            data["entity_type"] = entity_type
            data["entity_id"] = entity_id
        if title is not None:
            data["title"] = title
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def read_now_playing() -> dict | None:
    """
    Прочитать текущий трек из файла. Возвращает {entity_type, entity_id, title, currentTime}
    если данные свежие, иначе None. API без вычислений — просто читает.
    Когда известен трек (entity_type) — допускаем больший возраст (стрим пишет каждые 2 сек).
    """
    try:
        path = _get_path()
        if path is None or not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = data.get("timestamp", 0)
        max_age = MAX_AGE_WHEN_TRACK_KNOWN if ("entity_type" in data and "entity_id" in data) else MAX_AGE_SEC
        if time.time() - ts > max_age:
            return None
        pos = float(data.get("position_sec", 0))
        h, m, s = int(pos) // 3600, (int(pos) % 3600) // 60, int(pos) % 60
        current_time = f"{h:02d}:{m:02d}:{s:02d}"
        result = {"currentTime": current_time}
        if "entity_type" in data and "entity_id" in data:
            result["entity_type"] = data["entity_type"]
            result["entity_id"] = data["entity_id"]
            result["title"] = data.get("title") or "—"
        return result
    except (OSError, json.JSONDecodeError, (KeyError, TypeError, ValueError)):
        return None


def read_stream_position() -> float | None:
    """
    Прочитать позицию потока. Возвращает position_sec если файл свежий (< MAX_AGE_SEC),
    иначе None.
    """
    try:
        path = _get_path()
        if path is None or not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = data.get("timestamp", 0)
        if time.time() - ts > MAX_AGE_SEC:
            return None
        return float(data.get("position_sec", 0))
    except (OSError, json.JSONDecodeError, (KeyError, TypeError, ValueError)):
        return None
