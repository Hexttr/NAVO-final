# NAVO RADIO — Онбординг для AI-агента

Подробная инструкция для быстрого вхождения в контекст проекта. Документ для копирования в промпт или для чтения перед работой над задачей.

---

## 1. Что это за проект

**NAVO RADIO** — AI-радиостанция восточной/таджикской музыки.  
Сайт: **navoradio.com**

Пользователь открывает сайт → нажимает Play → слушает непрерывный эфир. Эфир формируется автоматически по расписанию (музыка, DJ-представления, новости, погода, подкасты, интро).

---

## 2. Стек технологий

| Слой | Технологии |
|------|------------|
| Backend | Python 3.x, FastAPI, SQLAlchemy, SQLite |
| Frontend | React 18, Vite, React Router |
| Стриминг | FFmpeg, Icecast2 |
| TTS | Edge TTS (по умолчанию) или ElevenLabs |
| LLM | Groq (по умолчанию) или OpenAI GPT |
| Deploy | Ubuntu, systemd, nginx, Paramiko (SSH) |

---

## 3. Архитектура и потоки данных

```
┌─────────────────────┐    FFmpeg pipe     ┌──────────────┐
│ navo-radio-source   │ ─────────────────► │   Icecast    │
│ (icecast_source.py) │  аудио в icecast   │  :8001/live  │
└──────────┬──────────┘                    └──────┬───────┘
           │ stream_position.json                 │
           │ (позиция в эфире)                    │ 404/502
           ▼                                      ▼
┌─────────────────────┐                ┌─────────────────────┐
│ Backend API         │◄───────────────│ Nginx /stream       │
│ FastAPI :8000       │  fallback      │ проксирует на API   │
└──────────┬──────────┘                └─────────────────────┘
           │
           ▼
┌─────────────────────┐
│ SQLite (navo.db)    │  Songs, News, Weather, BroadcastItem...
└─────────────────────┘
```

**Эфир:**
- Источник: `icecast_source.py` читает плейлист из БД, конкатенирует файлы через FFmpeg, стримит в Icecast
- Icecast — единая точка для всех слушателей (один поток)
- Fallback: при 404/502 от Icecast плеер переключается на `/stream` от backend
- Время: московское (Europe/Moscow). Расписание строится по слотам (час:минута:тип)

---

## 4. Сущности и модели

| Сущность | Описание |
|----------|----------|
| **Song** | Песня. Источник: Jamendo API или ручное добавление. Есть DJ-текст (LLM) и DJ-озвучка (TTS) |
| **News** | Выпуск новостей. RSS → LLM → TTS. Привязан к broadcast_date |
| **Weather** | Прогноз погоды. API погоды → LLM → TTS. Привязан к broadcast_date |
| **Podcast** | Подкаст. Общий пул, без привязки к дате |
| **Intro** | Интро в эфире (в конце часа или каждые N слотов) |
| **BroadcastItem** | Слот в сетке эфира: entity_type, entity_id, start_time, duration_seconds, sort_order |

---

## 5. Структура репозитория

