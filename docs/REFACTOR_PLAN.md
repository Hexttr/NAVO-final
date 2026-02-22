# NAVO RADIO — План упрощения и рефакторинга

**Цели:** максимальная надёжность эфира, соответствие расписанию, чёткое отображение «Сейчас в эфире» на фронтенде.

---

## 1. Текущая архитектура (проблемы)

### 1.1 Потоки воспроизведения (сложность)

| Приоритет | Источник | Проблемы |
|-----------|----------|----------|
| 1 | HLS (`/hls/{date}/{hash}/stream.m3u8`) | Генерация 30–50 мин, рассинхрон, проблемы со звуком в Safari |
| 2 | Icecast (порт 8001) | Работает, но дублируется логикой с /stream |
| 3 | `/stream` (FastAPI) | Fallback, каждый слушатель = отдельный FFmpeg |

### 1.2 «Сейчас играет»

- **Источник:** `stream_position.json` (пишет icecast_source или /stream)
- **Проблемы:** рассинхрон из‑за разницы `duration_seconds` в БД и реальной длительности файлов
- **Fallback:** вычисление по расписанию (сложная логика в `now-playing`)

### 1.3 Лишний код

- `hls_service.py` — ~260 строк
- `run_hls.py`, `clean_hls.py`
- HLS-эндпоинты в `broadcast.py` (~150 строк)
- HLS в `Player.jsx` — ~100 строк (hls.js, fallback, startPosition)
- `stream_broadcast_async`, `stream_broadcast_ffmpeg` в streamer_service (не используются в prod)
- `STREAM_MODE` в icecast_source

---

## 2. Целевая архитектура (упрощённая)

### 2.1 Схема потока

```
┌─────────────────────────────────────────────────────────────────┐
│                        СТРИМИНГ                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   БД (BroadcastItem)                                             │
│        │                                                         │
│        ▼                                                         │
│   icecast_source.py  ──►  FFmpeg concat  ──►  Icecast :8001/live │
│        │                         │                               │
│        │                         │  (единственный источник)      │
│        ▼                         ▼                               │
│   stream_position.json  ◄──  on_position callback                 │
│        │                                                         │
│        │  (читает API)                                           │
│        ▼                                                         │
│   GET /api/broadcast/now-playing  ──►  Фронт «Сейчас в эфире»     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     СЛУШАТЕЛИ (плеер)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   1. Пробуем Icecast /live  (один поток для всех)                │
│   2. Если 404/ошибка → /stream (fallback, свой FFmpeg на клиента)│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Принципы

1. **Один источник стрима** — icecast_source (Icecast). /stream — только fallback при недоступности Icecast.
2. **Один источник «Сейчас играет»** — stream_position.json. Пишет только тот, кто стримит.
3. **Реальные длительности** — при старте icecast_source и после генерации эфира вызывать `recalc_broadcast_for_date`.
4. **Без HLS** — убираем предгенерацию, хранилище, синхронизацию.

---

## 3. Детальный план изменений

### 3.1 Backend

#### 3.1.1 Удалить HLS

| Файл/объект | Действие |
|-------------|----------|
| `backend/services/hls_service.py` | Удалить |
| `backend/run_hls.py` | Удалить |
| `clean_hls.py` (корень) | Удалить |
| `backend/routes/broadcast.py` | Удалить: `_spawn_hls_generation`, `get_hls_url`, `hls_url`, `hls_status`, `get_hls_log`, `trigger_generate_hls`, `playlist_metadata` (или оставить упрощённую версию для now-playing), `_hls_generating_lock_path` |
| `backend/main.py` | Убрать проверку `hls_ready` из diagnostics |
| `backend/routes/broadcast.py` (generate, swap, delete_item, insert, move) | Убрать вызовы `_spawn_hls_generation` |

#### 3.1.2 Упростить streamer_service.py

| Действие |
|----------|
| Удалить `stream_broadcast` (sync generator) |
| Удалить `stream_broadcast_async` |
| Удалить `stream_broadcast_ffmpeg` |
| Оставить только `stream_broadcast_ffmpeg_concat` |
| Удалить неиспользуемые хелперы (если останутся только для concat) |

#### 3.1.3 Упростить icecast_source.py

| Действие |
|----------|
| Удалить `STREAM_MODE`, всегда использовать `stream_broadcast_ffmpeg_concat` |
| Удалить импорт `stream_broadcast_async` |
| Упростить логику — один путь |

#### 3.1.4 API now-playing

| Действие |
|----------|
| Оставить приоритет: 1) read_now_playing() из stream_position.json; 2) fallback по расписанию (position = read_stream_position() или moscow_seconds_now) |
| Убрать параметр `position` от HLS (больше не нужен) — но оставить для /stream fallback (клиент может передавать позицию) |
| Упростить логику — меньше ветвлений |

#### 3.1.5 Diagnostics

| Действие |
|----------|
| Убрать `hls_ready`, `hls_url` из `/api/diagnostics` |
| Оставить: broadcast_ready, stream_ready, icecast_live |

---

### 3.2 Frontend

#### 3.2.1 Player.jsx

| Действие |
|----------|
| Удалить HLS полностью (hls.js, getHlsUrl, startPosition, HLS_CANPLAY_TIMEOUT, playStream с HLS) |
| Логика: 1) Пробуем Icecast URL (из playback-hint или конфига); 2) При ошибке → /stream |
| Упростить `positionGetterRef` — для Icecast не передаём position (API использует stream_position); для /stream — передаём вычисленную позицию |
| Удалить `getHlsUrl` из api.js |
| Добавить явный Icecast URL: `/live` или полный `http://host:8001/live` (прокси через nginx) |

