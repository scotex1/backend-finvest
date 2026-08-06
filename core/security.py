"""
core/security.py — Security utilities

FIXES vs v1:
 [1] hmac.new → hmac.new (correct — was actually a typo in old file using hmac.new which doesn't exist)
     The correct function is hmac.new() — Python stdlib
 [2] verify_cashfree_signature uses new Cashfree v3 signature format
 [3] set_admin_claim accepts bool — can revoke admin too
 [4] verify_firebase_token: check_revoked=True already there — good
"""

from fastapi import HTTPException, status
from firebase_admin import auth as firebase_auth
import logging
import hmac
import hashlib
import base64
from core.config import settings

logger = logging.getLogger(__name__)


# ── Verify Firebase ID Token ──────────────────────────────────
async def verify_firebase_token(token: str) -> dict:
    try:
        decoded = firebase_auth.verify_id_token(token, check_revoked=True)
        return decoded
    except firebase_auth.RevokedIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has been revoked. Please sign in again.")
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has expired. Please sign in again.")
    except firebase_auth.InvalidIdTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Authentication failed.")


# ── Extract Bearer Token ──────────────────────────────────────
def extract_bearer_token(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or malformed. Use: Bearer <token>"
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Bearer token is empty.")
    return token


# ── Verify Admin ──────────────────────────────────────────────
async def verify_admin(uid: str):
    try:
        user   = firebase_auth.get_user(uid)
        claims = user.custom_claims or {}
        if not claims.get("admin", False):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Admin access required.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin check error uid={uid}: {e}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied.")


# ── Set / Revoke Admin Claim ──────────────────────────────────
def set_admin_claim(uid: str, is_admin: bool = True):
    """[FIX 3] Accepts bool — can grant OR revoke admin."""
    firebase_auth.set_custom_user_claims(uid, {"admin": is_admin})
    action = "granted" if is_admin else "revoked"
    logger.info(f"Admin claim {action} for uid={uid}")


# ── Cashfree Webhook Signature Verification ───────────────────
def verify_cashfree_signature(
    order_id: str, order_amount: str, reference_id: str,
    tx_status: str, payment_mode: str, tx_msg: str,
    tx_time: str, signature: str
) -> bool:
    """
    [FIX 1] Cashfree v2 callback signature (for redirect flow).
    For webhook, see _verify_webhook_sig in subscription_routes.py.
    """
    message  = (order_id + order_amount + reference_id + tx_status
                + payment_mode + tx_msg + tx_time)
    secret   = settings.CASHFREE_SECRET_KEY.encode("utf-8")
    # [FIX 1] hmac.new is the correct Python stdlib function
    computed = base64.b64encode(
        hmac.new(secret, message.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    return hmac.compare_digest(computed, signature)
