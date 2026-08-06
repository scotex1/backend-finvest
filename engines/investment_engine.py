"""
engines/investment_engine.py — Investment Advisor Engine
Combines risk profile + goals + market conditions into holistic advice
"""

from engines.risk_profile        import RiskProfileEngine
from engines.portfolio_optimizer import PortfolioEngine
from firebase.firebase_service   import FirebaseService
import logging

logger = logging.getLogger(__name__)


class InvestmentEngine:

    @staticmethod
    def get_personalized_advice(uid: str, investment_amount: float) -> dict:
        """
        Generates personalized investment recommendations
        based on user's stored risk profile and plan.
        """
        user = FirebaseService.get_user(uid)
        if not user:
            raise ValueError("User not found")

        risk_profile = user.get("risk_profile", "Moderate")
        risk_score   = user.get("risk_score",   20)

        # Map profile to risk key
        risk_map = {
            "Conservative":        "conservative",
            "Moderate":            "moderate",
            "Moderate-Aggressive": "moderate-aggressive",
            "Aggressive":          "aggressive",
        }
        risk_key = risk_map.get(risk_profile, "moderate")

        # Default 5-year horizon
        portfolio = PortfolioEngine.optimize(
            amount=investment_amount,
            risk=risk_key,
            horizon=5
        )

        return {
            "risk_profile":     risk_profile,
            "risk_score":       risk_score,
            "investment_amount": investment_amount,
            "portfolio":        portfolio,
            "message": (
                f"Based on your {risk_profile} risk profile, "
                f"here is an optimized portfolio for ₹{investment_amount:,.0f}."
            )
        }
