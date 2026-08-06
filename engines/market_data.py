"""
engines/market_data.py — Market Data Fetcher

FIXED vs v1:
 [1] Primary source is now NSE India's public data endpoint (free, real-time,
     unofficial — no API key needed). yfinance is kept as automatic fallback
     when NSE is unreachable/blocked, and Alpha Vantage (free tier) as a
     last-resort backup.
 [2] Added fetch_price_history() — real historical OHLC data used by
     stock_analysis.py to compute actual RSI/MACD (previously approximated).

Source priority for quotes: NSE public endpoint -> yfinance -> Alpha Vantage
Source priority for history: yfinance (best free historical depth) -> Alpha Vantage
"""

import asyncio
import logging

import httpx
import yfinance as yf

from core.config import settings

logger = logging.getLogger(__name__)

NSE_BASE = "https://www.nseindia.com"
NSE_QUOTE_PATH = "/api/quote-equity"

# NSE's endpoint requires browser-like headers + a session cookie obtained
# from the homepage first, otherwise it blocks the request.
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _nse_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + ".NS"


def _bare_symbol(symbol: str) -> str:
    """Strip .NS/.BO suffix — NSE's own API wants the bare ticker."""
    return symbol.upper().strip().replace(".NS", "").replace(".BO", "")


# ════════════════════════════════════════════════════════════
# SOURCE 1 — NSE India public endpoint (free, real-time, unofficial)
# ════════════════════════════════════════════════════════════

async def _fetch_nse_quote(symbol: str) -> dict:
    bare = _bare_symbol(symbol)
    async with httpx.AsyncClient(headers=_NSE_HEADERS, timeout=10) as client:
        # NSE requires visiting the homepage first to get valid session cookies
        await client.get(NSE_BASE)
        resp = await client.get(f"{NSE_BASE}{NSE_QUOTE_PATH}", params={"symbol": bare})
        resp.raise_for_status()
        data = resp.json()

    info = data.get("info", {})
    price_info = data.get("priceInfo", {})
    price      = price_info.get("lastPrice", 0)
    prev_close = price_info.get("previousClose", price)
    change     = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0

    return {
        "name":         info.get("companyName") or symbol,
        "exchange":     "NSE",
        "sector":       data.get("industryInfo", {}).get("sector", ""),
        "industry":     data.get("industryInfo", {}).get("industry", ""),
        "price":        round(price, 2),
        "prev_close":   round(prev_close, 2),
        "change":       round(change, 2),
        "change_pct":   round(change_pct, 2),
        "day_high":     price_info.get("intraDayHighLow", {}).get("max", 0),
        "day_low":      price_info.get("intraDayHighLow", {}).get("min", 0),
        "week_52_high": price_info.get("weekHighLow", {}).get("max", 0),
        "week_52_low":  price_info.get("weekHighLow", {}).get("min", 0),
        "volume":       price_info.get("totalTradedVolume", 0),
        "market_cap":   0,   # NSE quote endpoint doesn't return market cap directly
        "source":       "nse",
    }


# ════════════════════════════════════════════════════════════
# SOURCE 2 — yfinance (fallback)
# ════════════════════════════════════════════════════════════

async def _fetch_yfinance_quote(symbol: str) -> dict:
    def _fetch():
        ticker = yf.Ticker(_nse_symbol(symbol))
        info   = ticker.info

        price      = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        prev_close = info.get("previousClose", price)
        change     = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

        return {
            "name":         info.get("longName") or info.get("shortName") or symbol,
            "exchange":     "NSE",
            "sector":       info.get("sector", ""),
            "industry":     info.get("industry", ""),
            "price":        round(price, 2),
            "prev_close":   round(prev_close, 2),
            "change":       round(change, 2),
            "change_pct":   round(change_pct, 2),
            "day_high":     info.get("dayHigh", 0),
            "day_low":      info.get("dayLow", 0),
            "week_52_high": info.get("fiftyTwoWeekHigh", 0),
            "week_52_low":  info.get("fiftyTwoWeekLow", 0),
            "volume":       info.get("volume", 0),
            "market_cap":   info.get("marketCap", 0),
            "source":       "yfinance",
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch)


# ════════════════════════════════════════════════════════════
# SOURCE 3 — Alpha Vantage (last-resort backup, free tier: 25 req/day)
# ════════════════════════════════════════════════════════════

