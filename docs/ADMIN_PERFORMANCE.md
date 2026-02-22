# Анализ медленной работы админки

## Выявленные причины

### 1. Агрессивный polling

| Страница | API | Интервал | Проблема |
|----------|-----|----------|----------|
| Broadcast | `getBroadcastNowPlaying` | **500 мс** | 2 запроса/сек → нагрузка на сервер |
| AdminLayout | `getStats` | 10 сек | Приемлемо |
| Diagnostics | `getDiagnosticsNowPlaying` | 5 сек | Приемлемо |
| Broadcast (HLS) | `getHlsStatus` | 15 сек | Приемлемо |

**Исправлено:** интервал now-playing на Broadcast увеличен до 2000 мс (2 сек).

### 2. N+1 в get_broadcast

`GET /api/broadcast` для каждого элемента с `entity_type in (dj, news, weather)` вызывал `_get_entity_text()` — отдельный запрос к БД. При 877 элементах — сотни запросов.

**Исправлено:** batch-загрузка `_load_entity_texts_batch()` — 3 запроса вместо N.

### 3. Каталог при открытии «Вставить»

При клике «Вставить слот» выполняется `Promise.all([getSongs, getNews, getWeather, getPodcasts, getIntros])` — 5 параллельных запросов. Для больших каталогов — медленно.

**Рекомендация:** кэшировать каталог, подгружать по требованию (lazy).

### 4. Backend: diagnostics/now-playing

`/api/broadcast/diagnostics/now-playing` с `real_durations=true` вызывает `get_playlist_with_times(..., use_real_durations=True)` — ffprobe для каждого из ~877 файлов. По умолчанию `real_durations=false`, но вызов всё равно тяжёлый (много запросов к БД).

### 5. getTtsVoices при каждом заходе

Вызывается при монтировании Broadcast, SongsDj, News, Weather — на каждой странице заново.

**Рекомендация:** кэшировать в контексте или localStorage.

## Быстрые улучшения (сделано)

- Интервал now-playing: 500 мс → 2000 мс
- get_broadcast: N+1 устранён, batch-загрузка текстов (3 запроса вместо сотен)

## Дальнейшие улучшения

1. **get_broadcast** — устранить N+1 (batch load текстов)
2. **Каталог** — кэш + lazy load
3. **getTtsVoices** — кэш на уровне приложения
4. **diagnostics/now-playing** — не вызывать с `real_durations=true` по умолчанию
