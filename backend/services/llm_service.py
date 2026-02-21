"""
LLM service: routes to Groq or OpenAI based on settings.
Uses prompts from settings (editable in admin).
"""
from sqlalchemy.orm import Session
from services.settings_service import get
from services.groq_service import _call_groq
from config import settings as config_settings


async def generate_dj_text(
    db: Session, artist: str, title: str, album: str = "", greeting_allowed: bool = False
) -> str:
    prompt = get(db, "llm_prompt_dj")
    if not prompt:
        prompt = """Ты Диджей NAVO RADIO. Представь трек, который сейчас будет играть в эфире.
Проанализируй Автора, название песни, альбом.
Расскажи о стиле песни, что-то интересное об альбоме или авторе.
3-4 предложения.
ВАЖНО: Здороваться со слушателями можно только в 1 из 10 случаев. В большинстве случаев сразу переходи к представлению трека без приветствия."""
    content = f"Автор: {artist}\nНазвание: {title}\nАльбом: {album or 'не указан'}"
    if greeting_allowed:
        content += "\n\n[Можно начать с приветствия слушателей.]"
    return await _call_llm(db, prompt, content)


async def generate_news_text(db: Session, news_items: list[str]) -> str:
    prompt = get(db, "llm_prompt_news")
    if not prompt:
        prompt = """Ты ведущий новостей NAVO RADIO. Кратко поздоровайся (1 фраза) и СРАЗУ переходи к новостям.
ОБЯЗАТЕЛЬНО перескажи ВСЕ новости из списка ниже — это реальные события, не придумывай общие фразы.
Используй живые переходы между новостями, не нумеруй. Без реального контента из списка не пиши."""
    content = "\n".join(news_items[:15])
    if not content or not content.strip():
        raise ValueError("Нет новостей из RSS для пересказа")
    return await _call_llm(db, prompt, content)


async def generate_weather_text(db: Session, weather_data: str) -> str:
    prompt = get(db, "llm_prompt_weather")
    if not prompt:
        prompt = """Ты ведущий прогноза погоды. Поздоровайся со слушателями NAVO RADIO, объяви что начался прогноз погоды и расскажи про погоду в Душанбе на сегодня и на ближайшую неделю.
В конце добавь фразу про то что слушатели могут и дальше наслаждаться восточной музыкой."""
    return await _call_llm(db, prompt, weather_data)


async def _call_llm(db: Session, system_prompt: str, user_content: str) -> str:
    provider = get(db, "llm_provider") or "groq"
    if provider == "openai":
        return await _call_openai(system_prompt, user_content)
    return await _call_groq(system_prompt, user_content)


async def _call_openai(system_prompt: str, user_content: str) -> str:
    import httpx
    import os
    api_key = getattr(config_settings, "openai_api_key", None) or os.environ.get("OPENAI_API_KEY", "") or ""
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY не задан в .env. Добавьте ключ для использования ChatGPT.")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-5.2",
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
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:300]
        if e.response.status_code == 401:
            raise RuntimeError("Неверный OPENAI_API_KEY. Проверьте ключ в .env")
        raise RuntimeError(f"OpenAI API ошибка {e.response.status_code}: {body}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Ошибка связи с OpenAI: {str(e)[:150]}")
