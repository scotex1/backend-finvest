"""
engines/news_analysis.py — News Analysis Engine (FREE)
Fetches financial news + categorizes + sentiment analysis

FIXED vs v1:
 [1] Multi-provider fallback chain: NewsAPI -> GNews -> Currents -> demo data.
     Any provider that isn't configured (no key) or fails is skipped
     automatically, so partial API key setups still work.
 [2] Cache moved from in-memory dict (lost on restart, not shared across
     instances) to Firestore (news_cache collection), same 15-min TTL.
     Falls back to in-memory cache if Firestore is unavailable.
"""

import httpx
from datetime import datetime, timedelta
from core.config import settings
import logging

logger = logging.getLogger(__name__)

# In-memory fallback cache (used only if Firestore write/read fails)
_local_cache: dict = {}

CATEGORY_KEYWORDS = {
    "market":       ["nifty", "sensex", "bse", "nse", "market", "index", "rally", "fall"],
    "stocks":       ["stock", "share", "equity", "ipo", "listing", "buyback", "dividend", "quarterly"],
    "mutual-funds": ["mutual fund", "sip", "nav", "aum", "scheme", "folio", "elss", "nfo"],
    "economy":      ["rbi", "gdp", "inflation", "repo rate", "budget", "fiscal", "cpi", "wpi", "rbi policy"],
    "global":       ["fed", "us market", "china", "global", "dollar", "oil", "crude", "opec", "forex"],
}

POSITIVE_WORDS = {"rally", "surge", "gain", "rise", "record", "high", "profit", "growth",
                   "bullish", "positive", "strong", "beat", "upgrade", "buy"}
NEGATIVE_WORDS = {"fall", "drop", "decline", "crash", "loss", "bearish", "weak", "sell",
                   "concern", "risk", "fear", "cut", "downgrade", "miss", "debt"}

QUERIES = {
    "all":          "India stock market finance investment",
    "market":       "Nifty Sensex BSE NSE market",
    "stocks":       "India stocks equity NSE BSE earnings",
    "mutual-funds": "mutual fund SIP NAV India",
    "economy":      "RBI India GDP inflation budget",
    "global":       "global market Fed dollar oil India impact",
}


