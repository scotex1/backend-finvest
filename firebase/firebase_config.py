"""
firebase/firebase_config.py — Firebase Admin SDK initialization
"""

import firebase_admin
from firebase_admin import credentials
from core.config import settings
import logging
import os

logger = logging.getLogger(__name__)

_initialized = False


def initialize_firebase():
    """Initialize Firebase Admin SDK. Safe to call multiple times."""
    global _initialized
    if _initialized or len(firebase_admin._apps):
        return

    cred_path = settings.FIREBASE_CREDENTIALS_PATH

    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"Firebase credentials not found at: {cred_path}\n"
            "Download serviceAccountKey.json from Firebase Console → Project Settings → Service Accounts"
        )

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        "projectId": settings.FIREBASE_PROJECT_ID
    })
    _initialized = True
    logger.info(f"Firebase initialized: project={settings.FIREBASE_PROJECT_ID}")
