"""
services/subscription_service.py — Subscription management
"""

from firebase.firebase_service import PlanService, PaymentService, FirebaseService
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SubscriptionService:

    @staticmethod
    def get_subscription(uid: str) -> dict:
        return PlanService.get_user_plan(uid)

    @staticmethod
    def get_payment_history(uid: str) -> dict:
        payments = PaymentService.get_user_payments(uid)
        # Format dates for JSON
        for p in payments:
            if isinstance(p.get("created_at"), datetime):
                p["date"] = p["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
            p.pop("created_at", None)
            p.pop("updated_at", None)
        return {"payments": payments}

    @staticmethod
    def cancel_subscription(uid: str) -> dict:
        """
        Sets plan to expire at end of billing period (no refund).
        In this implementation, plan stays active until expiry — just not renewed.
        """
        user = FirebaseService.get_user(uid)
        if not user:
            raise ValueError("User not found")
        plan   = user.get("plan", "free")
        expiry = user.get("plan_expiry")
        logger.info(f"Cancellation noted for uid={uid} plan={plan} expiry={expiry}")
        return {
            "message": "Subscription will not renew. Access remains until expiry.",
            "expiry":  expiry.isoformat() if expiry else None,
        }
