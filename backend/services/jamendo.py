import httpx
from pathlib import Path
from config import settings

JAMENDO_API = "https://api.jamendo.com/v3.0"


async def search_tracks(query: str, limit: int = 20) -> list[dict]:
    """Search Jamendo for tracks. Query: eastern, tajik, asian music etc."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{JAMENDO_API}/tracks",
            params={
                "client_id": settings.jamendo_client_id,
                "search": query,
                "limit": limit,
                "format": "json",
                "include": "musicinfo",
            },
        )
        r.raise_for_status()
        data = r.json()
        return data.get("results", [])


async def download_track(audio_url: str, save_path: Path) -> Path:
    """Download MP3 from Jamendo URL to local path."""
    headers = {
        "User-Agent": "NAVO-Radio/1.0",
        "Referer": "https://www.jamendo.com/",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        r = await client.get(audio_url, headers=headers)
        r.raise_for_status()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(r.content)
    return save_path


class JamendoService:
    SEARCH_QUERIES = [
        "tajik music",
        "eastern music",
        "central asian",
        "persian music",
        "uzbek music",
    ]

    @staticmethod
    async def search_and_get_tracks(limit_per_query: int = 4) -> list[dict]:
        """Search multiple queries and return combined unique tracks."""
        all_tracks = []
        seen_ids = set()
        async with httpx.AsyncClient() as client:
            for q in JamendoService.SEARCH_QUERIES:
                try:
                    r = await client.get(
                        f"{JAMENDO_API}/tracks",
                        params={
                            "client_id": settings.jamendo_client_id,
                            "search": q,
                            "limit": limit_per_query,
                            "format": "json",
                            "include": "musicinfo",
                        },
                    )
                    r.raise_for_status()
                    results = r.json().get("results", [])
                    for t in results:
                        if t["id"] not in seen_ids:
                            seen_ids.add(t["id"])
                            all_tracks.append(t)
                except Exception:
                    continue
        return all_tracks
