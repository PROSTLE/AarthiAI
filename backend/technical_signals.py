"""
Technical signal scoring — Anti-gravity upgraded.
Converts raw indicator values into a directional score (-1 to +1).

Anti-gravity changes (2026-03-31):
  RSI: blends RSI(5) 70% + RSI(14) 30% to align with the 5-day prediction horizon.
       RSI(14) answers a 14-day question; our target is 5 days.
  MACD: uses histogram ACCELERATION (slope of last 3 bars) instead of static level
        crossover. Acceleration captures momentum direction changes over ~5 days,
        not the 3-6 week trend that EMA(26) implies.
  Weights: RSI 25%→30% (now more accurate), ATR 15%→10% (it's regime, not direction).
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

    # ── 1. RSI — HORIZON ALIGNED (weight: 30%) ────────────────────────────────
    # RSI(14) answers a 14-day momentum question; our target is 5-day.
    # Blend RSI(5) [70%] + RSI(14) [30%] to weight toward the prediction horizon
    # while retaining medium-term context as a sanity anchor.
    rsi_14 = float(latest.get("RSI", 50))
    rsi_5  = float(latest.get("RSI_5", rsi_14))   # RSI_5 added by stock_data.py upgrade
    rsi    = 0.70 * rsi_5 + 0.30 * rsi_14          # horizon-weighted blend

    if rsi >= 75:
        rsi_score = -0.8
        rsi_interp = "Overbought"
    elif rsi >= 65:
        rsi_score = -0.3
        rsi_interp = "Slightly overbought"
    elif rsi <= 25:
        rsi_score = 0.8
        rsi_interp = "Oversold"
    elif rsi <= 35:
        rsi_score = 0.3
        rsi_interp = "Slightly oversold"
    else:
        rsi_score = 0.0
        rsi_interp = "Neutral"
    signals["RSI"] = {"score": rsi_score, "value": round(rsi, 2), "interpretation": rsi_interp}

    # ── 2. MACD Momentum Acceleration (weight: 25%) ───────────────────────────
    # Static MACD crossover answers a 3-6 week question (uses EMA(26)).
    # For a 5-day forecast, histogram ACCELERATION is more informative:
    # the slope of the last 3 histogram bars captures whether bullish/bearish
    # momentum is growing or fading over the correct time window.
    macd = float(latest.get("MACD", 0))
    macd_signal_val = float(latest.get("MACD_Signal", 0))
    macd_diff = macd - macd_signal_val

    # Prefer acceleration when MACD_Hist column is available (added by stock_data upgrade)
    if "MACD_Hist" in df.columns and len(df) >= 3:
        hist_vals = df["MACD_Hist"].values[-3:]
        h = [float(v) for v in hist_vals]
        macd_accel = (h[-1] - h[0]) / 2.0          # slope per bar
        macd_score = max(-0.8, min(0.8, macd_accel * 50))
        if macd_accel > 0.005:
            macd_interp = "Bullish momentum accelerating"
        elif macd_accel < -0.005:
            macd_interp = "Bearish momentum accelerating"
        else:
            macd_interp = "Momentum flat"
    elif abs(macd_diff) < 0.01:
        macd_score = 0.0
        macd_interp = "Neutral"
    elif macd_diff > 0:
        macd_score = min(0.8, macd_diff * 10)
        macd_interp = "Bullish crossover"
    else:
        macd_score = max(-0.8, macd_diff * 10)
        macd_interp = "Bearish crossover"
    signals["MACD"] = {"score": round(macd_score, 3), "value": round(macd_diff, 4), "interpretation": macd_interp}

    # ── 3. SMA Trend (weight: 20%) ────────────────────────────────────────────
    price = float(latest["Close"])
    sma20 = float(latest.get("SMA_20", price))
    sma50 = float(latest.get("SMA_50", price))
    above_sma20 = price > sma20
    above_sma50 = price > sma50
    sma20_above_50 = sma20 > sma50  # golden cross

    if above_sma20 and above_sma50 and sma20_above_50:
        sma_score = 0.7
        sma_interp = "Strong uptrend (Golden Cross)"
    elif above_sma20 and above_sma50:
        sma_score = 0.4
        sma_interp = "Uptrend"
    elif not above_sma20 and not above_sma50 and not sma20_above_50:
        sma_score = -0.7
        sma_interp = "Strong downtrend (Death Cross)"
    elif not above_sma20 and not above_sma50:
        sma_score = -0.4
        sma_interp = "Downtrend"
    else:
        sma_score = 0.0
        sma_interp = "Mixed trend"
    signals["SMA_Trend"] = {"score": sma_score, "value": round(price - sma20, 2), "interpretation": sma_interp}

    # ── 4. Bollinger Band Width (weight: 15%) ─────────────────────────────────
    bb_width = float(latest.get("BB_Width", 0))
    bb_upper = float(latest.get("BB_Upper", price))
    bb_lower = float(latest.get("BB_Lower", price))

    if price >= bb_upper * 0.99:
        bb_score = -0.5
        bb_interp = "Near upper band"
    elif price <= bb_lower * 1.01:
        bb_score = 0.5
        bb_interp = "Near lower band"
    else:
        bb_score = 0.0
        bb_interp = "Within bands"
    signals["Bollinger"] = {"score": bb_score, "value": round(bb_width, 4), "interpretation": bb_interp}

    # ── 5. ATR Volatility (weight: 10%) ───────────────────────────────────────
    # Reduced from 15%: ATR is a regime signal (used for SL/TP sizing),
    # not a directional predictor for 5-day returns.
    atr = float(latest.get("ATR", 0))
    atr_pct = (atr / price * 100) if price > 0 else 0
    if atr_pct > 3.0:
        atr_score = -0.3
        atr_interp = "High volatility"
    elif atr_pct > 2.0:
        atr_score = -0.1
        atr_interp = "Moderate volatility"
    else:
        atr_score = 0.1
        atr_interp = "Low volatility"
    signals["ATR"] = {"score": atr_score, "value": round(atr_pct, 2), "interpretation": atr_interp}

    # ── Weighted composite ─────────────────────────────────────────────────────
    # RSI upgraded to 30% (horizon-aligned blend is more accurate).
    # ATR reduced to 10% (regime context, not directional signal).
    weights = {"RSI": 0.30, "MACD": 0.25, "SMA_Trend": 0.20, "Bollinger": 0.15, "ATR": 0.10}
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
