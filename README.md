# NAVO RADIO

AI-powered radio station for Eastern/Tajik music. Admin panel for content management, broadcast scheduling, and Icecast streaming.

## Stack

- **Backend:** Python, FastAPI, SQLite
- **Frontend:** React, Vite
- **Streaming:** FFmpeg subprocess (HTTP stream) или Icecast

## Setup

1. Clone and install:

```bash
# Backend
cd backend && python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install
```

2. Copy `.env.example` to `.env` and fill in API keys.

3. **FFmpeg** — для стриминга эфира (`/stream`). Установите: https://ffmpeg.org/download.html

4. Run:

```bash
# Terminal 1 - Backend
cd backend && uvicorn main:app --reload

# Terminal 2 - Frontend
cd frontend && npm run dev
```

- Player: http://localhost:5173
- Admin: http://localhost:5173/admin
- API: http://localhost:8000/docs

## Structure

- `/` — Play button (listen to broadcast)
- `/admin` — Dashboard, entities (Songs/DJ, News, Weather, Podcasts, INTRO), broadcast grid
