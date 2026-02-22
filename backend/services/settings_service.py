"""
Settings from DB. Fallback to defaults if not set.
Ключи: jamendo_tags, llm_provider, llm_prompt_dj, llm_prompt_news, llm_prompt_weather,
       tts_provider, broadcast_slots, broadcast_intro_minute.
"""
import json
from sqlalchemy.orm import Session
from models import Setting

# Defaults matching current hardcoded values
DEFAULTS = {
    "jamendo_tags": [
        "tajik music", "eastern music", "central asian", "persian music", "uzbek music",
        "oriental music", "pamir music", "afghan music", "turkmen music", "kyrgyz music",
        "kazakh music", "middle east music", "arabic music", "turkish music", "iranian music",
        "caucasus music", "silk road music", "central asia folk", "balkan music", "russian folk",
    ],
    "llm_provider": "groq",
    "llm_prompt_dj": """Ты Диджей NAVO RADIO. Представь трек, который сейчас будет играть в эфире.
Проанализируй Автора, название песни, альбом.
Расскажи о стиле песни, что-то интересное об альбоме или авторе.
5-6 предложений.
ВАЖНО: Здороваться со слушателями можно только в 1 из 10 случаев. В большинстве случаев сразу переходи к представлению трека без приветствия.""",
    "llm_prompt_news": """Ты ведущий новостей NAVO RADIO. Кратко поздоровайся (1 фраза) и СРАЗУ переходи к новостям.
ОБЯЗАТЕЛЬНО перескажи ВСЕ новости из списка ниже — это реальные события, не придумывай общие фразы.
Используй живые переходы между новостями, не нумеруй. Без реального контента из списка не пиши.""",
    "llm_prompt_weather": """Ты ведущий прогноза погоды. Поздоровайся со слушателями NAVO RADIO, объяви что начался прогноз погоды и расскажи про погоду в Душанбе на сегодня и на ближайшую неделю.
В конце добавь фразу про то что слушатели могут и дальше наслаждаться восточной музыкой.""",
    "tts_provider": "edge-tts",
    "broadcast_slots": [
        [9, 0, "news"], [10, 0, "weather"], [11, 0, "podcast"],
        [12, 0, "news"], [13, 0, "weather"], [14, 0, "podcast"],
        [15, 0, "news"], [16, 0, "weather"], [17, 0, "podcast"],
        [18, 0, "news"], [19, 0, "weather"], [20, 0, "podcast"],
        [21, 0, "news"], [22, 0, "weather"], [23, 0, "podcast"],
    ],
    "broadcast_intro_minute": 55,
    "weather_region": "dushanbe",
    "news_region": "tajikistan",
    "elevenlabs_api_key_frontend": "",
    "openai_api_key": "",
}

WEATHER_REGIONS = {
    "dushanbe": ("Душанбе", "Dushanbe"),
    "moscow": ("Москва", "Moscow"),
    "spb": ("Санкт-Петербург", "Saint Petersburg"),
    "almaty": ("Алматы", "Almaty"),
    "tashkent": ("Ташкент", "Tashkent"),
    "bishkek": ("Бишкек", "Bishkek"),
    "ashgabat": ("Ашхабад", "Ashgabat"),
}

NEWS_REGIONS = {
    "tajikistan": [
        "https://pressa.tj/ru/feed/",
        "https://asiaplustj.info/ru/rss",
        "https://feeds.tajikistannews.net/rss/929bcf2071e81801",
        "https://eurasianet.org/region/tajikistan/feed",
        "https://lenta.ru/rss",
        "https://ria.ru/export/rss2/index.xml",
    ],
    "russia": [
        "https://lenta.ru/rss",
        "https://ria.ru/export/rss2/index.xml",
        "https://tass.ru/rss/v2.xml",
        "https://www.interfax.ru/rss.asp",
    ],
    "central_asia": [
        "https://eurasianet.org/region/tajikistan/feed",
        "https://eurasianet.org/region/kyrgyzstan/feed",
        "https://eurasianet.org/region/uzbekistan/feed",
        "https://eurasianet.org/region/kazakhstan/feed",
        "https://lenta.ru/rss",
    ],
    "mixed": [
        "https://pressa.tj/ru/feed/",
        "https://asiaplustj.info/ru/rss",
        "https://eurasianet.org/region/tajikistan/feed",
        "https://lenta.ru/rss",
        "https://ria.ru/export/rss2/index.xml",
    ],
}


def get(db: Session, key: str) -> str:
    """Get setting value (always string). Returns default if not set."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is not None:
        return row.value or ""
    default = DEFAULTS.get(key, "")
    if isinstance(default, (list, dict)):
        return ""  # get_json will use DEFAULTS
    return str(default) if default is not None else ""


def get_json(db: Session, key: str):
    """Get JSON setting. Returns default (list/dict) if not set."""
    raw = get(db, key)
    if not raw:
        return DEFAULTS.get(key)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULTS.get(key)


def set_(db: Session, key: str, value: str) -> None:
    """Set setting value."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row is not None:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def set_json(db: Session, key: str, value) -> None:
    """Set JSON setting."""
    set_(db, key, json.dumps(value, ensure_ascii=False))


def get_all(db: Session) -> dict:
    """Get all settings as dict for API. Keys that have defaults but no stored value return default."""
    result = {}
    for key in DEFAULTS:
        default = DEFAULTS[key]
        if isinstance(default, (list, dict)):
            result[key] = get_json(db, key)
        else:
            result[key] = get(db, key) or default
    result["weather_region_options"] = [{"value": k, "label": v[0]} for k, v in WEATHER_REGIONS.items()]
    result["news_region_options"] = [
        {"value": "tajikistan", "label": "Таджикистан"},
        {"value": "russia", "label": "Россия"},
        {"value": "central_asia", "label": "Центральная Азия"},
        {"value": "mixed", "label": "Смешанный"},
    ]
    return result


def update_batch(db: Session, data: dict) -> dict:
    """Update multiple settings. data: {key: value}. Returns updated get_all()."""
    for key, value in data.items():
        if key not in DEFAULTS:
            continue
        default = DEFAULTS[key]
        if isinstance(default, (list, dict)):
            set_json(db, key, value)
        else:
            set_(db, key, str(value) if value is not None else "")
    return get_all(db)
