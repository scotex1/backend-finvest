"""
services/plan_access.py — Plan access helper used across services
"""

from firebase.firebase_service import FirebaseService
from datetime import datetime

PLAN_ENGINES = {
    "free":  ["risk-profile", "news"],
    "basic": ["risk-profile", "news", "goal-planner", "retirement"],
    "pro":   ["risk-profile", "news", "goal-planner", "retirement",
              "stock-analysis", "portfolio", "global-events"],
    "elite": ["risk-profile", "news", "goal-planner", "retirement",
              "stock-analysis", "portfolio", "global-events"],
}


def get_user_plan_safe(uid: str) -> str:
    """Returns effective plan — 'free' if expired."""
    user = FirebaseService.get_user(uid)
    if not user:
        return "free"
    plan   = user.get("plan", "free")
    expiry = user.get("plan_expiry")
    if expiry and plan != "free" and datetime.utcnow() > expiry:
        return "free"
    return plan


def user_can_access(uid: str, engine_id: str) -> bool:
    plan    = get_user_plan_safe(uid)
    allowed = PLAN_ENGINES.get(plan, PLAN_ENGINES["free"])
    return engine_id in allowed
