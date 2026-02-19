import httpx
from config import settings


async def fetch_weather_forecast(city: str = "Dushanbe") -> str:
    """Fetch weather for city. city: name for WeatherAPI (Dushanbe, Moscow, etc.)."""
    url = "https://api.weatherapi.com/v1/forecast.json"
    async with httpx.AsyncClient() as client:
        r = await client.get(
            url,
            params={
                "key": settings.weather_api_key,
                "q": city,
                "days": 7,
                "lang": "ru",
            },
        )
        r.raise_for_status()
        data = r.json()

    lines = []
    current = data.get("current", {})
    loc = data.get("location", {})
    lines.append(f"Город: {loc.get('name', 'Душанбе')}")
    lines.append(f"Сейчас: {current.get('temp_c')}°C, {current.get('condition', {}).get('text', '')}")
    lines.append(f"Влажность: {current.get('humidity')}%, Ветер: {current.get('wind_kph')} км/ч")

    forecast = data.get("forecast", {}).get("forecastday", [])
    for day in forecast:
        d = day.get("day", {})
        date_str = day.get("date", "")
        lines.append(f"{date_str}: макс {d.get('maxtemp_c')}°C, мин {d.get('mintemp_c')}°C, {d.get('condition', {}).get('text', '')}")

    return "\n".join(lines)
