# NAVO RADIO — локальная разработка

## Требования

- **Python 3.11+** (backend)
- **Node.js 20+** (frontend)
- **FFmpeg** — [ffmpeg.org/download](https://ffmpeg.org/download.html)
- **Icecast** — установлен в `C:\Program Files\Icecast`

## Порты

| Сервис | Порт | URL |
|--------|------|-----|
| Backend (FastAPI) | 8000 | http://localhost:8000 |
| Frontend (Vite) | 5173 | http://localhost:5173 |
| Icecast | 8001 | http://localhost:8001/live |

## .env для локальной разработки

В корне проекта создайте `.env` из `.env.example`. Для локальной разработки:

```
BASE_URL=http://localhost:8000
ICECAST_STREAM_URL=http://localhost:8001/live
```

## Быстрый запуск (всё в одном)

```bash
dev\start_all.bat
```

Откроет 4 окна: Icecast, Backend, Icecast Source, Frontend. При первом запуске создаст venv и установит зависимости.

## Запуск вручную (4 терминала)

### 1. Icecast
```bash
dev\start_icecast.bat
# или
powershell -File dev\start_icecast.ps1
```

### 2. Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

# В другом терминале — icecast source (стримит эфир)
python icecast_source.py
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

### 4. Icecast Source (стримит эфир в Icecast)
```bash
cd backend
venv\Scripts\activate
python icecast_source.py
```

## Проверка

- Player: http://localhost:5173
- Admin: http://localhost:5173/admin
- API docs: http://localhost:8000/docs
- Icecast status: http://localhost:8001/

## Поток

1. Сгенерируйте эфир в админке (Сетка эфира → Сгенерировать)
2. Запустите `icecast_source.py` — он читает эфир из БД и стримит в Icecast
3. Плеер подключается к http://localhost:8001/live
4. При недоступности Icecast — fallback на http://localhost:8000/stream