#### 3.2.2 API (api.js)

| Действие |
|----------|
| Удалить `getHlsUrl`, `getHlsStatus`, `generateHls`, `getPlaylistMetadata` (если не используется) |
| Добавить `getStreamUrl()` — возвращает URL для плеера (Icecast или /stream) |
| Упростить `getBroadcastNowPlaying` — убрать positionSec для Icecast (опционально оставить для /stream) |

#### 3.2.3 Broadcast.jsx (админка)

| Действие |
|----------|
| Удалить всё, связанное с HLS: `generateHls`, `getHlsStatus`, HLS_GENERATING_KEY, HLS_POLL_INTERVAL, кнопка «Генерировать HLS», индикатор генерации HLS |
| Убрать вызов `generateHls` после generate/swap/move/insert/delete |
| Усилить «Сейчас в эфире» — крупнее, контрастнее, возможно пульсация/подсветка |

#### 3.2.4 «Сейчас в эфире» — улучшение видимости

| Действие |
|----------|
| На Player: блок «Сейчас в эфире» — крупный шрифт, контрастный цвет, возможно иконка «в эфире» |
| Показывать даже когда не playing (например «Сейчас в эфире: Artist - Title» как превью) |
| Polling каждую 1–2 сек (как сейчас) — достаточно |

---

### 3.3 Конфигурация и деплой

#### 3.3.1 Nginx

| Действие |
|----------|
| Убрать `location /hls/` |
| Оставить proxy на Icecast `/live` и backend `/stream` |

#### 3.3.2 Systemd

| Действие |
|----------|
| Оставить `navo-radio` (backend), `navo-icecast-source`, `icecast` |
| Убрать любые HLS-скрипты |

#### 3.3.3 deploy/

| Действие |
|----------|
| Удалить `check_hls_status.py` |
| Обновить `deploy_to_server.py` — убрать HLS |
| Обновить `check_diagnostics.py` |

---

### 3.4 Локальная разработка (Windows)

#### 3.4.1 dev/run_local.ps1 (новый)

```powershell
# Запуск всех компонентов для локальной разработки
# 1. Backend (uvicorn)
# 2. Frontend (vite)
# 3. Icecast (если установлен)
# 4. icecast_source.py
```

#### 3.4.2 dev/README.md (новый)

