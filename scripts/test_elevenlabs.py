"""Тест ElevenLabs API. Локально: загружает .env из корня проекта. На сервере: /opt/navo-radio/.env"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Локально — корень проекта; на сервере — /opt/navo-radio
_root = Path(__file__).resolve().parent.parent
_env = _root / ".env"
if _env.exists():
    load_dotenv(_env)
else:
    load_dotenv("/opt/navo-radio/.env")

api_key = os.environ.get("ELEVENLABS_API_KEY", "")

try:
    import requests
    print("Testing ElevenLabs API...")
    r = requests.get(
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        timeout=10,
    )
    print(f"User status: {r.status_code}")
    print(f"User body: {r.text[:500]}")
except Exception as e:
    print(f"Exception: {str(e)}")
