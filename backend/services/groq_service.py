import httpx
from config import settings

GROQ_API = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant"


async def generate_dj_text(artist: str, title: str, album: str = "", greeting_allowed: bool = False) -> str:
    prompt = """Ты Диджей NAVO RADIO. Представь трек, который сейчас будет играть в эфире.
Проанализируй Автора, название песни, альбом.
Расскажи о стиле песни, что-то интересное об альбоме или авторе.
5-6 предложений.
ВАЖНО: Здороваться со слушателями можно только в 1 из 10 случаев. В большинстве случаев сразу переходи к представлению трека без приветствия."""

    content = f"Автор: {artist}\nНазвание: {title}\nАльбом: {album or 'не указан'}"
    if greeting_allowed:
        content += "\n\n[Можно начать с приветствия слушателей.]"
    return await _call_groq(prompt, content)


async def generate_news_text(news_items: list[str]) -> str:
    prompt = """Ты ведущий новостей. Поздоровайся со слушателями NAVO RADIO, объяви что начался выпуск новостей и расскажи про события.
Не нумеруй новости, просто перечисли эти новости и используй переходы между ними, чтобы это не было сухим перечислением."""

    content = "\n".join(news_items[:15])
    return await _call_groq(prompt, content)


async def generate_weather_text(weather_data: str) -> str:
    prompt = """Ты ведущий прогноза погоды. Поздоровайся со слушателями NAVO RADIO, объяви что начался прогноз погоды и расскажи про погоду в Душанбе на сегодня и на ближайшую неделю.
В конце добавь фразу про то что слушатели могут и дальше наслаждаться восточной музыкой."""

    return await _call_groq(prompt, weather_data)


async def _call_groq(system_prompt: str, user_content: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            GROQ_API,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.7,
            },
            timeout=60.0,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
