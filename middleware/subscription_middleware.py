"""
middleware/subscription_middleware.py — Plan expiry auto-check
Checks and downgrades expired plans on every request
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from firebase.firebase_service import FirebaseService, PlanService
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Only check on these path prefixes
CHECK_PATHS = ("/api/v1/engines/", "/api/v1/user/")


class SubscriptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only run on engine/user routes where plan matters
        if any(path.startswith(p) for p in CHECK_PATHS):
            uid = getattr(request.state, "uid", None)
            if uid:
                try:
                    user = FirebaseService.get_user(uid)
                    if user:
                        expiry = user.get("plan_expiry")
                        plan   = user.get("plan", "free")
                        # Auto-expire if needed
                        if expiry and plan != "free" and datetime.utcnow() > expiry:
                            PlanService.expire_plan(uid)
                            logger.info(f"Plan auto-expired for uid: {uid}")
                except Exception as e:
                    logger.warning(f"Subscription check error: {e}")
                    # Non-blocking — don't fail the request

        return await call_next(request)
