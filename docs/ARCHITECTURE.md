# NAVO Radio — Архитектура и рекомендации

## Обзор

NAVO Radio — AI-радиостанция с эфиром по расписанию. Стек: FastAPI, React, SQLite, Icecast, FFmpeg.

## Потоки данных

```
┌──────────────────┐     FFmpeg concat      ┌─────────────┐
│ navo-radio-source│ ──────────────────────► │   Icecast   │
│ (icecast_source) │   pipe → icecast://    │  :8001/live │
└────────┬─────────┘                        └──────┬──────┘
         │ write_stream_position()                  │
         ▼                                          │ 404/502
┌──────────────────┐                               ▼
│ stream_position  │                    ┌─────────────────────┐
│ .json            │                    │ Nginx /stream        │
└────────┬─────────┘                    │ fallback → Backend   │
         │ read_now_playing()           │ /stream (FastAPI)    │
         ▼                              └─────────────────────┘
┌──────────────────┐
│ /broadcast/      │
│ now-playing      │
└──────────────────┘
```

**Источники эфира:**
1. **Icecast** (основной) — navo-radio-source стримит в Icecast, Nginx проксирует /stream → Icecast
2. **Backend /stream** (fallback) — при 404/502 от Icecast Nginx отдаёт поток с FastAPI
3. **HLS** — VOD для seek, генерируется по запросу (~10–30 мин)

## Критические компоненты

### 1. Playlist (get_playlist_with_times)

Кортеж: `(path, start_sec, dur, entity_type, entity_id, title)` — 6 элементов.

Используется в: streamer_service, hls_service, broadcast routes. При изменении структуры — обновить все места распаковки.

### 2. stream_position.json

Путь: `{PROJECT_ROOT}/uploads/stream_position.json`

Пишется: icecast_source, backend /stream (on_position callback)  
Читается: /broadcast/now-playing

MAX_AGE_SEC=20 — данные старше 20 сек считаются устаревшими.

### 3. Московское время

- **time_service**: worldtimeapi.org (кэш 60 сек), fallback — системное время
- **Сервер**: рекомендуется Europe/Moscow (TZ)
- **sync_offset_seconds**: смещение в настройках (для коррекции рассинхрона)

### 4. Длительности (рассинхрон)

Админка и эфир должны использовать одни и те же длительности. См. [SYNC_DESYNC_FIX.md](SYNC_DESYNC_FIX.md).

- После замены файлов — «Пересчитать длительности» в админке
- recalc_broadcast_for_date — при генерации эфира

## Рекомендации по надёжности

### Развёртывание

1. **systemd**: navo-radio (API), navo-radio-source (Icecast source), icecast2
2. **Порядок старта**: icecast2 → navo-radio → navo-radio-source
3. **Restart=always** для navo-radio-source — при падении автоматический перезапуск

### База данных

- SQLite с WAL, busy_timeout=30000
- Один процесс пишет (API), source только читает — минимизация блокировок
- recalc в source отключён (database locked при параллельном доступе)

### HLS

- Lock-файл `hls_generating_{date}.lock` — не запускать два процесса для одной даты
- Генерация ~10–30 мин для суток эфира
- run_hls.py удаляет lock в finally

### Мониторинг

- `/api/diagnostics` — статус эфира, HLS, Icecast
- journalctl -u navo-radio-source — логи source
- stream_position.json существует и свежий — эфир идёт

## Рекомендации по развитию

### Краткосрочные

1. **Typed PlaylistItem** — NamedTuple или dataclass вместо кортежа, избежать ошибок распаковки
2. **Health check** — endpoint /health для мониторинга (Kubernetes, Uptime)
3. **Метрики** — Prometheus-совместимые метрики (количество слушателей, ошибки)

### Среднесрочные

1. **PostgreSQL** — при росте нагрузки, конкурентные записи
2. **Redis** — кэш stream_position, now-playing, снижение нагрузки на БД
3. **Отдельный воркер** — HLS генерация в Celery/RQ, не блокирует API

### Долгосрочные

1. **Микросервисы** — source, API, HLS generator как отдельные сервисы
2. **S3/MinIO** — хранение аудио и HLS сегментов
3. **CDN** — раздача HLS через CDN для масштабирования

## Конфигурация (.env)

| Переменная | Описание |
|------------|----------|
| BASE_URL | Публичный URL сайта |
| STREAM_URL | URL стрима (/stream или полный) |
| USE_EXTERNAL_TIME | true = worldtimeapi.org |
| SYNC_OFFSET_SECONDS | Смещение эфира (сек) |
| STREAM_BITRATE | 128k, 256k, 320k |
| ICECAST_* | Для navo-radio-source.service |
