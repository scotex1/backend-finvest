"""
FinVest Pro — FastAPI Backend
main.py — App entry point, router registration, middleware setup
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import logging

from core.config import settings
from firebase.firebase_config import initialize_firebase
from middleware.auth_middleware import AuthMiddleware
from middleware.subscription_middleware import SubscriptionMiddleware

from routes.auth_routes         import router as auth_router
from routes.user_routes         import router as user_router
from routes.investment_routes   import router as investment_router
from routes.subscription_routes import router as subscription_router
from routes.admin_routes        import router as admin_router

# ── Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("finvest")


# ── Lifespan (startup / shutdown) ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting FinVest Pro Backend...")
    initialize_firebase()
    logger.info("✅ Firebase initialized")
    yield
    logger.info("🛑 Shutting down...")


# ── App ────────────────────────────────────────────────────
app = FastAPI(
    title="FinVest Pro API",
    description="Backend API for FinVest Pro — AI-powered financial intelligence platform",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,   # Hide docs in production
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)


# ── CORS ───────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


# ── Custom Middleware ──────────────────────────────────────
app.add_middleware(AuthMiddleware)
app.add_middleware(SubscriptionMiddleware)


# ── Routers ────────────────────────────────────────────────
app.include_router(auth_router,         prefix="/api/v1/auth",         tags=["Auth"])
app.include_router(user_router,         prefix="/api/v1/user",         tags=["User"])
app.include_router(investment_router,   prefix="/api/v1/engines",      tags=["Engines"])
app.include_router(subscription_router, prefix="/api/v1/payment",      tags=["Payments"])
app.include_router(admin_router,        prefix="/api/v1/admin",        tags=["Admin"])


# ── Health Check ───────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", tags=["Health"])
async def root():
    return {"message": "FinVest Pro API", "docs": "/docs"}
