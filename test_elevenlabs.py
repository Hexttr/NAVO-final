import os
import requests
from dotenv import load_dotenv

load_dotenv("/opt/navo-radio/.env")
api_key = os.environ.get("ELEVENLABS_API_KEY", "")

try:
    print("Testing other endpoints...")
    r = requests.get(
        "https://api.elevenlabs.io/v1/user",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"}
    )
    print(f"User status: {r.status_code}")
    print(f"User body: {r.text[:500]}")
except Exception as e:
    print(f"Exception: {str(e)}")

