"""
engines/risk_profile.py — Risk Profile Engine (FREE)
Saves user risk score to Firestore + returns detailed profile
"""

from firebase_admin import firestore
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ── Profile definitions ───────────────────────────────────
PROFILES = {
    "Conservative": {
        "emoji": "🛡️",
        "score_range": (10, 16),
        "description": (
            "You prioritize capital preservation above all. Stability and predictable "
            "returns matter more to you than high growth. Ideal instruments: FDs, Debt Funds, "
            "Government Bonds, Gold."
        ),
        "allocation": {
            "Debt Mutual Funds":  40,
            "Fixed Deposits":     25,
            "Gold ETF":           20,
            "Large Cap Equity MF": 15,
        },
        "expected_cagr": "7–9%",
        "risk_level":    "Low",
        "volatility":    "Very Low",
        "suitable_for":  ["Retirees", "Risk-averse investors", "Short horizon < 2 yrs"],
        "avoid":         ["Small cap stocks", "Crypto", "Futures & Options"],
    },
    "Moderate": {
        "emoji": "⚖️",
        "score_range": (17, 24),
        "description": (
            "You seek a balance between growth and capital safety. You can tolerate "
            "moderate short-term volatility for better long-term returns. Suitable for "
            "a diversified mix of equity and debt."
        ),
        "allocation": {
            "Large Cap Equity MF": 35,
            "Debt / Hybrid Fund":  30,
            "Mid Cap MF":          20,
            "Gold ETF":            15,
        },
        "expected_cagr": "10–12%",
        "risk_level":    "Medium",
        "volatility":    "Moderate",
        "suitable_for":  ["Working professionals", "5-7 yr horizon", "First-time investors"],
        "avoid":         ["Heavy small caps", "Leveraged positions", "Illiquid assets"],
    },
    "Moderate-Aggressive": {
        "emoji": "📈",
        "score_range": (25, 32),
        "description": (
            "You have above-average risk tolerance and seek stronger long-term returns. "
            "You understand that short-term corrections are part of the process and stay "
            "invested through volatility."
        ),
        "allocation": {
            "Large + Mid Cap MF":  45,
            "Small Cap MF":        20,
            "International ETF":   15,
            "Debt Funds":          10,
            "Gold ETF":            10,
        },
        "expected_cagr": "12–15%",
        "risk_level":    "Moderate-High",
        "volatility":    "High",
        "suitable_for":  ["Age 25–40", "Long horizon 7-10 yrs", "Experienced investors"],
        "avoid":         ["Panic selling in corrections", "Over-concentration in one sector"],
    },
    "Aggressive": {
        "emoji": "🚀",
        "score_range": (33, 40),
        "description": (
            "You have a high risk appetite and are focused on maximum long-term wealth "
            "creation. You can withstand significant drawdowns (30-50%) without losing "
            "sleep and have a long investment horizon."
        ),
        "allocation": {
            "Mid + Small Cap MF":  40,
            "Direct Stocks":       25,
            "International Equity": 15,
            "Thematic / Sector MF": 15,
            "Gold ETF":             5,
        },
        "expected_cagr": "15–20%",
        "risk_level":    "High",
        "volatility":    "Very High",
        "suitable_for":  ["Age under 35", "10+ yr horizon", "High income, low liabilities"],
        "avoid":         ["F&O without expertise", "Concentrated bets", "Borrowed money investing"],
    },
}


def _get_profile(score: int) -> dict:
    for name, data in PROFILES.items():
        lo, hi = data["score_range"]
        if lo <= score <= hi:
            return {"name": name, **data}
    # Fallback
    return {"name": "Moderate", **PROFILES["Moderate"]}


class RiskProfileEngine:

    @staticmethod
    def save_and_analyze(uid: str, score: int, profile_name: str, answers: list) -> dict:
        """
        Saves quiz result to Firestore and returns enriched profile data.
        """
        profile = _get_profile(score)

        # Save to Firestore
        try:
            db  = firestore.client()
            ref = db.collection("users").document(uid)
            ref.update({
                "risk_score":   score,
                "risk_profile": profile["name"],
                "updated_at":   datetime.utcnow(),
            })
            # Also save full result in a sub-collection
            db.collection("users").document(uid)\
              .collection("risk_profiles")\
              .add({
                  "score":      score,
                  "profile":    profile["name"],
                  "answers":    answers,
                  "created_at": datetime.utcnow(),
              })
        except Exception as e:
            logger.warning(f"Could not save risk profile for {uid}: {e}")

        return {
            "score":       score,
            "max_score":   40,
            "percentage":  round(((score - 10) / 30) * 100),
            "profile":     profile["name"],
            "emoji":       profile["emoji"],
            "description": profile["description"],
            "allocation":  profile["allocation"],
            "expected_cagr": profile["expected_cagr"],
            "risk_level":  profile["risk_level"],
            "volatility":  profile["volatility"],
            "suitable_for": profile["suitable_for"],
            "avoid":       profile["avoid"],
        }

    @staticmethod
    def get_profile_only(score: int) -> dict:
        """Stateless helper — just returns profile for a given score."""
        return _get_profile(score)
