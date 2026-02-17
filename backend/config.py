from pathlib import Path
from pydantic_settings import BaseSettings

_env_path = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    jamendo_client_id: str = ""
    groq_api_key: str = ""
    weather_api_key: str = ""
    tts_provider: str = "edge-tts"
    tts_rate: str = "+25%"  # скорость: +20% быстрее, -50% медленнее
    tts_volume: str = "+0%"  # громкость: +50% громче, -50% тише
    tts_pitch: str = "+0Hz"  # тон: +50Hz выше, -50Hz ниже
    elevenlabs_api_key: str | None = None
    database_url: str = "sqlite:///./navo.db"
    upload_dir: str = "uploads"

    class Config:
        env_file = str(_env_path)
        extra = "ignore"


settings = Settings()
