"""
engines/stock_analysis.py — Stock Analysis Engine (PRO)
Fundamental + Technical analysis with AI-generated summary

FIXED vs v1:
 [1] RSI/MACD/moving averages now computed from REAL daily closing price
     history (via market_data.fetch_price_history), instead of being
     approximated from the 52-week high/low range.
 [2] Result is now saved to Firestore (users/{uid}/stock_analysis/) so
     users can see their analysis history — pass uid=None to skip saving
     (e.g. for anonymous/preview calls).
"""

import asyncio
from engines.market_data import fetch_stock_quote, fetch_fundamentals, fetch_price_history
from core.config import settings
import logging

logger = logging.getLogger(__name__)


class StockAnalysisEngine:

    @staticmethod
    async def analyze(symbol: str, uid: str = None) -> dict:
        """
        Full stock analysis:
        1. Fetch quote + fundamentals + price history in parallel
        2. Calculate REAL technical signals (RSI/MACD/MA from history)
        3. Generate buy/hold/sell verdict
        4. AI summary (if configured)
        5. Save result to Firestore (if uid provided)
        """
        # Parallel fetch
        quote_task   = fetch_stock_quote(symbol)
        fund_task    = fetch_fundamentals(symbol)
        history_task = fetch_price_history(symbol)
        quote, fundamentals, history = await asyncio.gather(
            quote_task, fund_task, history_task, return_exceptions=True
        )

        if isinstance(quote, Exception):
            raise ValueError(f"Could not find stock: {symbol}. Check the symbol and try again.")

        if isinstance(fundamentals, Exception):
            fundamentals = {}

        if isinstance(history, Exception) or not history:
            history = []

        # Technical signals — real calculation if we have history,
        # otherwise fall back to the 52-week-range approximation.
        if len(history) >= 15:
            technicals = StockAnalysisEngine._technicals_from_history(history, quote)
        else:
            logger.warning(
                f"No/insufficient price history for {symbol} ({len(history)} points) — "
                f"falling back to approximated technicals."
            )
            technicals = StockAnalysisEngine._technicals_approx(quote, fundamentals)

        # Verdict
        verdict = StockAnalysisEngine._verdict(fundamentals, technicals)

        # AI summary
        ai_summary = await StockAnalysisEngine._ai_summary(
            symbol, quote, fundamentals, technicals, verdict
        )

        # Format market cap
        mcap = quote.get("market_cap", 0)
        if mcap >= 1e12:
            mcap_str = f"₹{mcap/1e12:.1f}L Cr"
        elif mcap >= 1e9:
            mcap_str = f"₹{mcap/1e9:.0f}K Cr"
        elif mcap >= 1e7:
            mcap_str = f"₹{mcap/1e7:.0f} Cr"
        else:
            mcap_str = "N/A"

        result = {
            # Quote data
            "symbol":       symbol,
            "name":         quote.get("name", symbol),
            "exchange":     quote.get("exchange", "NSE"),
            "data_source":  quote.get("source", "unknown"),
            "price":        quote.get("price", 0),
            "prev_close":   quote.get("prev_close", 0),
            "change":       quote.get("change", 0),
            "change_pct":   quote.get("change_pct", 0),
            "day_high":     quote.get("day_high", 0),
            "day_low":      quote.get("day_low", 0),
            "week_52_high": quote.get("week_52_high", 0),
            "week_52_low":  quote.get("week_52_low", 0),
            "volume":       quote.get("volume", 0),
            "mcap":         mcap_str,
            # Fundamentals
            "pe":              fundamentals.get("pe_ratio", 0),
            "forward_pe":      fundamentals.get("forward_pe", 0),
            "eps":             fundamentals.get("eps", 0),
            "book_value":      fundamentals.get("book_value", 0),
            "price_to_book":   fundamentals.get("price_to_book", 0),
            "dividend_yield":  fundamentals.get("dividend_yield", 0),
            "roe":             fundamentals.get("roe", 0),
            "de":              fundamentals.get("debt_to_equity", 0),
            "revenue_growth":  fundamentals.get("revenue_growth", 0),
            "profit_growth":   fundamentals.get("earnings_growth", 0),
            "profit_margin":   fundamentals.get("profit_margin", 0),
            # Technicals
            "rsi":        technicals.get("rsi"),
            "rsi_signal": technicals.get("rsi_signal"),
            "macd":       technicals.get("macd"),
            "macd_signal_source": technicals.get("source", "approx"),
            "ma50":       technicals.get("ma50"),
            "ma200":      technicals.get("ma200"),
            "momentum":   technicals.get("momentum"),
            # Verdict & Summary
            "verdict":    verdict,
            "ai_summary": ai_summary,
        }

        # Save to Firestore history (best-effort — never blocks the response)
        if uid:
            try:
                from firebase.firebase_service import EngineDataService
                EngineDataService.save_stock_analysis(uid, result)
            except Exception as e:
                logger.warning(f"Could not save stock analysis for {uid}/{symbol}: {e}")

        return result

    @staticmethod
    def _technicals_approx(quote: dict, fundamentals: dict) -> dict:
        """
        FALLBACK ONLY — used when no real price history is available.
        Rough approximation derived from the 52-week high/low range.
        """
        price     = quote.get("price", 0)
        w52_high  = quote.get("week_52_high", price)
        w52_low   = quote.get("week_52_low",  price)
        change_pct = quote.get("change_pct", 0)

        range_52 = w52_high - w52_low if w52_high > w52_low else 1
        pos_in_range = (price - w52_low) / range_52  # 0 to 1
        rsi = round(30 + pos_in_range * 40)  # Simplified 30–70 range

        if rsi > 70:
            rsi_signal = "Overbought"
        elif rsi < 30:
            rsi_signal = "Oversold"
        else:
            rsi_signal = "Neutral"

        macd = "Bullish" if change_pct > 0 else "Bearish"

        ma50_above  = price > (w52_low + (range_52 * 0.35))
        ma200_above = price > (w52_low + (range_52 * 0.20))

        momentum = "Strong" if change_pct > 2 else \
                   "Moderate" if change_pct > 0 else \
                   "Weak" if change_pct > -2 else "Negative"

        return {
            "rsi":        rsi,
            "rsi_signal": rsi_signal,
            "macd":       macd,
            "ma50":       "Above" if ma50_above else "Below",
            "ma200":      "Above" if ma200_above else "Below",
            "momentum":   momentum,
            "source":     "approx",
        }

    @staticmethod
    def _technicals_from_history(closes: list, quote: dict) -> dict:
        """
        [NEW] Real technical indicators computed from actual daily closing
        prices (standard formulas — no external TA library needed).
        """
        price = closes[-1]

        # ── RSI (14-day, Wilder's smoothing) ──────────────────
        period = 14
        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))

        if len(gains) >= period:
            avg_gain = sum(gains[:period]) / period
            avg_loss = sum(losses[:period]) / period
            for i in range(period, len(gains)):
                avg_gain = (avg_gain * (period - 1) + gains[i]) / period
                avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs  = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
        else:
            rsi = 50.0
        rsi = round(rsi)

        if rsi > 70:
            rsi_signal = "Overbought"
        elif rsi < 30:
            rsi_signal = "Oversold"
        else:
            rsi_signal = "Neutral"

        # ── MACD (12-day EMA − 26-day EMA, 9-day signal line) ──
        def _ema(values: list, span: int) -> list:
            k = 2 / (span + 1)
            ema = [values[0]]
            for v in values[1:]:
                ema.append(v * k + ema[-1] * (1 - k))
            return ema

        if len(closes) >= 26:
            ema12 = _ema(closes, 12)
            ema26 = _ema(closes, 26)
            macd_line = [a - b for a, b in zip(ema12, ema26)]
            signal_line = _ema(macd_line, 9) if len(macd_line) >= 9 else macd_line
            macd_val   = macd_line[-1]
            signal_val = signal_line[-1]
            macd = "Bullish" if macd_val > signal_val else "Bearish"
        else:
            # Not enough history for a proper MACD — fall back to momentum
            macd = "Bullish" if closes[-1] > closes[0] else "Bearish"

        # ── Moving averages (50-day / 200-day, or as much history as we have) ──
        def _sma(values: list, window: int):
            if len(values) < window:
                return sum(values) / len(values)
            return sum(values[-window:]) / window

        ma50  = _sma(closes, min(50, len(closes)))
        ma200 = _sma(closes, min(200, len(closes)))

        change_pct = quote.get("change_pct", 0)
        momentum = "Strong" if change_pct > 2 else \
                   "Moderate" if change_pct > 0 else \
                   "Weak" if change_pct > -2 else "Negative"

        return {
            "rsi":        rsi,
            "rsi_signal": rsi_signal,
            "macd":       macd,
            "ma50":       "Above" if price > ma50 else "Below",
            "ma200":      "Above" if price > ma200 else "Below",
            "momentum":   momentum,
            "source":     "history",
        }

    @staticmethod
    def _verdict(fundamentals: dict, technicals: dict) -> str:
        """
        Rule-based buy/hold/sell verdict combining fundamentals + technicals.
        """
        score = 0

        # Fundamental scoring
        pe = fundamentals.get("pe_ratio", 0)
        if 0 < pe < 20:   score += 2
        elif 20 <= pe < 35: score += 1
        elif pe >= 35:    score -= 1

        roe = fundamentals.get("roe", 0)
        if roe > 20:   score += 2
        elif roe > 12: score += 1
        elif roe < 5:  score -= 1

        de = fundamentals.get("debt_to_equity", 0)
        if de < 0.3:    score += 1
        elif de > 1.5:  score -= 2

        rev_growth = fundamentals.get("revenue_growth", 0)
        if rev_growth > 15:  score += 2
        elif rev_growth > 8: score += 1
        elif rev_growth < 0: score -= 1

        # Technical scoring
        if technicals.get("macd") == "Bullish":    score += 1
        if technicals.get("ma50")  == "Above":     score += 1
        if technicals.get("ma200") == "Above":     score += 1
        if technicals.get("rsi_signal") == "Oversold":   score += 1
        if technicals.get("rsi_signal") == "Overbought": score -= 1
        if technicals.get("momentum") == "Strong":  score += 1
        if technicals.get("momentum") == "Negative": score -= 1

        if score >= 6:   return "STRONG BUY"
        elif score >= 3: return "BUY"
        elif score >= 0: return "HOLD"
        elif score >= -3: return "SELL"
        else:            return "STRONG SELL"

    @staticmethod
    async def _ai_summary(symbol: str, quote: dict, fundamentals: dict,
                           technicals: dict, verdict: str) -> str:
        """
        Generates AI narrative summary.
        Uses OpenAI/Claude if API key configured, else rule-based fallback.
        """
        # Rule-based fallback (always available)
        pe     = fundamentals.get("pe_ratio", 0)
        roe    = fundamentals.get("roe", 0)
        de     = fundamentals.get("debt_to_equity", 0)
        rev_g  = fundamentals.get("revenue_growth", 0)
        profit = fundamentals.get("profit_margin", 0)
        price  = quote.get("price", 0)
        w52h   = quote.get("week_52_high", 0)
        w52l   = quote.get("week_52_low",  0)

        from_high = round(((w52h - price) / w52h) * 100, 1) if w52h else 0
        from_low  = round(((price - w52l) / w52l) * 100, 1) if w52l else 0

        valuation = (
            "undervalued relative to peers" if pe and pe < 15 else
            "fairly valued" if pe and pe < 30 else
            "trading at a premium" if pe else "valuation data unavailable"
        )

        roe_comment = (
            "excellent return on equity, indicating efficient use of capital" if roe > 20 else
            "decent return on equity" if roe > 12 else
            "below-average return on equity" if roe else ""
        )

        debt_comment = (
            "virtually debt-free balance sheet" if de < 0.2 else
            "manageable debt levels" if de < 0.8 else
            "elevated debt levels that warrant caution" if de < 1.5 else
            "high debt burden — monitor closely"
        )

        verdict_comment = {
            "STRONG BUY": "Strong fundamentals combined with positive momentum make this a compelling investment opportunity.",
            "BUY":        "Solid fundamentals with positive technical outlook. Consider accumulating on dips.",
            "HOLD":       "Current holders may stay invested. New buyers should wait for a better entry point.",
            "SELL":       "Weakening fundamentals or overvaluation suggest reducing exposure.",
            "STRONG SELL": "Multiple red flags in fundamentals and technicals. Consider exiting positions."
        }.get(verdict, "")

        summary = (
            f"{symbol} is currently {valuation}, trading {from_low:.1f}% above its 52-week low "
            f"and {from_high:.1f}% below its 52-week high. "
        )
        if roe_comment:
            summary += f"The company shows {roe_comment}. "
        summary += f"The balance sheet reflects {debt_comment}. "
        if rev_g:
            summary += f"Revenue growth stands at {rev_g:.1f}%, "
            summary += "indicating healthy top-line expansion. " if rev_g > 10 else "showing moderate growth. "
        summary += f"{verdict_comment} "
        summary += "Note: This analysis is for educational purposes only and is not SEBI-registered investment advice."

        # Optional: Use Claude/OpenAI for richer summary
        if settings.ANTHROPIC_API_KEY:
            try:
                summary = await StockAnalysisEngine._claude_summary(
                    symbol, quote, fundamentals, technicals, verdict
                )
            except Exception as e:
                logger.warning(f"Claude summary failed, using fallback: {e}")

        return summary

    @staticmethod
    async def _claude_summary(symbol, quote, fundamentals, technicals, verdict) -> str:
        """Optional: Claude API for enriched narrative."""
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""You are a financial analyst. Write a 3-4 sentence investment analysis for {symbol}.

Data:
- Price: ₹{quote.get('price')} | Change: {quote.get('change_pct')}%
- P/E: {fundamentals.get('pe_ratio')} | ROE: {fundamentals.get('roe')}% | D/E: {fundamentals.get('debt_to_equity')}
- Revenue Growth: {fundamentals.get('revenue_growth')}% | Profit Margin: {fundamentals.get('profit_margin')}%
- RSI: {technicals.get('rsi')} ({technicals.get('rsi_signal')}) | MACD: {technicals.get('macd')}
- 52W: ₹{quote.get('week_52_low')} - ₹{quote.get('week_52_high')}
- Verdict: {verdict}

Rules:
- Be factual and concise
- End with: "Not SEBI-registered investment advice."
- Do not recommend specific investment amounts"""

        msg = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text
