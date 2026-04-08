"""
LLM Market Analysis via Google Gemini API (google-genai SDK).
Provides directional market insight (-1 to +1) with reasoning.
Falls back gracefully to neutral (0) on API errors or quota exhaustion.
Hardens against WinError 10053 with httpx no-proxy transport + retry logic.
"""

from __future__ import annotations
import os
import json
import time
import math
from dotenv import load_dotenv

# Load .env first
load_dotenv()

# ── New google-genai SDK ──────────────────────────────────────────────────────
GEMINI_AVAILABLE = False
_gemini_client = None
_httpx_available = False

try:
    from google import genai as _genai_sdk
    GEMINI_AVAILABLE = True
except ImportError:
    pass

try:
    import httpx
    _httpx_available = True
except ImportError:
    pass


def _make_client():
    """Build a Gemini client, bypassing Windows proxy issues with httpx if available.
    WinError 10053 is typically caused by Windows firewall/proxy intercepting the
    TCP connection. Using httpx with proxies={} bypasses system proxy settings.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or not GEMINI_AVAILABLE:
        return None
    if _httpx_available:
        try:
            transport = httpx.HTTPTransport(retries=2)
            http_client = httpx.Client(
                transport=transport,
                proxies={},                          # bypass system proxy
                timeout=httpx.Timeout(30.0, connect=10.0),
                verify=True,
            )
            return _genai_sdk.Client(api_key=api_key, http_client=http_client)
        except Exception:
            pass
    # Fallback: default client (no httpx)
    return _genai_sdk.Client(api_key=api_key)

# ── Model selection (tried in order until one works) ──────────────────────────
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-flash-latest",
]
_active_model: str | None = None

# Connection retry settings
_MAX_RETRIES = 3
_RETRY_DELAY = 1.5  # seconds, doubles on each retry

# ── Cache: 30-minute TTL per ticker ──────────────────────────────────────────
_LLM_CACHE_TTL = 30 * 60
_llm_cache: dict = {}  # {ticker: {"result": ..., "timestamp": ...}}
_TASK_EPS = 1e-6


def _to_task_score(signed_score: float) -> float:
    try:
        value = float(signed_score)
    except (TypeError, ValueError):
        value = 0.0
    if not math.isfinite(value):
        value = 0.0
    value = max(-1.0, min(1.0, value))
    normalized = (value + 1.0) / 2.0
    return max(_TASK_EPS, min(1.0 - _TASK_EPS, normalized))


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
    WinError 10053 is retried up to _MAX_RETRIES times.
    """
    global _gemini_client, _active_model

    # Check cache first
    cached = _get_cached(ticker)
    if cached is not None:
        return cached

    # Default fallback
    fallback = {
        "score": 0.5,
        "signed_score": 0.0,
        "direction": "neutral",
        "reasoning": "Gemini LLM offline — technical & sentiment signals active (13% weight held)",
        "source": "fallback",
        "confidence": 0.0,   # weight redistributes to technical/sentiment
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

    last_error = ""
    for attempt in range(_MAX_RETRIES):
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
            signed_score = max(-1.0, min(1.0, float(parsed.get("score", 0))))

            result = {
                "score": round(_to_task_score(signed_score), 6),
                "signed_score": round(signed_score, 3),
                "direction": parsed.get("direction", "neutral"),
                "reasoning": parsed.get("reasoning", ""),
                "source": f"gemini/{_active_model}",
                "confidence": 1.0,
            }
            _set_cached(ticker, result)
            return result

        except Exception as e:
            error_msg = str(e)
            last_error = error_msg

            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                fallback["reasoning"] = "Gemini quota limit reached — technical/sentiment active (13% weight held)"
                _gemini_client = None
                _active_model = None
                break

            elif "API_KEY_INVALID" in error_msg or "API key expired" in error_msg:
                fallback["reasoning"] = "Gemini API key issue — technical/sentiment active (13% weight held)"
                _gemini_client = None
                _active_model = None
                break

            elif "10053" in error_msg or "WinError" in error_msg or "ConnectionAborted" in error_msg or "ConnectionReset" in error_msg:
                # Windows TCP connection aborted — rebuild client and retry
                wait = _RETRY_DELAY * (2 ** attempt)
                print(f"[LLM] WinError 10053 on {ticker} (attempt {attempt+1}/{_MAX_RETRIES}), rebuilding connection in {wait:.1f}s...")
                time.sleep(wait)
                # Rebuild connection with fresh client
                try:
                    _gemini_client = _make_client()
                    _active_model = None
                    # Re-init model probe
                    for model in GEMINI_MODELS:
                        try:
                            _gemini_client.models.generate_content(model=model, contents="ping")
                            _active_model = model
                            break
                        except Exception:
                            continue
                    if _active_model is None:
                        break
                except Exception:
                    break
            else:
                # Other error — don't retry
                fallback["reasoning"] = f"Gemini unavailable — technical/sentiment active (13% weight held)"
                _set_cached(ticker, fallback)
                return fallback

    # All retries exhausted
    print(f"[LLM] All retries failed for {ticker}: {last_error[:80]}")
    fallback["reasoning"] = "Gemini connection failed after retries — technical/sentiment active (13% weight held)"
    _set_cached(ticker, fallback)
    return fallback
