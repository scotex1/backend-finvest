"""
database/models.py — Optional SQLAlchemy models
Used for caching market data, rate limiting, etc.
Primary storage is Firestore — this is just a local cache layer.
"""

from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from core.config import settings

Base = declarative_base()

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)


# ── Market Data Cache ─────────────────────────────────────
class MarketDataCache(Base):
    __tablename__ = "market_data_cache"

    id         = Column(Integer, primary_key=True, index=True)
    symbol     = Column(String(20), index=True, nullable=False)
    data_type  = Column(String(50), nullable=False)  # "quote", "fundamentals", "technicals"
    data       = Column(JSON, nullable=False)
    cached_at  = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    def is_valid(self) -> bool:
        return datetime.utcnow() < self.expires_at


# ── News Cache ─────────────────────────────────────────────
class NewsCache(Base):
    __tablename__ = "news_cache"

    id         = Column(Integer, primary_key=True)
    category   = Column(String(50), default="all")
    articles   = Column(JSON, nullable=False)
    cached_at  = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


# ── Rate Limiting ─────────────────────────────────────────
class RateLimit(Base):
    __tablename__ = "rate_limits"

    id         = Column(Integer, primary_key=True)
    uid        = Column(String(128), index=True, nullable=False)
    endpoint   = Column(String(100), nullable=False)
    count      = Column(Integer, default=0)
    window_start = Column(DateTime, default=datetime.utcnow)
