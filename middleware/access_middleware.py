"""
middleware/access_middleware.py — Plan-based engine access control
FastAPI dependency — inject into engine routes
"""

from fastapi import Depends, HTTPException, status, Request
from firebase.firebase_service import FirebaseService
import logging

logger = logging.getLogger(__name__)

# ── Plan → Engine mapping ─────────────────────────────────
PLAN_ACCESS = {
    "free":  ["risk-profile", "news"],
    "basic": ["risk-profile", "news", "goal-planner", "retirement"],
    "pro":   ["risk-profile", "news", "goal-planner", "retirement",
              "stock-analysis", "portfolio", "global-events"],
    "elite": ["risk-profile", "news", "goal-planner", "retirement",
              "stock-analysis", "portfolio", "global-events"],
}

PLAN_RANK = {"free": 0, "basic": 1, "pro": 2, "elite": 3}


def require_plan(engine_id: str):
    """
    FastAPI dependency factory.
    Usage: @router.post("/risk-profile", dependencies=[Depends(require_plan("risk-profile"))])
    """
    async def _check(request: Request):
        uid = getattr(request.state, "uid", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Not authenticated.")

        user = FirebaseService.get_user(uid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        plan = user.get("plan", "free")
        allowed = PLAN_ACCESS.get(plan, PLAN_ACCESS["free"])

        if engine_id not in allowed:
            min_plan = _get_min_plan(engine_id)
            raise HTTPException(
                status_code=403,
                detail={
                    "error":       "plan_required",
                    "message":     f"This feature requires {min_plan.title()} plan or higher.",
                    "required_plan": min_plan,
                    "current_plan":  plan,
                    "upgrade_url":   "/pricing.html",
                }
            )
    return _check


def _get_min_plan(engine_id: str) -> str:
    for plan in ["free", "basic", "pro", "elite"]:
        if engine_id in PLAN_ACCESS[plan]:
            return plan
    return "pro"


# ── Admin access dependency ───────────────────────────────
async def require_admin(request: Request):
    uid = getattr(request.state, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if not FirebaseService.is_admin(uid):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return uid


# ── Get current user dependency ───────────────────────────
async def get_current_user(request: Request) -> dict:
    uid = getattr(request.state, "uid", None)
    if not uid:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = FirebaseService.get_user(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user
