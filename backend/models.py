from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from database import Base
import enum


class EntityType(str, enum.Enum):
    SONG = "song"
    DJ = "dj"
    NEWS = "news"
    WEATHER = "weather"
    PODCAST = "podcast"
    INTRO = "intro"


class Song(Base):
    __tablename__ = "songs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(512), nullable=False)
    artist = Column(String(512), nullable=False)
    album = Column(String(512), default="")
    file_path = Column(String(1024), nullable=False)
    duration_seconds = Column(Float, default=0)
    dj_text = Column(Text, default="")
    dj_audio_path = Column(String(1024), default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    audio_path = Column(String(1024), default="")
    duration_seconds = Column(Float, default=0)
    broadcast_date = Column(Date, nullable=True, index=True)  # для какого дня — фильтр по дате
    created_at = Column(DateTime, default=datetime.utcnow)


class Weather(Base):
    __tablename__ = "weather"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    audio_path = Column(String(1024), default="")
    duration_seconds = Column(Float, default=0)
    broadcast_date = Column(Date, nullable=True, index=True)  # для какого дня — фильтр по дате
    created_at = Column(DateTime, default=datetime.utcnow)


class Podcast(Base):
    __tablename__ = "podcasts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False)
    duration_seconds = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Intro(Base):
    __tablename__ = "intros"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False)
    duration_seconds = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class BroadcastItem(Base):
    __tablename__ = "broadcast_items"

    id = Column(Integer, primary_key=True, index=True)
    broadcast_date = Column(Date, nullable=False, index=True)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(Integer, nullable=False)
    start_time = Column(String(8), nullable=False)  # HH:MM:SS
    end_time = Column(String(8), nullable=False)
    duration_seconds = Column(Float, default=0)
    sort_order = Column(Integer, default=0)
    metadata_json = Column(Text, default="{}")  # title, artist, etc. for display


class Setting(Base):
    """Key-value settings from admin panel. Replaces hardcoded config for editable options."""
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, default="")
