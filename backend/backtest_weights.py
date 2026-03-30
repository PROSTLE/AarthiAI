"""
Walk-forward weight derivation for StockSense AI.
Anti-gravity Step 5: derive signal weights from 180-day backtesting
rather than the legacy designer-derived 30/25/20/12/13 allocation.

Usage:
    from backtest_weights import derive_weights, get_tcs_macro_score
    weights = derive_weights("TCS.NS", df_180d)

Quarterly re-derivation is mandatory: TCS's optimal weights shift with
the US IT budget cycle (technical matters more in Feb pre-Q4;
macro/FX matters more in July at USD realisation peak).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import time
import json
import os

# IT exporters with USD/INR sensitivity
IT_TICKERS = {"TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS"}

# Weight derivation cache path
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "trained_models", "derived_weights.json")


def get_tcs_macro_score(ticker: str, macro: dict) -> float:
    """
    Convert macro signals into a directional score (-1 to +1) for IT exporters.

    USD/INR logic:
      A rising dollar (positive usd_5d_return) = more INR per USD = revenue uplift
      A falling dollar (negative usd_5d_return) = INR appreciation = margin pressure
      Formula: positive USD return → positive score for TCS

    CNXIT vs Nifty alpha:
      Positive sector alpha (CNXIT outperforms Nifty) = IT tailwind
    """
    if ticker not in IT_TICKERS:
        return 0.0
    usd_ret    = macro.get("usd_5d_return", 0.0)
    sector_ret = macro.get("cnxit_5d_return", 0.0)
    # USD rising = good for IT exporters (positive contribution)
    usd_score    = float(np.tanh(usd_ret    * 0.5))   # scaled to ~[-0.8, 0.8]
    sector_score = float(np.tanh(sector_ret * 0.3))   # sector alpha
    combined = 0.6 * usd_score + 0.4 * sector_score
    return round(combined, 3)


def _safe_dir(val: float) -> int:
    return 1 if val > 0 else -1


def derive_weights(ticker: str, df_180d: pd.DataFrame) -> dict:
    """
    Walk-forward directional accuracy test for each independent signal.
    Uses 60-day warm-up, then evaluates 5-day forward return direction
    for each signal type on non-overlapping 5-day windows.

    Returns weights as a dict normalised to sum = 1.0:
      {"lstm": 0.xx, "enterprise": 0.xx, "technical": 0.xx,
       "sentiment": 0.xx, "macro": 0.xx}

    Falls back to conservative uniform weights if insufficient data.
    """
    from technical_signals import score_technical_signals
    from stock_data import add_technical_indicators

    UNIFORM = {"lstm": 0.22, "enterprise": 0.22, "technical": 0.22,
               "sentiment": 0.17, "macro": 0.17}

    if len(df_180d) < 80:
        print(f"[WEIGHTS] Insufficient data ({len(df_180d)} rows) — using uniform fallback")
        return UNIFORM

    signal_correct: dict[str, list[int]] = {
        "technical": [], "macro": [], "momentum_proxy": []
    }
    # Note: LSTM and enterprise are expensive to retrain per window.
    # We derive their weights via momentum proxy (5-day return direction
    # from the last close before the window) as a baseline stand-in.

    try:
        df_ind = add_technical_indicators(df_180d.copy())
    except Exception as e:
        print(f"[WEIGHTS] Feature engineering failed: {e} — using uniform fallback")
        return UNIFORM

    for t in range(60, len(df_ind) - 5, 5):
        window  = df_ind.iloc[:t].copy()
        future  = df_ind.iloc[t:t + 5]
        if len(future) < 5:
            break

        actual_5d  = (float(future["Close"].iloc[-1]) / float(window["Close"].iloc[-1]) - 1)
        actual_dir = _safe_dir(actual_5d)

        # Technical signal direction
        try:
            tech_result = score_technical_signals(window)
            tech_dir    = _safe_dir(tech_result["score"])
            signal_correct["technical"].append(1 if tech_dir == actual_dir else 0)
        except Exception:
            pass

        # Momentum proxy (simple 5-day return continuation — baseline for LSTM/enterprise)
        try:
            if len(window) >= 6:
                prev_5d_ret = (float(window["Close"].iloc[-1]) / float(window["Close"].iloc[-6]) - 1)
                mom_dir     = _safe_dir(prev_5d_ret)
                signal_correct["momentum_proxy"].append(1 if mom_dir == actual_dir else 0)
        except Exception:
            pass

    if not any(signal_correct.values()):
        print("[WEIGHTS] No walk-forward samples — using uniform fallback")
        return UNIFORM

    # Compute average directional accuracy per measured signal
    accuracy = {}
    for k, v in signal_correct.items():
        accuracy[k] = float(np.mean(v)) if v else 0.5

    print(f"[WEIGHTS] Walk-forward accuracy ({ticker}): {accuracy}")

    # Skill above 50% baseline (random)
    skill = {k: max(0.0, v - 0.5) for k, v in accuracy.items()}
    total_skill = sum(skill.values())

    if total_skill < 0.01:
        print("[WEIGHTS] No measurable skill — using uniform fallback")
        return UNIFORM

    # Map measured skills to final weight slots
    tech_skill = skill.get("technical", 0.0)
    mom_skill  = skill.get("momentum_proxy", 0.0)  # proxy for LSTM + enterprise

    # Distribute momentum proxy skill between LSTM (55%) and enterprise (45%)
    lstm_skill      = mom_skill * 0.55
    enterprise_skill = mom_skill * 0.45
    # Macro and sentiment get equal shares of remaining allocation
    # (we don't walk-forward test them here due to API cost; use conservative baseline)
    macro_skill     = min(tech_skill * 0.5, 0.08)
    sentiment_skill = min(tech_skill * 0.4, 0.06)

    raw = {
        "lstm":       lstm_skill,
        "enterprise": enterprise_skill,
        "technical":  tech_skill,
        "sentiment":  sentiment_skill,
        "macro":      macro_skill,
    }
    total = sum(raw.values())
    weights = {k: round(v / total, 3) for k, v in raw.items()}

    # Normalise to exactly 1.0
    diff = round(1.0 - sum(weights.values()), 3)
    weights["technical"] = round(weights["technical"] + diff, 3)

    print(f"[WEIGHTS] Derived weights for {ticker}: {weights}")

    # Cache the derived weights with timestamp
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        cache = {}
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE) as f:
                cache = json.load(f)
        cache[ticker] = {
            "weights":   weights,
            "accuracy":  accuracy,
            "timestamp": time.time(),
            "rows_used": len(df_ind),
        }
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
        print(f"[WEIGHTS] Cached to {_CACHE_FILE}")
    except Exception as e:
        print(f"[WEIGHTS] Cache write failed (non-fatal): {e}")

    return weights


def load_cached_weights(ticker: str, max_age_days: int = 90) -> dict | None:
    """
    Load cached derived weights for a ticker if they are within max_age_days.
    Returns None if no cache exists or cache is stale.

    Quarterly re-derivation recommended (max_age_days=90).
    """
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE) as f:
            cache = json.load(f)
        entry = cache.get(ticker)
        if not entry:
            return None
        age_days = (time.time() - entry["timestamp"]) / 86400
        if age_days > max_age_days:
            print(f"[WEIGHTS] Cache for {ticker} is {age_days:.0f} days old (>{max_age_days}) — re-derive recommended")
            return None
        print(f"[WEIGHTS] Loaded cached weights for {ticker} ({age_days:.0f}d old): {entry['weights']}")
        return entry["weights"]
    except Exception:
        return None


def run_signal_health_check() -> dict:
    """
    Anti-entropy maintenance: Run on every cold start.
    Checks liveness of all signal sources and returns a health dict.
    """
    checks = {}

    # 1. LLM liveness
    try:
        from llm_analysis import _init_gemini, _active_model
        checks["llm_live"]  = bool(_init_gemini() and _active_model is not None)
        checks["llm_model"] = _active_model or "none"
    except Exception as e:
        checks["llm_live"]  = False
        checks["llm_model"] = f"error: {e}"

    # 2. Macro data availability
    try:
        from stock_data import fetch_tcs_macro_context
        macro = fetch_tcs_macro_context()
        checks["macro_available"] = macro.get("available", False)
        checks["usd_inr"]         = macro.get("usd_inr", "N/A")
    except Exception as e:
        checks["macro_available"] = False
        checks["macro_error"]     = str(e)

    # 3. Weight cache freshness
    try:
        cached = load_cached_weights("TCS.NS", max_age_days=90)
        checks["weights_cached"]  = cached is not None
        checks["weights_fresh"]   = cached is not None
    except Exception:
        checks["weights_cached"]  = False

    print(f"[HEALTH] Signal health check: {checks}")
    return checks


if __name__ == "__main__":
    # Quick CLI: python backtest_weights.py TCS.NS
    import sys
    import yfinance as yf

    ticker = sys.argv[1] if len(sys.argv) > 1 else "TCS.NS"
    print(f"[CLI] Deriving weights for {ticker} over 180-day window...")
    df = yf.Ticker(ticker).history(period="1y")
    df.reset_index(inplace=True)
    weights = derive_weights(ticker, df.tail(180))
    print(f"[CLI] Final weights: {weights}")
    print("[CLI] Running health check...")
    run_signal_health_check()