```
Radio7/
├── backend/                 # FastAPI
│   ├── main.py              # Точка входа, middleware (auth, CORS), роуты
│   ├── config.py            # Pydantic Settings из .env
│   ├── database.py          # SQLite, WAL, SessionLocal
│   ├── models.py            # SQLAlchemy модели
│   ├── routes/              # Роутеры (songs, news, weather, broadcast, ...)
│   ├── services/
│   │   ├── broadcast_generator.py   # Генерация сетки эфира
│   │   ├── streamer_service.py      # Плейлист, стриминг, moscow_seconds_now
│   │   ├── stream_position.py       # Запись stream_position.json
│   │   ├── settings_service.py      # Ключ-значение настройки из БД
│   │   ├── tts_service.py           # Edge TTS, ElevenLabs
│   │   ├── groq_service.py          # LLM Groq
│   │   ├── llm_service.py           # Обёртка LLM (Groq/OpenAI)
│   │   ├── jamendo.py               # Jamendo API
│   │   └── ...
│   └── utils/
│       ├── audio_utils.py           # Усиление громкости (ffmpeg)
│       ├── time_utils.py           # sec_to_hms, time_str
│       └── upload_utils.py          # Загрузка файлов
├── icecast_source.py        # Отдельный процесс — источник для Icecast (запуск из backend/)
├── frontend/
│   └── src/
│       ├── api.js                  # API-клиент, authHeaders, fetchAudioBlobUrl
│       ├── App.jsx                 # Роутинг: /, /admin/*
│       ├── pages/
│       │   ├── Player.jsx          # Плеер (публичная страница)
│       │   └── admin/
│       │       ├── AdminAuthGate.jsx   # Вход по X-Admin-Key
│       │       ├── Broadcast.jsx       # Сетка эфира
│       │       ├── SongsDj.jsx, News.jsx, Weather.jsx, Podcasts.jsx, Intros.jsx
│       │       ├── Settings.jsx        # Настройки (слоты, интро, TTS, LLM)
│       │       └── Diagnostics.jsx      # Отладка
├── config/icecast.xml       # Icecast для локальной разработки
├── deploy/
│   ├── deploy_to_server.py  # Деплой на Ubuntu (pull, build, systemd)
│   ├── deploy_icecast.py    # Настройка Icecast + source на сервере
│   ├── navo-radio.service   # systemd: API
│   ├── navo-radio-source.service  # systemd: Icecast source
│   └── nginx-navoradio.conf # Nginx конфиг
├── docs/                    # Документация
├── .env.example             # Шаблон переменных окружения
└── uploads/                 # Загруженные файлы, stream_position.json
```

---

## 6. Ключевые файлы и их роль

| Задача | Файл |
|--------|------|
| Добавить роут API | `backend/routes/*.py`, `backend/main.py` |
| Изменить генерацию эфира | `backend/services/broadcast_generator.py` |
| Изменить логику стрима | `backend/services/streamer_service.py`, `icecast_source.py` |
| Изменить «Сейчас играет» | `backend/routes/broadcast.py` (now-playing), `stream_position.py` |
| Изменить плеер | `frontend/src/pages/Player.jsx` |
| Изменить админку | `frontend/src/pages/admin/*.jsx` |
| Добавить настройку | `backend/services/settings_service.py`, `frontend/.../Settings.jsx` |
| Auth, X-Admin-Key | `backend/main.py` (_admin_auth_middleware, auth_check) |
| Воспроизведение аудио в админке | `fetchAudioBlobUrl` в api.js — blob URL (т.к. `<audio src>` не поддерживает заголовки) |

---

## 7. Переменные окружения (.env)

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| JAMENDO_CLIENT_ID | да | API Jamendo для музыки |
| GROQ_API_KEY | да | LLM для DJ, новостей, погоды |
| WEATHER_API_KEY | да | API погоды |
| ADMIN_API_KEY | prod | Ключ админки. Пусто = без авторизации |
| ICECAST_SOURCE_PASSWORD | prod | Пароль для Icecast source |
| ELEVENLABS_API_KEY | опционально | TTS (если tts_provider=elevenlabs) |
| OPENAI_API_KEY | опционально | LLM (если переключить в настройках) |
| DATABASE_URL | — | sqlite:///./navo.db |
| BASE_URL | prod | https://navoradio.com |
| TTS_VOLUME, TTS_RATE, PODCAST_INTRO_VOLUME_BOOST | — | Громкость, скорость, усиление подкастов/интро |

Полный список: `.env.example`

---

## 8. API и авторизация

**Публичные пути** (без X-Admin-Key):
- `/api/auth/check` — проверка ключа, вход
- `/api/diagnostics` — статус системы
- `/api/broadcast/now-playing` — текущий трек
- `/api/broadcast/stream-url`, `/api/broadcast/playlist-urls`

**Защищённые** — требуют `X-Admin-Key` или `Authorization: Bearer <key>`.

