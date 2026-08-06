"""
engines/goal_planner.py — Goal Planner Engine (BASIC+)

FIXED:
 - Removed auto-save from engine (frontend calls POST /user/goals separately)
 - Engine now only calculates and returns result
"""

from datetime import datetime
from dateutil.relativedelta import relativedelta
import math
import logging

logger = logging.getLogger(__name__)

GOAL_ICONS = {
    "home":"🏠", "car":"🚗", "education":"🎓", "wedding":"💍",
    "travel":"✈️", "emergency":"🛡️", "business":"💼", "custom":"🎯",
}


class GoalPlannerEngine:

    @staticmethod
    def calculate(uid: str, params: dict) -> dict:
        goal_type     = params.get("goal_type", "custom")
        goal_name     = params.get("goal_name", "My Goal")
        target_amount = float(params.get("target_amount", 0))
        target_date   = params.get("target_date", "")
        current_saved = float(params.get("current_saved", 0))
        annual_return = float(params.get("annual_return", 12.0))

        if target_amount <= 0:
            raise ValueError("Target amount must be positive")

        # Parse months from YYYY-MM
        try:
            target_dt = datetime.strptime(target_date, "%Y-%m")
            now       = datetime.utcnow().replace(day=1)
            rd        = relativedelta(target_dt, now)
            months    = max(1, rd.months + rd.years * 12)
        except Exception:
            raise ValueError("Invalid target_date. Use format: YYYY-MM")

        r  = annual_return / 100 / 12
        fv = target_amount - current_saved

        if fv <= 0:
            return {
                "sip_required": 0, "months": months,
                "goal_name": goal_name, "goal_type": goal_type,
                "goal_icon": GOAL_ICONS.get(goal_type, "🎯"),
                "target_amount": target_amount, "current_saved": current_saved,
                "total_invested": 0, "returns_earned": 0, "progress_pct": 100,
                "message": "You already have enough saved! 🎉",
                "milestones": [],
            }

        # SIP = FV * r / [((1+r)^n - 1) * (1+r)]
        if r == 0:
            sip = fv / months
        else:
            sip = (fv * r) / ((math.pow(1 + r, months) - 1) * (1 + r))

        sip            = math.ceil(sip)
        total_invested = sip * months
        returns_earned = max(0, fv - total_invested)
        progress_pct   = min(100, round((current_saved / target_amount) * 100))
        lumpsum        = fv / math.pow(1 + r, months) if r > 0 else fv
        milestones     = GoalPlannerEngine._milestones(sip, r, months, current_saved, target_amount)

        # NOTE: No auto-save here — frontend calls POST /user/goals separately
        return {
            "goal_name":      goal_name,
            "goal_type":      goal_type,
            "goal_icon":      GOAL_ICONS.get(goal_type, "🎯"),
            "target_amount":  target_amount,
            "current_saved":  current_saved,
            "months":         months,
            "years":          round(months / 12, 1),
            "annual_return":  annual_return,
            "sip_required":   sip,
            "lumpsum_needed": round(lumpsum),
            "total_invested": round(total_invested),
            "returns_earned": round(returns_earned),
            "progress_pct":   progress_pct,
            "milestones":     milestones,
        }

    @staticmethod
    def _milestones(sip, r, total_months, initial, target):
        milestones = []
        for pct, label in [(0.25,"25% Mark"),(0.5,"Halfway"),(0.75,"75% Done"),(1.0,"Goal Achieved! 🎉")]:
            m = max(1, int(total_months * pct))
            if r > 0:
                fv = sip * ((math.pow(1+r,m)-1)/r)*(1+r) + initial*math.pow(1+r,m)
            else:
                fv = sip * m + initial
            milestones.append({
                "month": m, "label": label,
                "amount": round(fv), "pct": round((fv/target)*100),
            })
        return milestones