"""
Московское время из внешнего API (worldtimeapi.org).
Не зависит от системного времени сервера. Кэш 60 сек.
"""
import json
import time
from datetime import date, datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

_CACHE_SEC = 0
_CACHE_DATE: date | None = None
_CACHE_SECONDS: int | None = None
_CACHE_TTL = 60  # секунд


def _fetch_moscow_from_api() -> tuple[date, int] | None:
    """(date, seconds) из worldtimeapi.org. None при ошибке."""
    global _CACHE_SEC, _CACHE_DATE, _CACHE_SECONDS
    now = time.time()
    if _CACHE_DATE is not None and _CACHE_SECONDS is not None and (now - _CACHE_SEC) < _CACHE_TTL:
        return _CACHE_DATE, _CACHE_SECONDS
    try:
        req = Request(
            "https://worldtimeapi.org/api/timezone/Europe/Moscow",
            headers={"User-Agent": "NAVO-Radio/1.0"},
        )
        with urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
        dt_str = data.get("datetime")
        if not dt_str:
            return None
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        d = dt.date()
        sec = dt.hour * 3600 + dt.minute * 60 + dt.second
        _CACHE_SEC = now
        _CACHE_DATE = d
        _CACHE_SECONDS = sec
        return d, sec
    except (URLError, HTTPError, ValueError, KeyError, OSError) as e:
        import sys
        print(f"[time_service] worldtimeapi.org недоступен, используется системное время: {e}", file=sys.stderr, flush=True)
        return None


def moscow_seconds_from_api() -> int | None:
    """Секунды от полуночи МСК. None при ошибке."""
    r = _fetch_moscow_from_api()
    return r[1] if r else None


def moscow_date_from_api() -> date | None:
    """Дата по МСК. None при ошибке."""
    r = _fetch_moscow_from_api()
    return r[0] if r else None
