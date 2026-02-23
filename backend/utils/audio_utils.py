"""Утилиты для аудио: усиление громкости при загрузке."""
import subprocess
from pathlib import Path


def apply_volume_boost(path: Path, multiplier: float) -> bool:
    """
    Применить усиление громкости к MP3 через ffmpeg.
    multiplier: 1.0 = без изменений, 1.5 ≈ +3.5 dB
    Перезаписывает файл. Возвращает True при успехе.
    """
    if not path.exists() or multiplier <= 0 or abs(multiplier - 1.0) < 0.01:
        return True
    try:
        tmp = path.with_suffix(".tmp.mp3")
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(path),
                "-af", f"volume={multiplier}",
                "-c:a", "libmp3lame", "-q:a", "2",
                str(tmp),
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if r.returncode == 0 and tmp.exists():
            tmp.replace(path)
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return False