async def _fetch_alphavantage_quote(symbol: str) -> dict:
    if not settings.ALPHA_VANTAGE_API_KEY:
        raise ValueError("ALPHA_VANTAGE_API_KEY not configured")

    bare = _bare_symbol(symbol)
    av_symbol = f"{bare}.BSE"  # Alpha Vantage's India coverage is via BSE suffix

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "GLOBAL_QUOTE",
                "symbol":   av_symbol,
                "apikey":   settings.ALPHA_VANTAGE_API_KEY,
            },
        )
        resp.raise_for_status()
        data = resp.json().get("Global Quote", {})

    if not data:
        raise ValueError(f"Alpha Vantage returned no data for {av_symbol}")

    price      = float(data.get("05. price", 0) or 0)
    prev_close = float(data.get("08. previous close", price) or price)
    change     = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0

    return {
        "name":         symbol,
        "exchange":     "BSE",
        "sector":       "",
        "industry":     "",
        "price":        round(price, 2),
        "prev_close":   round(prev_close, 2),
        "change":       round(change, 2),
        "change_pct":   round(change_pct, 2),
        "day_high":     float(data.get("03. high", 0) or 0),
        "day_low":      float(data.get("04. low", 0) or 0),
        "week_52_high": 0,
        "week_52_low":  0,
        "volume":       int(float(data.get("06. volume", 0) or 0)),
        "market_cap":   0,
        "source":       "alphavantage",
    }


# ════════════════════════════════════════════════════════════
# PUBLIC API — fallback chain: NSE -> yfinance -> Alpha Vantage
# ════════════════════════════════════════════════════════════

async def fetch_stock_quote(symbol: str) -> dict:
    """
    Fetch real-time quote, trying free sources in order of freshness/reliability.
    Raises the last error only if every source fails.
    """
    errors = []
    for name, fn in (
        ("nse", _fetch_nse_quote),
        ("yfinance", _fetch_yfinance_quote),
        ("alphavantage", _fetch_alphavantage_quote),
    ):
        try:
            return await fn(symbol)
        except Exception as e:
            errors.append(f"{name}: {e}")
            logger.warning(f"Market data source '{name}' failed for {symbol}: {e}")

    raise ValueError(
        f"Could not fetch quote for {symbol} from any source. "
        f"Tried: {' | '.join(errors)}"
    )


async def fetch_fundamentals(symbol: str) -> dict:
    """
    Fundamentals (P/E, ROE, etc.) — yfinance remains primary here since
    NSE's public endpoint and Alpha Vantage's free tier don't reliably
    cover these fields for Indian stocks.
    """
    def _fetch():
        ticker = yf.Ticker(_nse_symbol(symbol))
        info   = ticker.info
        return {
            "pe_ratio":        info.get("trailingPE", 0),
            "forward_pe":      info.get("forwardPE", 0),
            "eps":             info.get("trailingEps", 0),
            "book_value":      info.get("bookValue", 0),
            "price_to_book":   info.get("priceToBook", 0),
            "dividend_yield":  (info.get("dividendYield") or 0) * 100,
            "roe":             (info.get("returnOnEquity") or 0) * 100,
            "debt_to_equity":  info.get("debtToEquity", 0),
            "revenue_growth":  (info.get("revenueGrowth") or 0) * 100,
            "earnings_growth": (info.get("earningsGrowth") or 0) * 100,
            "profit_margin":   (info.get("profitMargins") or 0) * 100,
            "current_ratio":   info.get("currentRatio", 0),
            "beta":            info.get("beta", 1),
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch)


async def fetch_price_history(symbol: str, period: str = "6mo") -> list:
    """
    [NEW] Real daily closing prices for technical indicator calculation
    (RSI, MACD, moving averages). Returns list of floats, oldest first.
    Falls back to Alpha Vantage daily series if yfinance history is empty.
    """
    def _fetch_yf():
        ticker = yf.Ticker(_nse_symbol(symbol))
        hist = ticker.history(period=period)
        if hist is None or hist.empty:
            return []
        return [round(float(c), 2) for c in hist["Close"].tolist()]

    loop = asyncio.get_event_loop()
    closes = await loop.run_in_executor(None, _fetch_yf)
    if closes:
        return closes

    # Fallback: Alpha Vantage daily series (free tier, 25 req/day)
    if settings.ALPHA_VANTAGE_API_KEY:
        try:
            bare = _bare_symbol(symbol)
            av_symbol = f"{bare}.BSE"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://www.alphavantage.co/query",
                    params={
                        "function":   "TIME_SERIES_DAILY",
                        "symbol":     av_symbol,
                        "outputsize": "compact",
                        "apikey":     settings.ALPHA_VANTAGE_API_KEY,
                    },
                )
                resp.raise_for_status()
                series = resp.json().get("Time Series (Daily)", {})
            dates = sorted(series.keys())
            return [round(float(series[d]["4. close"]), 2) for d in dates]
        except Exception as e:
            logger.warning(f"Alpha Vantage history fallback failed for {symbol}: {e}")

    return []
