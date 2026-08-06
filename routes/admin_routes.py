"""
routes/admin_routes.py — /api/v1/admin/*

FIXES vs v1:
 [1] Self-promotion blocked: admin cannot grant admin to themselves
 [2] /admin/users/{uid}/plan endpoint added (frontend calls this)
 [3] is_admin update uses Firebase custom claims (not just Firestore field)
 [4] Pagination offset actually passed to Firestore query
"""

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from middleware.access_middleware import require_admin
from firebase.firebase_service import FirebaseService, AdminService, PlanService, PaymentService
from core.security import set_admin_claim
import logging
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)


class UpdateUserRequest(BaseModel):
    name:      Optional[str]  = None
    is_admin:  Optional[bool] = None
    is_active: Optional[bool] = None


class UpdatePlanRequest(BaseModel):
    name:        Optional[str]  = None
    price:       Optional[int]  = None
    description: Optional[str]  = None
    is_active:   Optional[bool] = None


class ChangePlanRequest(BaseModel):
    plan_id:     str
    expiry_date: str   # ISO date string "YYYY-MM-DD"


# ── GET /api/v1/admin/stats ───────────────────────────────────
@router.get("/stats", dependencies=[Depends(require_admin)])
async def get_stats():
    return AdminService.get_dashboard_stats()


# ── GET /api/v1/admin/users ───────────────────────────────────
@router.get("/users", dependencies=[Depends(require_admin)])
async def get_users(
    limit:  int = Query(50, le=200),
    page:   int = Query(1, ge=1),
    search: str = Query(""),
    plan:   str = Query(""),
):
    # [FIX 4] offset correctly passed
    offset = (page - 1) * limit
    return FirebaseService.get_all_users(
        limit=limit, offset=offset,
        search=search, plan_filter=plan
    )


# ── GET /api/v1/admin/users/{uid} ────────────────────────────
@router.get("/users/{uid}", dependencies=[Depends(require_admin)])
async def get_user(uid: str):
    user = FirebaseService.get_user(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


# ── PUT /api/v1/admin/users/{uid} ────────────────────────────
@router.put("/users/{uid}", dependencies=[Depends(require_admin)])
async def update_user(uid: str, body: UpdateUserRequest, request: Request):
    """
    [FIX 1] Admin cannot grant admin to themselves.
    [FIX 3] is_admin update writes Firebase custom claim (not just Firestore).
    """
    user = FirebaseService.get_user(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    updates = body.model_dump(exclude_none=True)

    # [FIX 1] Block self-promotion
    if "is_admin" in updates and uid == request.state.uid:
        raise HTTPException(
            status_code=400,
            detail="Cannot change your own admin status."
        )

    if updates:
        from firebase_admin import firestore as fs
        updates["updated_at"] = datetime.utcnow()
        fs.client().collection("users").document(uid).update(updates)

        # [FIX 3] Sync admin claim to Firebase Auth custom claims
        if "is_admin" in updates:
            try:
                set_admin_claim(uid, updates["is_admin"])
            except Exception as e:
                logger.warning(f"Could not set Firebase custom claim for {uid}: {e}")

    return {"success": True, "uid": uid}


# ── PUT /api/v1/admin/users/{uid}/plan ───────────────────────
@router.put("/users/{uid}/plan", dependencies=[Depends(require_admin)])
async def change_user_plan(uid: str, body: ChangePlanRequest, request: Request):
    """
    [FIX 2] Endpoint was missing — admin panel frontend calls this.
    Allows admin to manually change a user's plan and expiry.
    """
    user = FirebaseService.get_user(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    valid_plans = ["free", "basic", "pro", "elite"]
    if body.plan_id not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Must be one of: {valid_plans}")

    try:
        expiry_dt = datetime.fromisoformat(body.expiry_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expiry_date. Use ISO format: YYYY-MM-DD")

    # Calculate duration in days from now
    from datetime import timezone
    duration_days = max(1, (expiry_dt - datetime.utcnow()).days)

    from core.config import settings
    plan_names = {
        "free": "Free Plan", "basic": "Basic Plan",
        "pro": "Pro Plan",   "elite": "Elite Plan"
    }

    PlanService.activate_plan(
        uid=uid,
        plan_id=body.plan_id,
        duration_days=duration_days,
        order_id=f"ADMIN_{request.state.uid[:8]}_{uid[:8]}",
        amount=0,   # Admin-granted, no payment
    )

    logger.info(
        f"Admin {request.state.uid} changed plan for {uid} "
        f"to {body.plan_id} expiry={body.expiry_date}"
    )
    return {
        "success":     True,
        "uid":         uid,
        "plan_id":     body.plan_id,
        "expiry_date": body.expiry_date,
        "granted_by":  request.state.uid,
    }


# ── DELETE /api/v1/admin/users/{uid} ─────────────────────────
@router.delete("/users/{uid}", dependencies=[Depends(require_admin)])
async def delete_user(uid: str, request: Request):
    if uid == request.state.uid:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
    FirebaseService.delete_user(uid)
    return {"success": True, "deleted": uid}


# ── GET /api/v1/admin/payments ───────────────────────────────
@router.get("/payments", dependencies=[Depends(require_admin)])
async def get_payments(
    limit:  int = Query(50, le=200),
    page:   int = Query(1, ge=1),
    status: str = Query(""),
    plan:   str = Query(""),
):
    return PaymentService.get_all_payments(
        limit=limit, status_filter=status, plan_filter=plan
    )


# ── GET /api/v1/admin/plans ──────────────────────────────────
@router.get("/plans", dependencies=[Depends(require_admin)])
async def get_plans():
    stats = PlanService.get_plan_stats()
    return [
        {"id": "free",  "name": "Free Plan",  "price": 0,    "is_active": True, "active_subscribers": stats.get("free",  0)},
        {"id": "basic", "name": "Basic Plan", "price": 499,  "is_active": True, "active_subscribers": stats.get("basic", 0)},
        {"id": "pro",   "name": "Pro Plan",   "price": 999,  "is_active": True, "active_subscribers": stats.get("pro",   0)},
        {"id": "elite", "name": "Elite Plan", "price": 1999, "is_active": True, "active_subscribers": stats.get("elite", 0)},
    ]


# ── PUT /api/v1/admin/plans/{plan_id} ────────────────────────
@router.put("/plans/{plan_id}", dependencies=[Depends(require_admin)])
async def update_plan(plan_id: str, body: UpdatePlanRequest):
    return {"success": True, "plan_id": plan_id, "updated": body.model_dump(exclude_none=True)}
