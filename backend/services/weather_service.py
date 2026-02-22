import httpx
from config import settings

# Координаты для надёжного поиска (WeatherAPI иногда не находит город по имени)
CITY_COORDS = {
    "Dushanbe": "38.56,68.78",
    "Moscow": "55.76,37.62",
    "Saint Petersburg": "59.93,30.31",
    "Almaty": "43.22,76.85",
    "Tashkent": "41.31,69.24",
    "Bishkek": "42.87,74.59",
    "Ashgabat": "37.95,58.38",
}


def _get_query(city: str) -> str:
    """Возвращает q для API: координаты если известны, иначе город."""
    return CITY_COORDS.get(city, city)


async def fetch_weather_forecast(city: str = "Dushanbe") -> str:
    """Fetch weather for city. Uses coordinates for reliability."""
    if not settings.weather_api_key:
        raise ValueError("WEATHER_API_KEY не задан в .env")
    q = _get_query(city)
    base_params = {"key": settings.weather_api_key, "q": q, "lang": "ru"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url, extra in [
            ("https://api.weatherapi.com/v1/forecast.json", {"days": 3}),
            ("https://api.weatherapi.com/v1/current.json", {}),
        ]:
            r = await client.get(url, params={**base_params, **extra})
            if r.status_code == 200:
                data = r.json()
                break
            err_body = r.text
            try:
                err_json = r.json()
                err_msg = err_json.get("error", {}).get("message", err_body)
                err_code = err_json.get("error", {}).get("code", "")
            except Exception:
                err_msg = err_body or f"HTTP {r.status_code}"
                err_code = ""
            if url.endswith("current.json"):
                raise ValueError(f"WeatherAPI: {err_msg} (код {err_code})")

    lines = []
    current = data.get("current", {})
    loc = data.get("location", {})
    city_name = loc.get("name", city)
    lines.append(f"Город: {city_name}")
    lines.append(f"Сейчас: {current.get('temp_c')}°C, {current.get('condition', {}).get('text', '')}")
    lines.append(f"Влажность: {current.get('humidity')}%, Ветер: {current.get('wind_kph')} км/ч")

    forecast = data.get("forecast", {}).get("forecastday", [])
    for day in forecast:
        d = day.get("day", {})
        date_str = day.get("date", "")
        lines.append(f"{date_str}: макс {d.get('maxtemp_c')}°C, мин {d.get('mintemp_c')}°C, {d.get('condition', {}).get('text', '')}")

    return "\n".join(lines)
