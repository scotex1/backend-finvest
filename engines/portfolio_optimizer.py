"""
engines/portfolio_optimizer.py — Portfolio Optimizer Engine (PRO)

FIXED:
 - Added 'projected' field (frontend uses this)
 - risk key normalization improved
"""

import math

PORTFOLIOS = {
    "conservative": {
        "label": "Conservative Portfolio", "cagr": 8.0,
        "risk_level": "Low", "max_drawdown": "5–8%",
        "allocation": [
            {"asset":"Debt Mutual Funds",      "pct":40,"color":"#3B82F6","expected_return":"7–8%",  "examples":["HDFC Short Term Debt Fund","ICICI Pru Corporate Bond Fund"]},
            {"asset":"Fixed Deposits / Bonds", "pct":25,"color":"#06B6D4","expected_return":"6–7%",  "examples":["SBI FD (5yr)","RBI Floating Rate Bonds"]},
            {"asset":"Gold ETF / SGB",         "pct":20,"color":"#C9A84C","expected_return":"8–10%", "examples":["Nippon India Gold ETF","SGB 2024 Series"]},
            {"asset":"Large Cap Equity MF",    "pct":15,"color":"#22C55E","expected_return":"10–12%","examples":["Mirae Asset Large Cap Fund","Axis Bluechip Fund"]},
        ],
    },
    "moderate": {
        "label": "Balanced Portfolio", "cagr": 11.0,
        "risk_level": "Medium", "max_drawdown": "15–20%",
        "allocation": [
            {"asset":"Large Cap Equity MF",  "pct":35,"color":"#22C55E","expected_return":"10–12%","examples":["Mirae Asset Large Cap","UTI Nifty 50 Index Fund"]},
            {"asset":"Debt / Hybrid Fund",   "pct":25,"color":"#3B82F6","expected_return":"8–9%",  "examples":["HDFC Balanced Advantage Fund","SBI Equity Hybrid Fund"]},
            {"asset":"Mid Cap MF",           "pct":20,"color":"#F59E0B","expected_return":"12–15%","examples":["Kotak Emerging Equity Fund","Axis Mid Cap Fund"]},
            {"asset":"Gold ETF",             "pct":10,"color":"#C9A84C","expected_return":"8–10%", "examples":["Nippon India Gold ETF"]},
            {"asset":"International Fund",   "pct":10,"color":"#A78BFA","expected_return":"10–14%","examples":["Motilal Oswal Nasdaq 100","Parag Parikh Flexi Cap"]},
        ],
    },
    "moderate-aggressive": {
        "label": "Growth Portfolio", "cagr": 13.5,
        "risk_level": "Moderate-High", "max_drawdown": "25–35%",
        "allocation": [
            {"asset":"Large + Mid Cap MF",   "pct":45,"color":"#22C55E","expected_return":"12–15%","examples":["Mirae Asset Emerging Bluechip","Canara Robeco Emerging Equities"]},
            {"asset":"Small Cap MF",         "pct":20,"color":"#F59E0B","expected_return":"14–18%","examples":["Nippon India Small Cap Fund","SBI Small Cap Fund"]},
            {"asset":"International ETF",    "pct":15,"color":"#A78BFA","expected_return":"10–14%","examples":["Motilal Oswal Nasdaq 100 ETF"]},
            {"asset":"Sector / Thematic MF", "pct":10,"color":"#EC4899","expected_return":"12–20%","examples":["Mirae Asset Healthcare Fund","ICICI Pru Technology Fund"]},
            {"asset":"Gold ETF",             "pct":10,"color":"#C9A84C","expected_return":"8–10%", "examples":["Nippon India Gold ETF"]},
        ],
    },
    "aggressive": {
        "label": "Aggressive Growth Portfolio", "cagr": 16.0,
        "risk_level": "High", "max_drawdown": "40–55%",
        "allocation": [
            {"asset":"Mid + Small Cap MF",   "pct":40,"color":"#22C55E","expected_return":"14–20%","examples":["Nippon India Small Cap Fund","Kotak Small Cap Fund"]},
            {"asset":"Direct Equity (NSE)",  "pct":25,"color":"#F59E0B","expected_return":"15–25%","examples":["Build your own stock basket","Focus on quality businesses"]},
            {"asset":"International Equity", "pct":15,"color":"#A78BFA","expected_return":"10–15%","examples":["Motilal Oswal S&P 500 Index","Nasdaq 100 ETF"]},
            {"asset":"Sector / Thematic MF", "pct":15,"color":"#EC4899","expected_return":"12–22%","examples":["ICICI Pru Technology Fund","Tata Digital India Fund"]},
            {"asset":"Gold ETF",             "pct":5, "color":"#C9A84C","expected_return":"8–10%", "examples":["Nippon India Gold ETF"]},
        ],
    },
}


class PortfolioEngine:

    @staticmethod
    def optimize(amount: float, risk: str, horizon: int) -> dict:
        # Normalize risk key
        risk_key = risk.lower().strip().replace(" ", "-")
        p = PORTFOLIOS.get(risk_key, PORTFOLIOS["moderate"])

        # Projected value with CAGR
        projected = amount * math.pow(1 + p["cagr"] / 100, horizon)

        # Build allocation with rupee amounts
        allocation = []
        for asset in p["allocation"]:
            allocation.append({
                **asset,
                "amount": round(amount * asset["pct"] / 100),
            })

        return {
            "label":      p["label"],
            "risk_level": p["risk_level"],
            "cagr":       p["cagr"],
            "max_drawdown": p["max_drawdown"],
            "amount":     round(amount),
            "horizon":    horizon,
            "projected":  round(projected),    # FIX: frontend uses this field
            "returns":    round(projected - amount),
            "allocation": allocation,
        }