import asyncio
import edge_tts
import httpx
from pathlib import Path
from config import settings
from sqlalchemy.orm import Session

from services.settings_service import get

# Edge TTS Russian voices
EDGE_VOICES = [
    ("ru-RU-DmitryNeural", "Дмитрий (мужской)"),
    ("ru-RU-SvetlanaNeural", "Светлана (женский)"),
]


async def list_voices(db: Session) -> list[tuple[str, str]]:
    """Return voices for current TTS provider."""
    provider = get(db, "tts_provider") or "edge-tts"
    if provider == "elevenlabs":
        return await _list_elevenlabs_voices()
    return EDGE_VOICES.copy()


async def _list_elevenlabs_voices() -> list[tuple[str, str]]:
    api_key = getattr(settings, "elevenlabs_api_key", None) or ""
    if not api_key:
        return [("", "ElevenLabs: добавьте ELEVENLABS_API_KEY в .env")]
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            voices = data.get("voices", [])
            return [(v["voice_id"], v.get("name", v["voice_id"])) for v in voices[:50]]
    except Exception as e:
        return [("", f"ElevenLabs: {str(e)[:80]}")]


async def text_to_speech(
    text: str,
    output_path: Path,
    voice: str = "ru-RU-DmitryNeural",
    rate: str | None = None,
    volume: str | None = None,
    pitch: str | None = None,
    db: Session | None = None,
) -> Path:
    """Convert text to speech. Provider from settings (Edge TTS or ElevenLabs)."""
    provider = "edge-tts"
    if db:
        provider = get(db, "tts_provider") or "edge-tts"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if provider == "elevenlabs":
        return await _tts_elevenlabs(text, output_path, voice)
    return await _tts_edge(text, output_path, voice, rate, volume, pitch)


async def _tts_edge(
    text: str, output_path: Path, voice: str,
    rate: str | None, volume: str | None, pitch: str | None,
) -> Path:
    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=rate or getattr(settings, "tts_rate", "+0%"),
        volume=volume or getattr(settings, "tts_volume", "+0%"),
        pitch=pitch or getattr(settings, "tts_pitch", "+0Hz"),
    )
    await communicate.save(str(output_path))
    return output_path


async def _tts_elevenlabs(text: str, output_path: Path, voice_id: str) -> Path:
    api_key = getattr(settings, "elevenlabs_api_key", None) or ""
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY не задан в .env")
    if not voice_id:
        raise ValueError("Выберите голос ElevenLabs в настройках")

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
            },
            timeout=60,
        )
        r.raise_for_status()
        output_path.write_bytes(r.content)
    return output_path
