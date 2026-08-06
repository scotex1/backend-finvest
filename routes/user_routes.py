"""
routes/user_routes.py — /api/v1/user/*

FIXES vs v1:
 [1] /user/dashboard-stats endpoint added (frontend calls this)
 [2] /user/goals GET + POST + DELETE added (frontend calls these)
 [3] profile response includes is_admin from server (not sessionStorage)
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.auth_service import AuthService
from firebase.firebase_service import PlanService, FirebaseService
from firebase_admin import firestore
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateProfileRequest(BaseModel):
    name:       Optional[str] = None
    phone:      Optional[str] = None
    city:       Optional[str] = None
    occupation: Optional[str] = None
    income:     Optional[str] = None


class GoalRequest(BaseModel):
    goal_type:     str
    goal_name:     str
    target_amount: float
    months:        int
    sip_required:  float
    annual_return: float = 12.0
    current_saved: float = 0


# ── GET /api/v1/user/profile ──────────────────────────────────
@router.get("/profile")
async def get_profile(request: Request):
    """
    [FIX 3] Returns is_admin from server — this is how frontend session
    gets is_admin set safely (not from sessionStorage spoofing).
    """
    uid = request.state.uid
    try:
        return AuthService.get_user_profile(uid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── PUT /api/v1/user/profile ──────────────────────────────────
@router.put("/profile")
async def update_profile(body: UpdateProfileRequest, request: Request):
    uid = request.state.uid
    updated = AuthService.update_profile(uid, body.model_dump(exclude_none=True))
    return updated


# ── GET /api/v1/user/plan ─────────────────────────────────────
@router.get("/plan")
async def get_plan(request: Request):
    uid = request.state.uid
    return PlanService.get_user_plan(uid)


# ── GET /api/v1/user/dashboard-stats ─────────────────────────
@router.get("/dashboard-stats")
async def dashboard_stats(request: Request):
    """
    [FIX 1] Frontend dashboard calls this — was missing in v1.
    Returns portfolio_value, active_goals, risk_profile for the user.
    """
    uid = request.state.uid
    try:
        db   = firestore.client()
        user = FirebaseService.get_user(uid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        # Goals count
        goals_ref   = db.collection("users").document(uid).collection("goals")
        goals_count = len(list(goals_ref.stream()))

        # Portfolio value (sum of holdings if stored, else 0)
        portfolio_value  = user.get("portfolio_value", 0)
        portfolio_change = user.get("portfolio_change_pct", 0)

        return {
            "portfolio_value":    portfolio_value,
            "portfolio_change":   portfolio_change,
            "active_goals":       goals_count,
            "risk_profile":       user.get("risk_profile", None),
            "risk_score":         user.get("risk_score",   None),
            "plan":               user.get("plan", "free"),
            "plan_expiry":        user.get("plan_expiry").isoformat() if user.get("plan_expiry") else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"dashboard_stats error uid={uid}: {e}")
        raise HTTPException(status_code=500, detail="Could not load dashboard stats.")


# ── GET /api/v1/user/goals ────────────────────────────────────
@router.get("/goals")
async def get_goals(request: Request):
    """[FIX 2] Frontend calls this — was missing in v1."""
    uid = request.state.uid
    try:
        db   = firestore.client()
        docs = (db.collection("users").document(uid)
                  .collection("goals")
                  .order_by("created_at", direction=firestore.Query.DESCENDING)
                  .limit(20)
                  .stream())
        goals = []
        for doc in docs:
            g = doc.to_dict()
            g["id"] = doc.id
            # Serialize datetime
            if isinstance(g.get("created_at"), datetime):
                g["created_at"] = g["created_at"].isoformat()
            goals.append(g)
        return {"goals": goals, "total": len(goals)}
    except Exception as e:
        logger.error(f"get_goals error uid={uid}: {e}")
        raise HTTPException(status_code=500, detail="Could not load goals.")


# ── POST /api/v1/user/goals ───────────────────────────────────
@router.post("/goals")
async def save_goal(body: GoalRequest, request: Request):
    """[FIX 2] Save goal to Firestore (not in-memory)."""
    uid = request.state.uid
    try:
        db  = firestore.client()
        ref = db.collection("users").document(uid).collection("goals")
        doc = ref.add({
            **body.model_dump(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        return {"success": True, "goal_id": doc[1].id}
    except Exception as e:
        logger.error(f"save_goal error uid={uid}: {e}")
        raise HTTPException(status_code=500, detail="Could not save goal.")


# ── DELETE /api/v1/user/goals/{goal_id} ───────────────────────
@router.delete("/goals/{goal_id}")
async def delete_goal(goal_id: str, request: Request):
    uid = request.state.uid
    try:
        firestore.client().collection("users").document(uid)\
                 .collection("goals").document(goal_id).delete()
        return {"success": True}
    except Exception as e:
        logger.error(f"delete_goal error uid={uid} goal={goal_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not delete goal.")