**Auth flow:**
1. `POST /api/auth/check` с `{key: "..."}` — при успехе ключ сохраняется в localStorage
2. Все запросы админки добавляют `X-Admin-Key` через `apiFetch` в api.js
3. Аудио в админке: `fetchAudioBlobUrl(url)` — fetch с заголовками, blob → URL.createObjectURL (т.к. `<audio src>` не передаёт заголовки)
4. При 401 — сброс ключа, событие `admin-unauth`

---

## 9. Генерация эфира

**Логика** (`broadcast_generator.py`):
- Фиксированные слоты из настроек: (час, минута, тип) — news, weather, podcast
- Между слотами — песни
- Интро: по `broadcast_intro_minute` (каждый час) или `broadcast_intro_every_n_slots` (каждые N слотов)
- Слоты сортируются по времени, заполняются до 24:00

**Настройки** (Settings, БД):
- `broadcast_slots` — список [час, минута, тип]
- `broadcast_intro_minute` — минута интро (55 = в 8:55, 9:55...)
- `broadcast_intro_every_n_slots` — 0 = по времени, 5/10 = каждые 5/10 слотов

---

## 10. Стриминг и «Сейчас играет»

**Playlist** — кортеж из 6 элементов: `(path, start_sec, dur, entity_type, entity_id, title)`.

**stream_position.json** — текущая позиция (секунды от полуночи МСК). Пишется icecast_source и backend /stream. Читается now-playing.

**Порядок определения «Сейчас играет»:**
1. `read_now_playing()` — файл от Icecast source
2. `read_stream_position()` — stream_position.json
3. `moscow_seconds_now()` — fallback по времени сервера

**Рассинхрон:** если реальная длительность файла ≠ duration_seconds в БД — расхождение. Решение: «Пересчитать длительности» в админке.

---

## 11. Локальная разработка

```bash
# Backend
cd backend && python -m venv venv
# Windows: venv\Scripts\activate  |  Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend && npm install && npm run dev

# Icecast (опционально, для полного стрима)
# Запустить icecast с config/icecast.xml (порт 8001)
# Запустить: python icecast_source.py (из backend/)
```

- Плеер: http://localhost:5173  
- Админка: http://localhost:5173/admin  
- API docs: http://localhost:8000/docs  

---

## 12. Деплой на сервер

**Ветка:** `ubuntu` (или `local` — зависит от настройки)

**Перед деплоем:** `git push origin ubuntu`

**Скрипты:**
```bash
# Полный деплой
python deploy/deploy_to_server.py

# Только ключи + рестарт
NAVO_ELEVENLABS_API_KEY=sk_xxx python deploy/deploy_to_server.py --key-and-restart

# Только nginx
python deploy/deploy_to_server.py --nginx-only
```

**Сервер:** `/opt/navo-radio/`, `.env` копируется вручную или создаётся из `.env.example`.

**systemd:** icecast2 → navo-radio (API) → navo-radio-source. Restart=always.

---

## 13. Известные проблемы и решения

| Проблема | Решение |
|----------|---------|
| Плеер не воспроизводит | Проверить Icecast (8001), fallback /stream. Unlock AudioContext при клике. |
| «Сейчас играет» не совпадает | Пересчитать длительности. См. docs/SYNC_DESYNC_FIX.md |
| ElevenLabs 403/302 | Проверить ключ, follow_redirects. Возможна блокировка IP датацентра. |
| Аудио в админке не играет | fetchAudioBlobUrl + X-Admin-Key. Проверить ADMIN_API_KEY. |
| auth/check 401 при пустом ключе | Исправлено: пустой key возвращает auth_required без 401. |
| Сетка с утра при перезагрузке | server_time в ответе getBroadcast — позиция по времени сервера. |

---

## 14. Полезные команды

```bash
# Диагностика
curl http://localhost:8000/api/diagnostics

# Проверка продакшена
python deploy/check_diagnostics.py
```

---

## 15. Связанные документы

- `AGENTS.md` — краткий контекст, известные проблемы
- `docs/ARCHITECTURE.md` — архитектура, компоненты
- `docs/SYNC_DESYNC_FIX.md` — рассинхрон эфира и админки
