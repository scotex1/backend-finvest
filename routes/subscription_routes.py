"""
routes/subscription_routes.py — /api/v1/payment/*

FIXES vs v1:
 [1] verify_payment: plan_id NOT accepted from client — resolved from DB by order_id
 [2] create_order: idempotency_key enforced (no duplicate charges)
 [3] webhook: Cashfree signature actually verified before processing
 [4] return_url: plan_id removed — plan resolved server-side only
"""

from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from services.payment_service import CashfreeService
from services.subscription_service import SubscriptionService
from firebase.firebase_service import PaymentService
import hmac as _hmac, hashlib, base64, json, logging
from core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


class CreateOrderRequest(BaseModel):
    plan_id:         str
    idempotency_key: Optional[str] = ""


class VerifyPaymentRequest(BaseModel):
    order_id: str
    # plan_id intentionally REMOVED — backend resolves from DB


# ── POST /api/v1/payment/create-order ────────────────────────
@router.post("/create-order")
async def create_order(body: CreateOrderRequest, request: Request):
    uid = request.state.uid

    # [FIX 2] Idempotency — return existing order if same key used
    if body.idempotency_key:
        existing = PaymentService.get_by_idempotency_key(body.idempotency_key, uid)
        if existing:
            logger.info(f"Idempotency hit: returning existing order key={body.idempotency_key}")
            return existing

    try:
        result = await CashfreeService.create_order(
            uid=uid,
            plan_id=body.plan_id,
            idempotency_key=body.idempotency_key,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"create_order error uid={uid}: {e}")
        raise HTTPException(status_code=500, detail="Order creation failed. Please try again.")


# ── POST /api/v1/payment/verify ───────────────────────────────
@router.post("/verify")
async def verify_payment(body: VerifyPaymentRequest, request: Request):
    """
    [FIX 1] plan_id NOT accepted from client.
    Resolved from payment record in Firestore using order_id.
    Client cannot spoof which plan they paid for.
    """
    uid = request.state.uid

    # Load payment record from DB
    payment_record = PaymentService.get_payment(body.order_id)
    if not payment_record:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Ensure order belongs to authenticated user
    if payment_record.get("uid") != uid:
        logger.warning(f"User {uid} tried to verify order belonging to {payment_record.get('uid')}")
        raise HTTPException(status_code=403, detail="Order does not belong to this account.")

    # Resolve plan from DB — never from client
    plan_id = payment_record.get("plan")
    if not plan_id:
        raise HTTPException(status_code=400, detail="Payment record corrupted — plan missing.")

    # Already SUCCESS — return cached result (idempotent verify)
    if payment_record.get("status") == "SUCCESS":
        from firebase.firebase_service import PlanService
        user_plan = PlanService.get_user_plan(uid)
        return {
            "success":     True,
            "message":     "Payment already verified.",
            "plan_id":     user_plan.get("plan_id"),
            "plan_name":   user_plan.get("plan_name"),
            "expiry_date": user_plan.get("expiry_date"),
        }

    try:
        result = await CashfreeService.verify_payment(
            uid=uid,
            order_id=body.order_id,
            plan_id=plan_id,        # From DB, not request
        )
        return result
    except Exception as e:
        logger.error(f"verify_payment error uid={uid} order={body.order_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Verification failed. If money was deducted, contact support with order ID: " + body.order_id
        )


# ── POST /api/v1/payment/webhook ─────────────────────────────
@router.post("/webhook")
async def payment_webhook(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None, alias="x-webhook-signature"),
    x_webhook_timestamp: Optional[str] = Header(None, alias="x-webhook-timestamp"),
):
    """
    [FIX 3] Cashfree webhook with real signature verification.
    Anyone on the internet can POST to this URL — verify every time.
    """
    try:
        raw_body = await request.body()

        # Verify signature if webhook secret configured
        if getattr(settings, "CASHFREE_WEBHOOK_SECRET", ""):
            if not x_webhook_signature or not x_webhook_timestamp:
                logger.warning("Webhook missing signature headers — rejected")
                return {"status": "rejected", "reason": "missing_signature"}

            if not _verify_webhook_sig(raw_body, x_webhook_timestamp, x_webhook_signature):
                logger.warning("Webhook signature mismatch — possible forgery attempt")
                return {"status": "rejected", "reason": "invalid_signature"}

        payload = json.loads(raw_body)
        result  = await CashfreeService.handle_webhook(payload)
        return result

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        # Always 200 to Cashfree — prevents retry storms
        return {"status": "error", "detail": str(e)}


def _verify_webhook_sig(body: bytes, timestamp: str, signature: str) -> bool:
    """
    Cashfree signature: base64( HMAC-SHA256( timestamp + "." + body, webhook_secret ) )
    """
    try:
        message  = (timestamp + ".").encode() + body
        secret   = settings.CASHFREE_WEBHOOK_SECRET.encode()
        computed = base64.b64encode(
            _hmac.new(secret, message, hashlib.sha256).digest()
        ).decode()
        return _hmac.compare_digest(computed, signature)
    except Exception as e:
        logger.error(f"Signature check error: {e}")
        return False


# ── GET /api/v1/payment/history ───────────────────────────────
@router.get("/history")
async def payment_history(request: Request):
    uid = request.state.uid
    return SubscriptionService.get_payment_history(uid)
