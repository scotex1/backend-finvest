"""
services/auth_service.py — Auth business logic
"""

from firebase.firebase_service import FirebaseService
from firebase_admin import auth as firebase_auth
import logging

logger = logging.getLogger(__name__)


class AuthService:

    @staticmethod
    def sync_user(uid: str, email: str, name: str = "", photo: str = "") -> dict:
        """
        Called when user logs in from frontend.
        Creates user in Firestore if first time, else updates.
        """
        user = FirebaseService.create_or_update_user(uid, {
            "email": email,
            "name":  name or email.split("@")[0],
            "photo": photo or "",
        })
        logger.info(f"User synced: uid={uid} email={email}")
        return {
            "uid":      uid,
            "email":    user.get("email"),
            "name":     user.get("name"),
            "plan":     user.get("plan", "free"),
            "is_admin": user.get("is_admin", False),
        }

    @staticmethod
    def get_user_profile(uid: str) -> dict:
        user = FirebaseService.get_user(uid)
        if not user:
            raise ValueError(f"User not found: {uid}")
        return {
            "uid":        uid,
            "email":      user.get("email"),
            "name":       user.get("name"),
            "photo":      user.get("photo"),
            "phone":      user.get("phone"),
            "city":       user.get("city"),
            "occupation": user.get("occupation"),
            "income":     user.get("income"),
            "plan":       user.get("plan", "free"),
            "plan_name":  user.get("plan_name", "Free"),
            "is_admin":   user.get("is_admin", False),
            "created_at": user.get("created_at"),
        }

    @staticmethod
    def update_profile(uid: str, data: dict) -> dict:
        FirebaseService.update_user_profile(uid, data)
        return AuthService.get_user_profile(uid)

    @staticmethod
    def delete_firebase_user(uid: str):
        """Hard delete from Firebase Auth + Firestore."""
        try:
            firebase_auth.delete_user(uid)
        except Exception as e:
            logger.warning(f"Could not delete Firebase Auth user {uid}: {e}")
        FirebaseService.delete_user(uid)
        logger.info(f"User deleted: {uid}")
