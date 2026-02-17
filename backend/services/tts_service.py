import asyncio
import edge_tts
from pathlib import Path
from config import settings

# Edge TTS Russian voices (can be extended)
RUSSIAN_VOICES = [
    ("ru-RU-DmitryNeural", "Дмитрий (мужской)"),
    ("ru-RU-SvetlanaNeural", "Светлана (женский)"),
]


async def list_voices() -> list[tuple[str, str]]:
    """Return available Russian voices for selection."""
    return RUSSIAN_VOICES.copy()


async def text_to_speech(
    text: str,
    output_path: Path,
    voice: str = "ru-RU-DmitryNeural",
    rate: str | None = None,
    volume: str | None = None,
    pitch: str | None = None,
) -> Path:
    """Convert text to speech using Edge TTS. Saves MP3 to output_path.
    rate: +20% быстрее, -50% медленнее (по умолчанию из config)
    volume: +50% громче, -50% тише
    pitch: +50Hz выше, -50Hz ниже
    """
    if settings.tts_provider != "edge-tts":
        raise NotImplementedError("Only edge-tts is supported. Set TTS_PROVIDER=edge-tts")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=rate or getattr(settings, "tts_rate", "+0%"),
        volume=volume or getattr(settings, "tts_volume", "+0%"),
        pitch=pitch or getattr(settings, "tts_pitch", "+0Hz"),
    )
    await communicate.save(str(output_path))
    return output_path
