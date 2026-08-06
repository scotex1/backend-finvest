"""
middleware/auth_middleware.py — Firebase token verification middleware
Attaches decoded user info to request.state for all protected routes
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from firebase_admin import auth as firebase_auth
import logging

logger = logging.getLogger(__name__)

# Routes that do NOT require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/sync",
    "/api/v1/payment/webhook",   # Cashfree webhook — verified by signature
}

PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public routes
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authorization header missing. Use: Bearer <token>"}
            )

        token = auth_header.split(" ", 1)[1].strip()

        # Verify with Firebase
        try:
            decoded = firebase_auth.verify_id_token(token, check_revoked=True)
            request.state.uid   = decoded["uid"]
            request.state.email = decoded.get("email", "")
            request.state.token_data = decoded
        except firebase_auth.RevokedIdTokenError:
            return JSONResponse(status_code=401, content={"detail": "Token revoked. Please sign in again."})
        except firebase_auth.ExpiredIdTokenError:
            return JSONResponse(status_code=401, content={"detail": "Token expired. Please sign in again."})
        except Exception as e:
            logger.warning(f"Token verification failed: {e}")
            return JSONResponse(status_code=401, content={"detail": "Invalid authentication token."})

        return await call_next(request)
