"""
core/config.py — Environment configuration

FIXES vs v1:
 [1] FRONTEND_URL + BACKEND_URL added (used in payment_service for return/notify URLs)
 [2] CASHFREE_WEBHOOK_SECRET added (for webhook signature verification)
 [3] PLAN_PRICES and PLAN_DURATIONS moved to proper typed fields
"""

from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────
    APP_NAME:    str  = "FinVest Pro"
    DEBUG:       bool = False
    SECRET_KEY:  str  = "change-this-in-production-use-openssl-rand-hex-32"
    API_VERSION: str  = "v1"

    # ── URLs [FIX 1] ──────────────────────────────────────
    FRONTEND_URL: str = "https://yourdomain.com"    # ← Set in .env
    BACKEND_URL:  str = "https://your-backend.com"  # ← Set in .env

    # ── CORS ───────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://yourdomain.com",
        "https://www.yourdomain.com",
    ]

    # ── Firebase ───────────────────────────────────────────
    FIREBASE_CREDENTIALS_PATH: str = "firebase/serviceAccountKey.json"
    FIREBASE_PROJECT_ID:       str = "your-firebase-project-id"

    # ── Database ───────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./finvest.db"

    # ── Cashfree ───────────────────────────────────────────
    CASHFREE_APP_ID:        str = "your-cashfree-app-id"
    CASHFREE_SECRET_KEY:    str = "your-cashfree-secret-key"
    CASHFREE_WEBHOOK_SECRET: str = ""    # [FIX 2] Get from Cashfree dashboard → Webhooks
    CASHFREE_BASE_URL:      str = "https://sandbox.cashfree.com/pg"
    # Production: CASHFREE_BASE_URL=https://api.cashfree.com/pg

    # ── Plan Pricing (paise = rupees × 100) ───────────────
    PLAN_PRICES: dict = {
        "basic":        49900,
        "pro":          99900,
        "elite":       199900,
        "basic_yearly": 449900,
        "pro_yearly":   899900,
    }

    # ── Plan Durations (days) ─────────────────────────────
    PLAN_DURATIONS: dict = {
        "basic":        30,
        "pro":          30,
        "elite":        30,
        "basic_yearly": 365,
        "pro_yearly":   365,
    }

    # ── Market Data ────────────────────────────────────────
    MARKET_DATA_API_KEY: str = ""

    # ── AI ─────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY:    str = ""

    # ── News (multi-provider, free tiers) ──────────────────
    NEWS_API_KEY:     str = ""   # newsapi.org
    GNEWS_API_KEY:    str = ""   # gnews.io
    CURRENTS_API_KEY: str = ""   # currentsapi.services

    # ── Market Data (free alternatives to yfinance) ────────
    ALPHA_VANTAGE_API_KEY: str = ""   # alphavantage.co — backup only

    # ── Redis ──────────────────────────────────────────────
    REDIS_URL: str = ""

    # ── Email ──────────────────────────────────────────────
    SMTP_HOST:     str = "smtp.gmail.com"
    SMTP_PORT:     int = 587
    SMTP_USER:     str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL:    str = "noreply@finvestpro.in"

    class Config:
        env_file          = ".env"
        env_file_encoding = "utf-8"
        case_sensitive    = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
