import feedparser
import httpx
from datetime import datetime

DEFAULT_RSS_SOURCES = [
    "https://pressa.tj/ru/feed/",
    "https://asiaplustj.info/ru/rss",
    "https://feeds.tajikistannews.net/rss/929bcf2071e81801",
    "https://eurasianet.org/region/tajikistan/feed",
    "https://lenta.ru/rss",
    "https://ria.ru/export/rss2/index.xml",
]


async def fetch_news_from_rss(limit: int = 15, rss_urls: list[str] | None = None) -> list[dict]:
    """Fetch news from RSS feeds. Returns list of {title, link, summary, source}."""
    urls = rss_urls or DEFAULT_RSS_SOURCES
    all_news = []
    seen_titles = set()

    for url in urls:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, timeout=15.0)
                r.raise_for_status()
                feed = feedparser.parse(r.content)

            for entry in feed.entries[:5]:
                title = (entry.get("title") or "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                raw = (
                    entry.get("summary", "")
                    or entry.get("description", "")
                    or (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
                )
                summary = (raw or "")[:400].strip()
                all_news.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "summary": summary,
                    "source": feed.feed.get("title", url),
                })
                if len(all_news) >= limit:
                    return all_news
        except Exception:
            continue

    return all_news[:limit]