class NewsEngine:

    @staticmethod
    async def get_curated_news(category: str = "all") -> dict:
        """
        Fetch, categorize, and return financial news.
        Tries providers in order (NewsAPI -> GNews -> Currents), falls
        back to demo data if none are configured or all fail.
        Cached in Firestore for 15 minutes (shared across all instances).
        """
        cache_key = f"news_{category}"

        cached = NewsEngine._get_cache(cache_key)
        if cached is not None:
            return cached

        articles = None
        for provider_name, fetch_fn, api_key in (
            ("newsapi",  NewsEngine._fetch_newsapi,  settings.NEWS_API_KEY),
            ("gnews",    NewsEngine._fetch_gnews,     settings.GNEWS_API_KEY),
            ("currents", NewsEngine._fetch_currents,  settings.CURRENTS_API_KEY),
        ):
            if not api_key:
                continue
            try:
                articles = await fetch_fn(category)
                if articles:
                    logger.info(f"News fetched via {provider_name} for category={category}")
                    break
            except Exception as e:
                logger.warning(f"{provider_name} failed: {e}. Trying next provider.")

        if not articles:
            articles = NewsEngine._demo_news()

        # Filter by category
        if category != "all":
            articles = [a for a in articles if a.get("category") == category]

        result = {"news": articles, "count": len(articles), "category": category,
                  "fetched_at": datetime.utcnow().isoformat()}

        NewsEngine._set_cache(cache_key, result)
        return result

    # ════════════════════════════════════════════════════
    # CACHE — Firestore primary, in-memory fallback
    # ════════════════════════════════════════════════════

    @staticmethod
    def _get_cache(cache_key: str):
        try:
            from firebase.firebase_service import EngineDataService
            cached = EngineDataService.get_news_cache(cache_key, ttl_minutes=15)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"Firestore news cache read failed, using local cache: {e}")
            entry = _local_cache.get(cache_key)
            if entry and datetime.utcnow() < entry["expires"]:
                return entry["data"]
        return None

    @staticmethod
    def _set_cache(cache_key: str, result: dict):
        try:
            from firebase.firebase_service import EngineDataService
            EngineDataService.save_news_cache(cache_key, result)
        except Exception as e:
            logger.warning(f"Firestore news cache write failed, using local cache: {e}")
        # Always also keep the local cache warm as a safety net
        _local_cache[cache_key] = {
            "data": result,
            "expires": datetime.utcnow() + timedelta(minutes=15),
        }

    # ════════════════════════════════════════════════════
    # PROVIDER 1 — NewsAPI.org
    # ════════════════════════════════════════════════════

    @staticmethod
    async def _fetch_newsapi(category: str) -> list:
        query = QUERIES.get(category, QUERIES["all"])
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        query,
                    "language": "en",
                    "sortBy":   "publishedAt",
                    "pageSize": 20,
                    "from":     (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d"),
                    "apiKey":   settings.NEWS_API_KEY,
                }
            )
            resp.raise_for_status()
            data = resp.json()

        articles = []
        for a in data.get("articles", []):
            if not a.get("title") or a["title"] == "[Removed]":
                continue
            text = a.get("title", "") + " " + a.get("description", "")
            articles.append({
                "title":     a["title"],
                "summary":   a.get("description", "")[:200],
                "url":       a.get("url", "#"),
                "source":    a.get("source", {}).get("name", "News"),
                "time_ago":  NewsEngine._time_ago(a.get("publishedAt", "")),
                "category":  NewsEngine._categorize(text),
                "sentiment": NewsEngine._sentiment(text),
            })
        return articles

    # ════════════════════════════════════════════════════
    # PROVIDER 2 — GNews.io (free: 100 req/day, production allowed)
    # ════════════════════════════════════════════════════

    @staticmethod
    async def _fetch_gnews(category: str) -> list:
        query = QUERIES.get(category, QUERIES["all"])
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://gnews.io/api/v4/search",
                params={
                    "q":       query,
                    "lang":    "en",
                    "max":     20,
                    "sortby":  "publishedAt",
                    "apikey":  settings.GNEWS_API_KEY,
                }
            )
            resp.raise_for_status()
            data = resp.json()

        articles = []
        for a in data.get("articles", []):
            if not a.get("title"):
                continue
            text = a.get("title", "") + " " + a.get("description", "")
            articles.append({
                "title":     a["title"],
                "summary":   (a.get("description") or "")[:200],
                "url":       a.get("url", "#"),
                "source":    a.get("source", {}).get("name", "News"),
                "time_ago":  NewsEngine._time_ago(a.get("publishedAt", "")),
                "category":  NewsEngine._categorize(text),
                "sentiment": NewsEngine._sentiment(text),
            })
        return articles

    # ════════════════════════════════════════════════════
    # PROVIDER 3 — Currents API (free: ~600 req/day, production allowed)
    # ════════════════════════════════════════════════════

    @staticmethod
    async def _fetch_currents(category: str) -> list:
        query = QUERIES.get(category, QUERIES["all"])
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.currentsapi.services/v1/search",
                params={
                    "keywords": query,
                    "language": "en",
                    "apiKey":   settings.CURRENTS_API_KEY,
                }
            )
            resp.raise_for_status()
            data = resp.json()

        articles = []
        for a in data.get("news", [])[:20]:
            if not a.get("title"):
                continue
            text = a.get("title", "") + " " + a.get("description", "")
            articles.append({
                "title":     a["title"],
                "summary":   (a.get("description") or "")[:200],
                "url":       a.get("url", "#"),
                "source":    a.get("author") or "News",
                "time_ago":  NewsEngine._time_ago(a.get("published", "")),
                "category":  NewsEngine._categorize(text),
                "sentiment": NewsEngine._sentiment(text),
            })
        return articles

    # ════════════════════════════════════════════════════
    # SHARED HELPERS
    # ════════════════════════════════════════════════════

    @staticmethod
    def _categorize(text: str) -> str:
        text_lower = text.lower()
        for cat, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return cat
        return "market"

    @staticmethod
    def _sentiment(text: str) -> str:
        text_lower = text.lower()
        pos = sum(1 for w in POSITIVE_WORDS if w in text_lower)
        neg = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
        if pos > neg:   return "positive"
        elif neg > pos: return "negative"
        return "neutral"

    @staticmethod
    def _time_ago(dt_str: str) -> str:
        try:
            dt   = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            diff = datetime.now(dt.tzinfo) - dt
            mins = int(diff.total_seconds() / 60)
            if mins < 60:     return f"{mins}m ago"
            elif mins < 1440: return f"{mins//60}h ago"
            else:             return f"{mins//1440}d ago"
        except Exception:
            return "Recently"

    @staticmethod
    def _demo_news() -> list:
        """Fallback demo news when no provider is configured / all failed."""
        return [
            {"title": "RBI Keeps Repo Rate Unchanged at 6.5% in Latest MPC Meeting",
             "summary": "The Monetary Policy Committee voted unanimously to hold rates, citing balanced inflation risks and supporting economic growth momentum.",
             "url": "#", "source": "Economic Times", "time_ago": "1h ago",
             "category": "economy", "sentiment": "positive"},

            {"title": "Nifty 50 Hits New High as FII Buying Returns in Large Cap Stocks",
             "summary": "Foreign institutional investors turned net buyers after three weeks of selling, injecting ₹4,200 crore into Indian equities.",
             "url": "#", "source": "Business Standard", "time_ago": "2h ago",
             "category": "market", "sentiment": "positive"},

            {"title": "TCS Reports Strong Q3 Results — Revenue Up 8.2% YoY",
             "summary": "Tata Consultancy Services beat analyst estimates with deal wins across BFSI and healthcare verticals.",
             "url": "#", "source": "Mint", "time_ago": "4h ago",
             "category": "stocks", "sentiment": "positive"},

            {"title": "SEBI Proposes Stricter Norms for Equity Mutual Fund Categorization",
             "summary": "The market regulator has proposed reclassifying mid and small cap fund exposure limits to better protect retail investors.",
             "url": "#", "source": "SEBI", "time_ago": "5h ago",
             "category": "mutual-funds", "sentiment": "neutral"},

            {"title": "US Fed Signals Possible Rate Cut in Second Half of 2025",
             "summary": "Federal Reserve minutes indicate policymakers are watching inflation data closely before committing to easing.",
             "url": "#", "source": "Bloomberg", "time_ago": "6h ago",
             "category": "global", "sentiment": "positive"},

            {"title": "India's CPI Inflation Drops to 4.8% — Lowest in 6 Months",
             "summary": "Consumer price inflation eased on falling vegetable prices, coming within RBI's comfort zone.",
             "url": "#", "source": "MoSPI", "time_ago": "8h ago",
             "category": "economy", "sentiment": "positive"},

            {"title": "Gold Prices Hit ₹73,400/10g as Geopolitical Tensions Rise",
             "summary": "Safe-haven demand drove gold to fresh highs in domestic markets.",
             "url": "#", "source": "CNBC TV18", "time_ago": "10h ago",
             "category": "market", "sentiment": "positive"},

            {"title": "Smallcap Index Underperforms — Mutual Fund Managers Turn Cautious",
             "summary": "Several fund houses have been reducing small cap exposure after valuations stretched above 5-year averages.",
             "url": "#", "source": "Moneycontrol", "time_ago": "12h ago",
             "category": "mutual-funds", "sentiment": "negative"},
        ]
