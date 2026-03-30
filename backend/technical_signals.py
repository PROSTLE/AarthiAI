"""
Technical signal scoring.
Converts raw indicator values into a directional score (-1 to +1).
Each signal has an individual sub-score; the aggregate is weighted.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def score_technical_signals(df: pd.DataFrame) -> dict:
    """
    Analyze technical indicators and return a composite score.

    Returns:
        {
            "score": float (-1 to +1),
            "direction": "bullish" | "bearish" | "neutral",
            "signals": {name: {"score": float, "value": float, "interpretation": str}},
        }
    """
    latest = df.iloc[-1]
    signals = {}

    # ── 1. RSI (weight: 25%) ──────────────────────────
    rsi = float(latest.get("RSI", 50))
    if rsi >= 75:
        rsi_score = -0.8  # overbought → bearish
        rsi_interp = "Overbought"
    elif rsi >= 65:
        rsi_score = -0.3
        rsi_interp = "Slightly overbought"
    elif rsi <= 25:
        rsi_score = 0.8  # oversold → bullish
        rsi_interp = "Oversold"
    elif rsi <= 35:
        rsi_score = 0.3
        rsi_interp = "Slightly oversold"
    else:
        rsi_score = 0.0
        rsi_interp = "Neutral"
    signals["RSI"] = {"score": rsi_score, "value": round(rsi, 2), "interpretation": rsi_interp}

    # ── 2. MACD Crossover (weight: 25%) ───────────────
    macd = float(latest.get("MACD", 0))
    macd_signal = float(latest.get("MACD_Signal", 0))
    macd_diff = macd - macd_signal
    if abs(macd_diff) < 0.01:
        macd_score = 0.0
        macd_interp = "Neutral"
    elif macd_diff > 0:
        macd_score = min(0.8, macd_diff * 10)  # bullish crossover
        macd_interp = "Bullish crossover"
    else:
        macd_score = max(-0.8, macd_diff * 10)  # bearish crossover
        macd_interp = "Bearish crossover"
    signals["MACD"] = {"score": round(macd_score, 3), "value": round(macd_diff, 4), "interpretation": macd_interp}

    # ── 3. SMA Trend (weight: 20%) ────────────────────
    price = float(latest["Close"])
    sma20 = float(latest.get("SMA_20", price))
    sma50 = float(latest.get("SMA_50", price))
    above_sma20 = price > sma20
    above_sma50 = price > sma50
    sma20_above_50 = sma20 > sma50  # golden cross

    if above_sma20 and above_sma50 and sma20_above_50:
        sma_score = 0.7  # strong uptrend
        sma_interp = "Strong uptrend (Golden Cross)"
    elif above_sma20 and above_sma50:
        sma_score = 0.4
        sma_interp = "Uptrend"
    elif not above_sma20 and not above_sma50 and not sma20_above_50:
        sma_score = -0.7  # strong downtrend
        sma_interp = "Strong downtrend (Death Cross)"
    elif not above_sma20 and not above_sma50:
        sma_score = -0.4
        sma_interp = "Downtrend"
    else:
        sma_score = 0.0
        sma_interp = "Mixed trend"
    signals["SMA_Trend"] = {"score": sma_score, "value": round(price - sma20, 2), "interpretation": sma_interp}

    # ── 4. Bollinger Band Width (weight: 15%) ─────────
    bb_width = float(latest.get("BB_Width", 0))
    bb_upper = float(latest.get("BB_Upper", price))
    bb_lower = float(latest.get("BB_Lower", price))

    if price >= bb_upper * 0.99:
        bb_score = -0.5  # near upper band → reversal risk
        bb_interp = "Near upper band"
    elif price <= bb_lower * 1.01:
        bb_score = 0.5  # near lower band → bounce potential
        bb_interp = "Near lower band"
    else:
        bb_score = 0.0
        bb_interp = "Within bands"
    signals["Bollinger"] = {"score": bb_score, "value": round(bb_width, 4), "interpretation": bb_interp}

    # ── 5. ATR Volatility (weight: 15%) ───────────────
    atr = float(latest.get("ATR", 0))
    atr_pct = (atr / price * 100) if price > 0 else 0
    if atr_pct > 3.0:
        atr_score = -0.3  # high volatility = risk
        atr_interp = "High volatility"
    elif atr_pct > 2.0:
        atr_score = -0.1
        atr_interp = "Moderate volatility"
    else:
        atr_score = 0.1
        atr_interp = "Low volatility"
    signals["ATR"] = {"score": atr_score, "value": round(atr_pct, 2), "interpretation": atr_interp}

    # ── Weighted composite ────────────────────────────
    weights = {"RSI": 0.25, "MACD": 0.25, "SMA_Trend": 0.20, "Bollinger": 0.15, "ATR": 0.15}
    composite = sum(signals[k]["score"] * weights[k] for k in weights)
    composite = max(-1.0, min(1.0, composite))

    if composite > 0.15:
        direction = "bullish"
    elif composite < -0.15:
        direction = "bearish"
    else:
        direction = "neutral"

    return {
        "score": round(composite, 3),
        "direction": direction,
        "signals": signals,
    }
