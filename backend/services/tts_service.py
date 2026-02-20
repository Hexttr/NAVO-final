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
        return await _list_elevenlabs_voices(db)
    return EDGE_VOICES.copy()


def _get_elevenlabs_api_key(db: Session | None = None) -> str:
    """API key from settings (elevenlabs_api_key_frontend or elevenlabs_api_key) or os.environ."""
    if db:
        key = get(db, "elevenlabs_api_key_frontend") or get(db, "elevenlabs_api_key") or ""
        if key:
            return key
    key = getattr(settings, "elevenlabs_api_key", None) or ""
    if not key:
        import os
        key = os.environ.get("ELEVENLABS_API_KEY", "")
    return key or ""


async def _list_elevenlabs_voices(db: Session) -> list[tuple[str, str]]:
    """Fetch ElevenLabs voices via backend (avoids CORS when frontend would call directly)."""
    api_key = _get_elevenlabs_api_key(db)
    default_voice_id = "pFZP5JQG7iQjIQuC4Bku"
    if not api_key:
        return [(default_voice_id, "Укажите ключ ElevenLabs в Настройках")]
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": api_key},
                timeout=15,
            )
            if not r.is_success:
                return [(default_voice_id, "ElevenLabs (дефолтный голос)")]
            data = r.json()
            voices = data.get("voices", [])
            return [(v["voice_id"], v.get("name") or v["voice_id"]) for v in voices[:50]]
    except Exception:
        return [(default_voice_id, "ElevenLabs (базовый голос)")]


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
        try:
            return await _tts_elevenlabs(text, output_path, voice, db)
        except Exception:
            # ElevenLabs blocks server IP (302 → country restrictions) — fallback to Edge TTS
            return await _tts_edge(text, output_path, "ru-RU-DmitryNeural", rate, volume, pitch)
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


async def _tts_elevenlabs(text: str, output_path: Path, voice_id: str, db: Session | None = None) -> Path:
    api_key = _get_elevenlabs_api_key(db)
    if not api_key:
        raise RuntimeError("Укажите API ключ ElevenLabs в Настройках")
    # Edge TTS voice IDs (ru-RU-*) are invalid for ElevenLabs — use default
    if not voice_id or "-" in voice_id and voice_id.startswith("ru-"):
        voice_id = "pFZP5JQG7iQjIQuC4Bku"

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
