# План поэтапного рефакторинга NAVO Radio

## Целевая архитектура: HLS как единственный бесшовный режим

### Текущая схема
```
[БД + расписание] → Icecast source (FFmpeg concat) → Icecast → клиенты
                  → /stream (FFmpeg concat) → fallback
                  → HLS (pre-generated VOD) → основной плеер
```

### Предлагаемая схема (современная)
```
[БД + расписание] → HLS Generator (фоновый) → /hls/{date}/{hash}/stream.m3u8
                                              → ЕДИНСТВЕННЫЙ источник для плеера
                  
                  → /stream (fallback) — только когда HLS не готов
                  → Icecast source — опционально, для внешних плееров (VLC и т.д.)
```

**Принципы:**
1. **HLS — primary**: Плеер всегда предпочитает HLS. Бесшовные переходы, seek, metadata.
2. **/stream — fallback**: Для старых клиентов или пока HLS генерируется.
3. **Icecast — опционально**: Для интеграций (внешние приложения, партнёры).

---

## Фазы рефакторинга

### Фаза 1: Критические исправления ✅
- [x] Генерация тишины при отсутствующих файлах (stream_broadcast, stream_broadcast_ffmpeg)
- [x] Документация: см. DEPLOYMENT.md — «Дубли icecast_source»

### Фаза 2: Качество кода ✅
- [x] `db.query(Model).get(id)` → `db.get(Model, id)` (SQLAlchemy 2.0)
- [x] Удалить мёртвый код в database.py
- [x] Использовать `Depends(get_db)` в /stream и /stream-test

### Фаза 3: Общие утилиты ✅
- [x] Создать `utils/time_utils.py`: parse_time, time_str, sec_to_hms
- [x] Убрать дублирование из streamer_service, broadcast_service, broadcast_generator

### Фаза 4: HLS как primary ✅
- [x] Исправить _DATERANGE_BASE — использовать broadcast_date
- [ ] Упростить логику плеера: HLS first, /stream только при 404 (опционально)

### Фаза 5: Архитектура (отложено)
- [ ] Разбить циклические импорты (streamer ↔ broadcast_service)
- [ ] Выделить `services/audio_resolver.py` — разрешение путей к файлам
- [ ] Типизация и тесты для критичных путей
