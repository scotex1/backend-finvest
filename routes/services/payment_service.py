"""
services/payment_service.py — Cashfree payment gateway integration

FIXES vs v1:
 [1] return_url does NOT include plan_id (security — plan resolved server-side)
 [2] notify_url and return_url from settings (not hardcoded placeholder)
 [3] idempotency_key stored in payment record
 [4] verify_payment resolves plan from DB (plan_id param is from DB, not client)
 [5] hmac.new bug fixed → hmac.new is correct, but import was wrong in security.py
 [6] Webhook: plan already activated guard (idempotent webhook handling)
"""

import httpx
import uuid
import logging
from datetime import datetime
from core.config import settings
from firebase.firebase_service import PaymentService, PlanService, FirebaseService

logger = logging.getLogger(__name__)

CASHFREE_HEADERS = {
    "Content-Type":    "application/json",
    "x-api-version":   "2023-08-01",
    "x-client-id":     settings.CASHFREE_APP_ID,
    "x-client-secret": settings.CASHFREE_SECRET_KEY,
}


class CashfreeService:

    # ── Create Order ──────────────────────────────────────────
    @staticmethod
    async def create_order(uid: str, plan_id: str, idempotency_key: str = "") -> dict:
        """
        Creates a Cashfree order. Amount is resolved from settings — never from client.
        [FIX 1] return_url does not include plan_id.
        [FIX 2] URLs come from settings, not hardcoded.
        [FIX 3] idempotency_key stored in record.
        """
        amount_paise = settings.PLAN_PRICES.get(plan_id)
        if not amount_paise:
            raise ValueError(f"Invalid plan: {plan_id}. Valid: {list(settings.PLAN_PRICES.keys())}")

        amount_rupees = amount_paise / 100
        order_id      = f"FV_{uid[:8]}_{uuid.uuid4().hex[:8].upper()}"

        user = FirebaseService.get_user(uid)
        if not user:
            raise ValueError("User not found.")

        # [FIX 1] return_url has NO plan_id — backend resolves from order_id
        # [FIX 2] Domain from settings
        frontend_url = getattr(settings, "FRONTEND_URL", "https://yourdomain.com")
        backend_url  = getattr(settings, "BACKEND_URL",  "https://your-backend.com")

        payload = {
            "order_id":       order_id,
            "order_amount":   amount_rupees,
            "order_currency": "INR",
            "customer_details": {
                "customer_id":    uid,
                "customer_email": user.get("email", ""),
                "customer_name":  user.get("name", "User"),
                "customer_phone": user.get("phone", "9999999999"),
            },
            "order_meta": {
                # [FIX 1] Only order_id in return URL — no plan_id
                "return_url":  f"{frontend_url}/dashboard/subscription.html?order_id={order_id}&order_status={{order_status}}",
                "notify_url":  f"{backend_url}/api/v1/payment/webhook",
            },
            "order_note": f"FinVest Pro — {plan_id} subscription",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.CASHFREE_BASE_URL}/orders",
                json=payload,
                headers=CASHFREE_HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        # Save pending payment record with idempotency_key
        PaymentService.create_payment_record(
            uid=uid,
            order_id=order_id,
            plan_id=plan_id,
            amount=amount_paise,
            idempotency_key=idempotency_key,
        )

        logger.info(f"Order created: {order_id} uid={uid} plan={plan_id} amount=₹{amount_rupees}")
        return {
            "order_id":           order_id,
            "payment_session_id": data.get("payment_session_id"),
            "amount":             amount_rupees,
            # plan_id returned for frontend display only — backend never trusts this on verify
        }

    # ── Verify Payment ────────────────────────────────────────
    @staticmethod
    async def verify_payment(uid: str, order_id: str, plan_id: str) -> dict:
        """
        [FIX 4] plan_id here comes from DB (passed by route after DB lookup),
        NOT from the client request. This method itself is safe as long as
        callers pass plan_id from DB.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.CASHFREE_BASE_URL}/orders/{order_id}",
                headers=CASHFREE_HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            order_data = resp.json()

        cf_status = order_data.get("order_status")
        logger.info(f"Cashfree status for {order_id}: {cf_status}")

        if cf_status == "PAID":
            duration    = settings.PLAN_DURATIONS.get(plan_id, 30)
            expiry_date = PlanService.activate_plan(
                uid=uid,
                plan_id=plan_id,
                duration_days=duration,
                order_id=order_id,
                amount=settings.PLAN_PRICES.get(plan_id, 0),
            )

            user = FirebaseService.get_user(uid)
            PaymentService.update_payment_status(
                order_id=order_id,
                status="SUCCESS",
                payment_id=str(order_data.get("cf_order_id", "")),
                user_email=user.get("email", "") if user else "",
            )

            base_plan = plan_id.replace("_yearly", "")
            plan_names = {
                "basic": "Basic Plan", "pro": "Pro Plan",
                "elite": "Elite Plan", "free": "Free Plan",
            }

            return {
                "success":     True,
                "message":     "Payment successful! Plan activated.",
                "plan_id":     base_plan,
                "plan_name":   plan_names.get(base_plan, base_plan),
                "expiry_date": expiry_date,
                "amount":      settings.PLAN_PRICES.get(plan_id, 0) / 100,
            }

        elif cf_status in ("ACTIVE", "PENDING"):
            PaymentService.update_payment_status(order_id, "PENDING")
            return {"success": False, "status": "PENDING", "message": "Payment is being processed."}

        else:
            PaymentService.update_payment_status(order_id, "FAILED")
            return {"success": False, "status": "FAILED", "message": f"Payment failed: {cf_status}"}

    # ── Webhook Handler ───────────────────────────────────────
    @staticmethod
    async def handle_webhook(payload: dict) -> dict:
        """
        [FIX 6] Idempotent — checks if plan already activated before processing.
        Signature already verified in the route before this is called.
        """
        data         = payload.get("data", {})
        order_data   = data.get("order",   {})
        payment_data = data.get("payment", {})

        order_id  = order_data.get("order_id", "")
        cf_status = payment_data.get("payment_status", "")

        if not order_id:
            logger.warning("Webhook: missing order_id in payload")
            return {"status": "ignored", "reason": "no_order_id"}

        payment = PaymentService.get_payment(order_id)
        if not payment:
            logger.warning(f"Webhook for unknown order: {order_id}")
            return {"status": "unknown_order"}

        # [FIX 6] Idempotency — skip if already processed
        if payment.get("status") == "SUCCESS" and cf_status == "SUCCESS":
            logger.info(f"Webhook: order {order_id} already activated — skipping")
            return {"status": "already_processed"}

        if cf_status == "SUCCESS":
            uid     = payment.get("uid")
            plan_id = payment.get("plan")
            if uid and plan_id:
                duration = settings.PLAN_DURATIONS.get(plan_id, 30)
                PlanService.activate_plan(
                    uid=uid, plan_id=plan_id,
                    duration_days=duration,
                    order_id=order_id,
                    amount=payment.get("amount", 0),
                )
                PaymentService.update_payment_status(
                    order_id, "SUCCESS",
                    payment_id=str(payment_data.get("cf_payment_id", "")),
                )
                logger.info(f"Webhook activated plan: uid={uid} plan={plan_id} order={order_id}")

        elif cf_status == "FAILED":
            PaymentService.update_payment_status(order_id, "FAILED")
            logger.info(f"Webhook: payment failed for order={order_id}")

        return {"status": "processed"}
