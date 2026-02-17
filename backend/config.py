from pathlib import Path
from pydantic_settings import BaseSettings

_env_path = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    jamendo_client_id: str = ""
    groq_api_key: str = ""
    weather_api_key: str = ""
    tts_provider: str = "edge-tts"
    elevenlabs_api_key: str | None = None
    database_url: str = "sqlite:///./navo.db"
    upload_dir: str = "uploads"

    class Config:
        env_file = str(_env_path)
        extra = "ignore"


settings = Settings()
