from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import engine, Base, get_db
from routes import (
    admin_router,
    songs_router,
    news_router,
    weather_router,
    podcasts_router,
    intros_router,
    broadcast_router,
)
from config import settings
from services.tts_service import list_voices


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="NAVO RADIO API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/api")
app.include_router(songs_router, prefix="/api")
app.include_router(news_router, prefix="/api")
app.include_router(weather_router, prefix="/api")
app.include_router(podcasts_router, prefix="/api")
app.include_router(intros_router, prefix="/api")
app.include_router(broadcast_router, prefix="/api")


@app.get("/api/tts/voices")
async def get_tts_voices():
    return {"voices": await list_voices()}


# Serve uploaded files
uploads_path = Path(settings.upload_dir)
if uploads_path.exists():
    app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")


@app.get("/")
def root():
    return {"message": "NAVO RADIO API", "docs": "/docs"}
