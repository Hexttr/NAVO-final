# NAVO RADIO — контекст для AI-агента

Документ для быстрого онбординга нового агента. Ветка: **ubuntu**. Деплой на сервер: `python deploy/deploy_to_server.py`.

---

## Функционал приложения

**NAVO RADIO** — AI-радиостанция восточной/таджикской музыки. Сайт: navoradio.com.

### Основные сущности
- **Songs** — песни из Jamendo, с опциональным DJ-текстом (представление трека, LLM)
- **News** — выпуски новостей (RSS → LLM → TTS)
- **Weather** — прогноз погоды (API → LLM → TTS)
- **Podcasts** — подкасты (общий пул, без привязки к дате)
- **Intro** — интро в конце каждого часа
- **BroadcastItem** — слот в сетке эфира (entity_type, entity_id, start_time, duration_seconds)

### Поток эфира
1. **Сетка эфира** генерируется в админке («Сгенерировать эфир») — `broadcast_generator.py`
2. Эфир — 24 часа, фиксированные слоты (новости, погода, подкасты по часам), между ними — песни
3. **Воспроизведение**: 
   - Приоритет **Icecast** (`http://localhost:8001/live` или `https://navoradio.com/live`) — единый поток
   - Fallback **/stream** — живой MP3 от backend (при недоступности Icecast)
4. **Icecast** (порт 8001) — единый поток для всех слушателей. Источник: `icecast_source.py`, читает эфир из БД и стримит через FFmpeg concat (бесшовно)

### Технологии
- Backend: FastAPI, SQLite, FFmpeg
- Frontend: React, Vite
- TTS: Edge TTS (бесплатно) или ElevenLabs (платно)
- LLM: Groq (бесплатно) или ChatGPT/OpenAI (платно)
- Ключи в `.env`: JAMENDO_CLIENT_ID, GROQ_API_KEY, OPENAI_API_KEY, WEATHER_API_KEY, ELEVENLABS_API_KEY

### Ключевые файлы
- `backend/services/streamer_service.py` — плейлист, синхронизация с Москвой, стриминг (ffmpeg_concat)
- `backend/services/broadcast_generator.py` — генерация сетки
- `backend/icecast_source.py` — источник для Icecast
- `frontend/src/pages/Player.jsx` — плеер (Icecast или /stream)
- `config/icecast.xml` — конфиг Icecast для проекта
- `deploy/deploy_to_server.py` — деплой на Ubuntu-сервер

---

## Известные проблемы

### 1. ElevenLabs — нет выбора голоса

**Симптом:** В выпадающем «Голос TTS» вместо списка голосов:  
`ElevenLabs: Redirect response '302 Found' for url 'https://api.elevenlabs.io/v1/voices'`  
или ранее: `403 Forbidden`.

**Что сделано:**
- Ключ читается из `ELEVENLABS_API_KEY` в `.env` (config.py, tts_service.py)
- Fallback на `os.environ`
- Добавлено `follow_redirects=True` в httpx для запроса voices
- На сервере ключ обновляется через `NAVO_ELEVENLABS_API_KEY` при деплое или `--key-and-restart`

**Возможные причины:**
- ElevenLabs редиректит запросы (302) — нужно убедиться, что httpx корректно следует редиректам
- Блокировка IP датацентра (сервер в Нидерландах) со стороны ElevenLabs
- Неверный или истёкший ключ

**Где смотреть:** `backend/services/tts_service.py` — `_list_elevenlabs_voices()`

### 2. Эфир не воспроизводится (сегменты грузятся, звука нет)

**Симптом:** В Network все запросы 200 (hls-url, stream.m3u8, seg_*.ts), но звука нет, ошибок в консоли нет.

**Что сделано:**
- HLS: используется `startPosition` в конфиге Hls.js вместо `audio.currentTime` в MANIFEST_PARSED
- Разблокировка AudioContext при клике Play (`unlockAudioContext`)
- Nginx: при 400 от Icecast — fallback на backend `/stream` (`error_page 400 404 ...`)

**Где смотреть:** `frontend/src/pages/Player.jsx`

### 3. Рассинхрон эфира и админки

**Симптом:** Подкаст/трек звучит раньше или позже, чем показывает админка «Сейчас играет».

**Причина:** Эфир воспроизводит файлы по фактической длительности, админка — по `BroadcastItem.duration_seconds` из БД.

**Решение:** 
- «Пересчитать длительности» в админке после замены файлов
- При старте icecast_source вызывается `recalc_broadcast_for_date(today)`

**Документ:** `docs/SYNC_DESYNC_FIX.md`

---

## Деплой

**Проверка диагностики:** `python deploy/check_diagnostics.py` — проверка /api/diagnostics

```bash
# Полный деплой (pull, build, restart)
python deploy/deploy_to_server.py

# Только обновить ключ ElevenLabs и перезапустить backend
NAVO_ELEVENLABS_API_KEY=sk_xxx python deploy/deploy_to_server.py --key-and-restart

# Только nginx config
python deploy/deploy_to_server.py --nginx-only
```

Перед деплоем: `git push origin ubuntu`.
