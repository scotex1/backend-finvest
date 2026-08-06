"""
engines/retirement_calculator.py — Retirement Planner Engine (BASIC+)

FIXED:
 - Added chart_data field for frontend area chart
 - Standardized field names: corpus_needed, monthly_expense_retire, future_savings
 - Added monthly_at_retire alias for frontend compatibility
"""

import math
from datetime import datetime


class RetirementEngine:

    @staticmethod
    def calculate(params: dict) -> dict:
        current_age   = int(params["current_age"])
        retire_age    = int(params["retire_age"])
        life_exp      = int(params.get("life_expectancy", 85))
        monthly_exp   = float(params["monthly_expenses"])
        inflation     = float(params.get("inflation", 6.0)) / 100
        curr_savings  = float(params.get("current_savings", 0))
        return_pre    = float(params.get("return_pre",  12.0)) / 100
        return_post   = float(params.get("return_post",  7.0)) / 100

        if retire_age <= current_age:
            raise ValueError("Retirement age must be greater than current age")
        if life_exp <= retire_age:
            raise ValueError("Life expectancy must be greater than retirement age")

        years_to_retire  = retire_age   - current_age
        retirement_years = life_exp     - retire_age
        months_to_retire = years_to_retire  * 12
        months_in_retire = retirement_years * 12

        # Step 1: Inflation-adjusted monthly expense at retirement
        monthly_at_retire = monthly_exp * math.pow(1 + inflation, years_to_retire)

        # Step 2: Corpus needed (PV of inflation-adjusted annuity)
        r_post = return_post / 12
        real_r = ((1 + r_post) / (1 + inflation / 12)) - 1
        if real_r > 0:
            corpus = monthly_at_retire * (
                (1 - math.pow(1 + real_r, -months_in_retire)) / real_r
            )
        else:
            corpus = monthly_at_retire * months_in_retire

        # Step 3: Future value of existing savings
        future_savings = curr_savings * math.pow(1 + return_pre, years_to_retire)
        remaining      = max(0, corpus - future_savings)

        # Step 4: Monthly SIP needed
        r_pre = return_pre / 12
        if remaining > 0 and r_pre > 0 and months_to_retire > 0:
            sip = (remaining * r_pre) / (
                (math.pow(1 + r_pre, months_to_retire) - 1) * (1 + r_pre)
            )
        elif remaining > 0:
            sip = remaining / months_to_retire
        else:
            sip = 0

        sip = math.ceil(sip)

        # Step 5: Chart data — corpus growth by year
        chart_data = RetirementEngine._chart_data(
            sip=sip, r=r_pre, years=years_to_retire,
            init=curr_savings, current_age=current_age
        )

        # Step 6: Milestones
        milestones = RetirementEngine._milestones(
            sip=sip, r=r_pre, months=months_to_retire,
            init=curr_savings, corpus=corpus, current_age=current_age
        )

        return {
            # Core results — frontend uses these field names
            "corpus_needed":          round(corpus),
            "corpus_required":        round(corpus),          # alias
            "monthly_sip":            sip,
            "years_to_retire":        years_to_retire,
            "months_to_retire":       months_to_retire,
            "retirement_years":       retirement_years,

            # Expense fields
            "monthly_expense_today":  round(monthly_exp),
            "monthly_expense_retire": round(monthly_at_retire),
            "monthly_at_retire":      round(monthly_at_retire),  # alias

            # Savings fields
            "future_savings":         round(future_savings),
            "existing_corpus_fv":     round(future_savings),    # alias
            "remaining_corpus":       round(remaining),
            "total_sip_invested":     round(sip * months_to_retire),

            # Chart + milestones
            "chart_data":             chart_data,
            "milestones":             milestones,

            # Meta
            "inflation_used":         inflation * 100,
            "return_pre_used":        return_pre * 100,
            "return_post_used":       return_post * 100,
            "note": (
                f"At {inflation*100:.0f}% inflation, "
                f"₹{monthly_exp:,.0f}/month today = "
                f"₹{monthly_at_retire:,.0f}/month at retirement."
            )
        }

    @staticmethod
    def _chart_data(sip: float, r: float, years: int, init: float, current_age: int) -> list:
        """Year-by-year corpus growth for frontend area chart."""
        data = []
        for y in range(0, years + 1, max(1, years // 10)):
            m = y * 12
            if r > 0 and m > 0:
                corpus = sip * ((math.pow(1 + r, m) - 1) / r) * (1 + r) +                          init * math.pow(1 + r, m)
            else:
                corpus = sip * m + init
            data.append({
                "age":    current_age + y,
                "year":   y,
                "corpus": round(corpus),
            })
        return data

    @staticmethod
    def _milestones(sip, r, months, init, corpus, current_age):
        milestones = []
        for pct, label in [(0.25, "25% Milestone"), (0.5, "Halfway 🏁"),
                           (0.75, "75% Achieved"), (1.0, "Retirement! 🎉")]:
            m = max(1, int(months * pct))
            if r > 0:
                fv = sip * ((math.pow(1 + r, m) - 1) / r) * (1 + r) +                      init * math.pow(1 + r, m)
            else:
                fv = sip * m + init
            milestones.append({
                "age":            current_age + round(m / 12),
                "month":          m,
                "label":          label,
                "amount":         round(fv),
                "corpus":         round(fv),   # alias used in frontend
                "pct_of_corpus":  round((fv / corpus) * 100) if corpus > 0 else 0,
            })
        return milestones