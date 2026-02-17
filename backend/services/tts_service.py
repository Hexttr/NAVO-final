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


async def text_to_speech(text: str, output_path: Path, voice: str = "ru-RU-DmitryNeural") -> Path:
    """Convert text to speech using Edge TTS. Saves MP3 to output_path."""
    if settings.tts_provider != "edge-tts":
        # Placeholder for ElevenLabs - add later
        raise NotImplementedError("Only edge-tts is supported. Set TTS_PROVIDER=edge-tts")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))
    return output_path
