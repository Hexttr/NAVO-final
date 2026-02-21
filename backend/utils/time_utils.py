"""
Общие утилиты для работы со временем эфира.
Формат HH:MM:SS — секунды от полуночи.
"""


def parse_time(t: str) -> int:
    """Parse HH:MM:SS to seconds since midnight."""
    parts = t.split(":")
    if len(parts) != 3:
        return 0
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def time_str(h: int, m: int, s: int = 0) -> str:
    """Format hours, minutes, seconds as HH:MM:SS."""
    return f"{h:02d}:{m:02d}:{s:02d}"


def sec_to_hms(sec: int) -> tuple[int, int, int]:
    """Convert seconds since midnight to (h, m, s)."""
    sec = int(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return h, m, s
