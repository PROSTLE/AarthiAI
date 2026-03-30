"""
LLM Market Analysis via Google Gemini API (google-genai SDK).
Provides directional market insight (-1 to +1) with reasoning.
Falls back gracefully to neutral (0) on API errors or quota exhaustion.
"""

from __future__ import annotations
import os
import json
import time
from dotenv import load_dotenv

# Load .env first
load_dotenv()

# ── New google-genai SDK ──────────────────────────────────────────────────────
GEMINI_AVAILABLE = False
_gemini_client = None

try:
    from google import genai as _genai_sdk
    GEMINI_AVAILABLE = True
except ImportError:
    pass

# ── Model selection (tried in order until one works) ──────────────────────────
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-latest",
]
_active_model: str | None = None

# ── Cache: 30-minute TTL per ticker ──────────────────────────────────────────
_LLM_CACHE_TTL = 30 * 60
_llm_cache: dict = {}  # {ticker: {"result": ..., "timestamp": ...}}


def _get_cached(ticker: str) -> dict | None:
    entry = _llm_cache.get(ticker)
    if entry and (time.time() - entry["timestamp"]) < _LLM_CACHE_TTL:
        return entry["result"]
    return None


def _set_cached(ticker: str, result: dict):
    _llm_cache[ticker] = {"result": result, "timestamp": time.time()}
    if len(_llm_cache) > 30:
        oldest = min(_llm_cache, key=lambda k: _llm_cache[k]["timestamp"])
        del _llm_cache[oldest]


def _init_gemini() -> bool:
    global _gemini_client, _active_model

    if _gemini_client is not None and _active_model is not None:
        return True

    if not GEMINI_AVAILABLE:
        print("[LLM] ERROR: google-genai SDK not installed.")
        return False

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[LLM] ERROR: GEMINI_API_KEY not found in environment!")
        return False

    try:
        _gemini_client = _genai_sdk.Client(api_key=api_key)
        # Pick the first model that responds
        for model in GEMINI_MODELS:
            try:
                _gemini_client.models.generate_content(
                    model=model, contents="ping"
                )
                _active_model = model
                print(f"[LLM] Ready: {model}")
                return True
            except Exception as probe_err:
                msg = str(probe_err)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    print(f"[LLM] {model}: quota exhausted, trying next model...")
                    continue
                elif "404" in msg or "NOT_FOUND" in msg:
                    print(f"[LLM] {model}: not found, trying next model...")
                    continue
                else:
                    print(f"[LLM] {model}: {msg[:80]}")
                    continue

        print("[LLM] All Gemini models exhausted quota or unavailable.")
        _gemini_client = None
        return False

    except Exception as e:
        print(f"[LLM] Gemini init error: {e}")
        _gemini_client = None
        return False


def _build_prompt(
    ticker: str,
    current_price: float,
    indicators: dict,
    sentiment_score: float,
    sentiment_label: str,
    recent_prices: list[float],
) -> str:
    """Build a concise prompt for market analysis."""
    price_change_5d = ((current_price - recent_prices[0]) / recent_prices[0] * 100) if recent_prices else 0

    return f"""You are a stock market analyst. Analyze this Indian stock and give a prediction bias.

STOCK: {ticker}
CURRENT PRICE: ₹{current_price:.2f}
5-DAY PRICE CHANGE: {price_change_5d:+.2f}%
RECENT 5 CLOSES: {[round(p,2) for p in recent_prices[-5:]]}

TECHNICAL INDICATORS:
- RSI: {indicators.get('RSI', 'N/A')} (>70 overbought, <30 oversold)
- MACD: {indicators.get('MACD', 'N/A')} (Signal: {indicators.get('MACD_Signal', 'N/A')})
- SMA_20: {indicators.get('SMA_20', 'N/A')} | SMA_50: {indicators.get('SMA_50', 'N/A')}
- BB_Width: {indicators.get('BB_Width', 'N/A')} | ATR: {indicators.get('ATR', 'N/A')}

NEWS SENTIMENT: {sentiment_label} (score: {sentiment_score:+.3f})

Respond ONLY with this exact JSON format, no other text:
{{"score": <float between -1.0 and 1.0>, "direction": "<bullish/bearish/neutral>", "reasoning": "<one sentence>"}}

Score guide: -1.0 = very bearish, 0 = neutral, +1.0 = very bullish"""


def analyze_with_llm(
    ticker: str,
    current_price: float,
    indicators: dict,
    sentiment_score: float = 0.0,
    sentiment_label: str = "neutral",
    recent_prices: list[float] | None = None,
) -> dict:
    """
    Get LLM market analysis. Returns:
      {"score": float, "direction": str, "reasoning": str, "source": str}
    Falls back to neutral if Gemini is unavailable or quota is exhausted.
    """
    # Must declare global before any use of these names in this function
    global _gemini_client, _active_model

    # Check cache first
    cached = _get_cached(ticker)
    if cached is not None:
        return cached

    # Default fallback
    fallback = {
        "score": 0.0,
        "direction": "neutral",
        "reasoning": "LLM analysis unavailable — using technical/sentiment signals only",
        "source": "fallback",
    }

    if not _init_gemini():
        _set_cached(ticker, fallback)
        return fallback

    if recent_prices is None:
        recent_prices = [current_price]

    prompt = _build_prompt(
        ticker, current_price, indicators,
        sentiment_score, sentiment_label, recent_prices,
    )

    try:
        response = _gemini_client.models.generate_content(
            model=_active_model,
            contents=prompt,
        )
        text = response.text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)
        score = max(-1.0, min(1.0, float(parsed.get("score", 0))))

        result = {
            "score": round(score, 3),
            "direction": parsed.get("direction", "neutral"),
            "reasoning": parsed.get("reasoning", ""),
            "source": f"gemini/{_active_model}",
        }
        _set_cached(ticker, result)
        return result

    except Exception as e:
        error_msg = str(e)

        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            # Quota hit — reset so next call tries to find a working model
            fallback["reasoning"] = "LLM quota exhausted — using technical/sentiment signals only"
            _gemini_client = None
            _active_model = None
        elif "API_KEY_INVALID" in error_msg or "API key expired" in error_msg:
            fallback["reasoning"] = "LLM API key invalid/expired — using technical/sentiment signals only"
            _gemini_client = None
            _active_model = None
        else:
            fallback["reasoning"] = f"LLM analysis failed: {error_msg[:100]}"
            # Cache non-auth errors so we don't spam the API
            _set_cached(ticker, fallback)

        return fallback
