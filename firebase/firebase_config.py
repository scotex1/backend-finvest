import os
import json
import logging
import firebase_admin
from firebase_admin import credentials

from core.config import settings

logger = logging.getLogger(__name__)

_initialized = False


def initialize_firebase():
    global _initialized

    if _initialized or firebase_admin._apps:
        return firebase_admin.get_app()

    try:
        firebase_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

        if not firebase_json:
            raise ValueError("FIREBASE_CREDENTIALS_JSON missing")

        # =========================
        # STEP 1: CLEAN INPUT (IMPORTANT)
        # =========================
        firebase_json = firebase_json.strip()

        # Remove hidden newline corruption (Render issue fix)
        firebase_json = firebase_json.replace("\r", "")

        # =========================
        # STEP 2: PARSE JSON SAFELY
        # =========================
        cred_dict = json.loads(firebase_json)

        # =========================
        # STEP 3: FIX PRIVATE KEY FORMATTING
        # =========================
        if "private_key" in cred_dict:
            key = cred_dict["private_key"]

            # handle all cases: \\n or real new lines
            key = key.replace("\\n", "\n")

            cred_dict["private_key"] = key

        # =========================
        # STEP 4: INIT FIREBASE
        # =========================
        cred = credentials.Certificate(cred_dict)

        firebase_admin.initialize_app(
            cred,
            {
                "projectId": cred_dict.get("project_id") or settings.FIREBASE_PROJECT_ID
            }
        )

        _initialized = True
        logger.info("Firebase initialized successfully")

        return firebase_admin.get_app()

    except Exception as e:
        logger.exception("Firebase initialization failed")
        raise RuntimeError(f"Firebase init error: {str(e)}")

