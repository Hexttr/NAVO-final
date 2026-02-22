import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings

_env_path = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    jamendo_client_id: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    weather_api_key: str = ""
    tts_provider: str = "edge-tts"
    tts_rate: str = "+25%"  # скорость: +20% быстрее, -50% медленнее
    tts_volume: str = "+0%"  # громкость: +50% громче, -50% тише
    tts_pitch: str = "+0Hz"  # тон: +50Hz выше, -50Hz ниже
    elevenlabs_api_key: str | None = Field(default=None, validation_alias="ELEVENLABS_API_KEY")
    database_url: str = "sqlite:///./navo.db"
    upload_dir: str = "uploads"
    base_url: str = "https://navoradio.com"
    # URL стрима для плеера (относительный /stream или полный https://...)
    stream_url: str = "/stream"
    # STREAM_BITRATE: 128k, 256k, 320k, 512k — выше = лучше качество, ~4× трафик
    stream_bitrate: str = "256k"
    # Смещение эфира в секундах: +120 = на 2 мин вперёд (если запаздывает), -60 = на 1 мин назад
    sync_offset_seconds: int = 0
    # Московское время: False = системное (сервер в Europe/Moscow), True = worldtimeapi.org
    use_external_time: bool = False

    class Config:
        env_file = str(_env_path)
        extra = "ignore"


settings = Settings()