- Установка FFmpeg, Icecast на Windows
- Порты: 8000 (API), 5173 (frontend), 8001 (Icecast)
- Порядок запуска

---

## 4. Порядок реализации (фазы)

### Фаза 1: Удаление HLS (backend)
1. Удалить `hls_service.py`, `run_hls.py`, `clean_hls.py`
2. В `broadcast.py` — удалить все HLS-эндпоинты и вызовы `_spawn_hls_generation`
3. В `main.py` — упростить diagnostics
4. Проверить: backend запускается, generate broadcast работает

### Фаза 2: Упрощение streamer и icecast_source
1. В `streamer_service.py` — удалить неиспользуемые функции
2. В `icecast_source.py` — убрать STREAM_MODE, оставить только ffmpeg_concat
3. Проверить: icecast_source стримит, stream_position обновляется

### Фаза 3: Frontend — Player
1. Удалить HLS из Player.jsx
2. Логика: Icecast → /stream fallback
3. Упростить api.js (удалить getHlsUrl и т.д.)
4. Проверить: воспроизведение работает

### Фаза 4: Frontend — Broadcast (админка)
1. Удалить HLS из Broadcast.jsx
2. Улучшить отображение «Сейчас в эфире»
3. Проверить: админка работает

### Фаза 5: «Сейчас в эфире» — усиление
1. На Player: крупный блок, контраст
2. На Broadcast: выделенная строка/блок для текущего трека
3. Проверить: синхрон с эфиром

### Фаза 6: Dev-скрипты и документация
1. Создать dev/run_local.ps1, dev/README.md
2. Обновить README.md, AGENTS.md, DEPLOYMENT.md
3. Удалить/обновить deploy-скрипты

---

## 5. Риски и митигация

| Риск | Митигация |
|------|-----------|
| /stream при многих слушателях нагружает сервер | Icecast — основной путь; /stream только fallback. На проде Icecast должен быть всегда доступен |
| stream_position устаревает при паузе icecast_source | MAX_AGE в read_now_playing; fallback на расписание |
| Рассинхрон БД и реальных длительностей | recalc_broadcast_for_date при generate и при старте icecast_source; кнопка «Пересчитать» в админке |

---

## 6. Файлы для изменения (сводка)

| Файл | Действия |
|------|----------|
| `backend/services/hls_service.py` | УДАЛИТЬ |
| `backend/run_hls.py` | УДАЛИТЬ |
| `clean_hls.py` | УДАЛИТЬ |
| `backend/services/streamer_service.py` | Удалить stream_broadcast, stream_broadcast_async, stream_broadcast_ffmpeg |
| `backend/icecast_source.py` | Убрать STREAM_MODE, stream_broadcast_async |
| `backend/routes/broadcast.py` | Удалить HLS-эндпоинты, _spawn_hls, упростить generate/swap/move/insert/delete |
| `backend/main.py` | Убрать hls из diagnostics |
| `frontend/src/pages/Player.jsx` | Удалить HLS, упростить до Icecast + /stream |
| `frontend/src/api.js` | Удалить getHlsUrl, getHlsStatus, generateHls, getPlaylistMetadata |
| `frontend/src/pages/admin/Broadcast.jsx` | Удалить HLS UI, улучшить «Сейчас в эфире» |
| `deploy/check_hls_status.py` | УДАЛИТЬ |
| `deploy/deploy_to_server.py` | Убрать HLS |
| `deploy/check_diagnostics.py` | Убрать HLS |
| `AGENTS.md` | Обновить |
| `README.md` | Обновить |
| `DEPLOYMENT.md` | Убрать HLS |
| `docs/REFACTOR_PLAN.md` | Этот файл |

---

## 7. Ожидаемый результат

- **Меньше кода:** ~800 строк удалено
- **Один путь стриминга:** Icecast (+ /stream fallback)
- **Один источник «Сейчас играет»:** stream_position.json
- **Надёжность:** меньше точек отказа, проще отладка
- **Локальная разработка:** скрипты для Windows, затем Ubuntu
