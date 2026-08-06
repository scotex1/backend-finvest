"""
engines/global_event_engine.py — Global Events Tracker (PRO)
Macro events + impact analysis on Indian markets
"""

from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class GlobalEventEngine:

    @staticmethod
    async def get_events() -> dict:
        """
        Returns curated macro/geopolitical events with Indian market impact.
        In production: fetch from news APIs + AI classification.
        Currently returns a well-structured curated list.
        """
        events = GlobalEventEngine._get_events_data()

        # Market sentiment summary
        sentiment = GlobalEventEngine._calculate_sentiment(events)

        return {
            "events":    events,
            "count":     len(events),
            "sentiment": sentiment,
            "fetched_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _get_events_data() -> list:
        return [
            {
                "id":      "fed-fomc-jan25",
                "flag":    "🇺🇸",
                "region":  "United States",
                "event":   "Federal Reserve FOMC Meeting — Rate Decision",
                "date":    "Jan 29, 2025",
                "status":  "upcoming",
                "impact":  "high",
                "summary": "The Fed is expected to hold rates at 5.25–5.5%. Any dovish signal could trigger a rally in emerging markets including India. Watch for the press conference language.",
                "impact_india": {
                    "equity": "positive",
                    "debt":   "positive",
                    "gold":   "neutral",
                    "inr":    "positive",
                },
                "what_to_watch": "Fed funds futures, press conference tone, dot plot revision",
            },
            {
                "id":      "india-budget-feb25",
                "flag":    "🇮🇳",
                "region":  "India",
                "event":   "Union Budget 2025–26",
                "date":    "Feb 1, 2025",
                "status":  "upcoming",
                "impact":  "high",
                "summary": "Finance Minister expected to focus on fiscal consolidation and capex push. Watch for changes to LTCG tax, STT, F&O regulations, and disinvestment targets.",
                "impact_india": {
                    "equity": "high-impact",
                    "debt":   "positive",
                    "gold":   "neutral",
                    "inr":    "neutral",
                },
                "what_to_watch": "LTCG tax changes, infra spend, fiscal deficit target",
            },
            {
                "id":      "china-gdp-q4",
                "flag":    "🇨🇳",
                "region":  "China",
                "event":   "China Q4 GDP Data Release",
                "date":    "Jan 17, 2025",
                "status":  "completed",
                "impact":  "medium",
                "summary": "China GDP grew 4.9% YoY, slightly above expectations. Stronger Chinese demand supports commodity prices and global IT outsourcing demand.",
                "impact_india": {
                    "equity": "positive",
                    "debt":   "neutral",
                    "gold":   "neutral",
                    "inr":    "neutral",
                },
                "what_to_watch": "Export demand, commodity prices, Chinese equity flows",
            },
            {
                "id":      "ecb-rate-jan25",
                "flag":    "🇪🇺",
                "region":  "Eurozone",
                "event":   "ECB Interest Rate Decision",
                "date":    "Jan 25, 2025",
                "status":  "upcoming",
                "impact":  "medium",
                "summary": "ECB expected to begin rate cuts. A weaker Euro typically strengthens the USD, which could put mild pressure on the INR and cause some FII outflows.",
                "impact_india": {
                    "equity": "neutral",
                    "debt":   "neutral",
                    "gold":   "positive",
                    "inr":    "negative",
                },
                "what_to_watch": "EUR/USD rate, European inflation data, capital flows to EMs",
            },
            {
                "id":      "opec-output-feb25",
                "flag":    "🛢️",
                "region":  "OPEC+",
                "event":   "OPEC+ Production Decision Q2 2025",
                "date":    "Feb 5, 2025",
                "status":  "upcoming",
                "impact":  "high",
                "summary": "India imports 85% of its crude oil. Any OPEC+ production cut raising oil above $90/barrel would directly widen India's CAD, pressure INR, and spike inflation.",
                "impact_india": {
                    "equity": "negative",
                    "debt":   "negative",
                    "gold":   "positive",
                    "inr":    "negative",
                },
                "what_to_watch": "Crude oil prices, India's CAD, oil & gas sector stocks",
            },
            {
                "id":      "boj-rate-jan25",
                "flag":    "🇯🇵",
                "region":  "Japan",
                "event":   "Bank of Japan Rate Hike Expectations",
                "date":    "Jan 24, 2025",
                "status":  "upcoming",
                "impact":  "medium",
                "summary": "BoJ rate hike could trigger unwinding of yen carry trades. Historically, yen carry trade unwinding causes sharp FII selling in emerging markets like India.",
                "impact_india": {
                    "equity": "negative",
                    "debt":   "neutral",
                    "gold":   "positive",
                    "inr":    "negative",
                },
                "what_to_watch": "USD/JPY, FII flows, Nifty volatility (VIX)",
            },
            {
                "id":      "us-cpi-jan25",
                "flag":    "🇺🇸",
                "region":  "United States",
                "event":   "US CPI Inflation Data — January 2025",
                "date":    "Feb 12, 2025",
                "status":  "upcoming",
                "impact":  "high",
                "summary": "Lower US CPI = higher probability of Fed rate cuts = positive for EMs including India. Higher CPI = delayed cuts = potential outflows from Indian equity and debt.",
                "impact_india": {
                    "equity": "positive",  # if lower than expected
                    "debt":   "positive",
                    "gold":   "neutral",
                    "inr":    "positive",
                },
                "what_to_watch": "Core CPI vs expectations, Fed rate probability shift",
            },
            {
                "id":      "israel-iran-tensions",
                "flag":    "🌍",
                "region":  "Middle East",
                "event":   "Ongoing Middle East Geopolitical Tensions",
                "date":    "Ongoing",
                "status":  "ongoing",
                "impact":  "medium",
                "summary": "Continued conflict in the Middle East keeps crude oil risk elevated. Strait of Hormuz disruption risk adds uncertainty to global oil supply, directly impacting India.",
                "impact_india": {
                    "equity": "negative",
                    "debt":   "negative",
                    "gold":   "positive",
                    "inr":    "negative",
                },
                "what_to_watch": "Crude oil, Brent price, India inflation expectations",
            },
        ]

    @staticmethod
    def _calculate_sentiment(events: list) -> dict:
        """Calculate overall market sentiment from event impacts."""
        pos, neg = 0, 0
        for e in events:
            if e.get("status") in ("upcoming", "ongoing"):
                for asset, signal in e.get("impact_india", {}).items():
                    if signal == "positive":   pos += 1
                    elif signal == "negative": neg += 1

        total = pos + neg or 1
        score = pos / total

        if score >= 0.65:   mood = "Bullish 📈"
        elif score >= 0.45: mood = "Cautiously Optimistic ⚖️"
        elif score >= 0.35: mood = "Mixed 🔀"
        else:               mood = "Cautious 📉"

        return {
            "mood":         mood,
            "positive_signals": pos,
            "negative_signals": neg,
            "score":        round(score * 100),
        }
