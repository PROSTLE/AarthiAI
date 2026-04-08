"""
AarthiAI Long-Term Stock Scoring Engine
========================================
5-Pillar composite scoring system for NSE/BSE equities.
Weights:
  P1 - Fundamental Quality    40%
  P2 - Technical Entry Signal 20%
  P3 - News & Sentiment       15%
  P4 - Ownership & Governance 15%
  P5 - Growth Pipeline        10%
  (Sector overrides applied automatically)

Verdict thresholds:
  0–4   → Avoid
  4–6   → Watchlist
  6–8   → Buy
  8–10  → High Conviction
"""

from __future__ import annotations
import time
import math

# ── Cache: 2-hour TTL per ticker ──────────────────────────────────────────────
_LT_CACHE: dict = {}
_LT_TTL = 2 * 60 * 60   # 2 hours


def _get_cached(ticker: str) -> dict | None:
    e = _LT_CACHE.get(ticker)
    if e and (time.time() - e["ts"]) < _LT_TTL:
        return e["result"]
    return None


def _set_cached(ticker: str, result: dict):
    _LT_CACHE[ticker] = {"result": result, "ts": time.time()}
    if len(_LT_CACHE) > 50:
        oldest = min(_LT_CACHE, key=lambda k: _LT_CACHE[k]["ts"])
        del _LT_CACHE[oldest]


# ── Sector detection ─────────────────────────────────────────────────────────

def _detect_sector(info: dict) -> str:
    sector = (info.get("sector") or "").lower()
    industry = (info.get("industry") or "").lower()
    name = (info.get("longName") or info.get("shortName") or "").lower()
    if any(k in sector for k in ["financial", "bank", "insurance", "nbfc"]):
        return "banking"
    if "pharma" in sector or "pharma" in industry or "drug" in industry:
        return "pharma"
    if "technology" in sector or "software" in industry or "it " in industry:
        return "it"
    if "auto" in sector or "vehicle" in industry or "automobile" in industry:
        return "auto"
    if "consumer" in sector and "staple" in sector:
        return "fmcg"
    if any(k in sector for k in ["industrial", "infrastructure", "construction", "capital goods"]):
        return "infra"
    if "defence" in sector or "defence" in industry or "defense" in industry:
        return "defence"
    return "general"


def _sector_weights(sector: str) -> dict:
    """Return (fundamental, technical, sentiment, ownership, growth) weights that sum to 1.0"""
    if sector == "fmcg":
        return dict(fundamental=0.50, technical=0.15, sentiment=0.15, ownership=0.12, growth=0.08)
    if sector == "pharma":
        return dict(fundamental=0.35, technical=0.15, sentiment=0.20, ownership=0.15, growth=0.15)
    if sector in ("infra", "defence"):
        return dict(fundamental=0.35, technical=0.15, sentiment=0.10, ownership=0.15, growth=0.25)
    if sector == "banking":
        return dict(fundamental=0.40, technical=0.20, sentiment=0.10, ownership=0.15, growth=0.15)
    if sector == "auto":
        return dict(fundamental=0.35, technical=0.20, sentiment=0.12, ownership=0.15, growth=0.18)
    # Default / IT / general
    return dict(fundamental=0.40, technical=0.20, sentiment=0.15, ownership=0.15, growth=0.10)


# ── Helper: safe numeric extraction ──────────────────────────────────────────

def _f(d: dict, key: str, default: float = 0.0) -> float:
    v = d.get(key)
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


# ── PILLAR 1: Fundamental Quality ────────────────────────────────────────────

def _score_fundamentals(info: dict, sector: str) -> tuple[float, list[str]]:
    """Returns (score 0-10, list of signal strings)"""
    signals = []
    score = 5.0   # neutral baseline

    # -- PE vs sector --
    pe = _f(info, "trailingPE") or _f(info, "forwardPE")
    if pe > 0:
        if sector == "banking":
            if pe < 12:   score += 1.0; signals.append("✅ Attractive P/E < 12 (banking norm)")
            elif pe < 18: score += 0.5; signals.append("✓ Fair P/E range for bank")
            elif pe > 30: score -= 1.0; signals.append("⚠ High P/E > 30 for bank")
        else:
            if pe < 15:   score += 1.0; signals.append("✅ Attractive P/E < 15")
            elif pe < 25: score += 0.5; signals.append("✓ Reasonable P/E < 25")
            elif pe > 50: score -= 1.2; signals.append("⚠ Very expensive P/E > 50")
            elif pe > 35: score -= 0.6; signals.append("⚠ High P/E > 35")

    # -- PEG ratio --
    peg = _f(info, "pegRatio")
    if 0 < peg < 1.0:
        score += 0.8; signals.append("✅ PEG < 1 — growth at a discount")
    elif 1.0 <= peg <= 2.0:
        signals.append("✓ PEG 1-2 — fair growth pricing")
    elif peg > 2.0:
        score -= 0.6; signals.append("⚠ PEG > 2 — expensive relative to growth")

    # -- Return on Equity --
    roe = _f(info, "returnOnEquity") * 100
    if roe >= 20:
        score += 1.2; signals.append(f"✅ Strong ROE {roe:.1f}% (>20% target)")
    elif roe >= 15:
        score += 0.6; signals.append(f"✓ Good ROE {roe:.1f}%")
    elif roe >= 8:
        signals.append(f"~ Moderate ROE {roe:.1f}%")
    else:
        score -= 0.8; signals.append(f"⚠ Weak ROE {roe:.1f}%")

    # -- Debt to Equity --
    dte = _f(info, "debtToEquity") / 100   # yfinance gives as %, e.g. 38.0 = 0.38
    if sector == "banking":
        # Use NPA / NIM proxy via Price-to-Book instead
        pb = _f(info, "priceToBook")
        roa = _f(info, "returnOnAssets") * 100
        if pb < 1.5 and roa > 1.0:
            score += 1.0; signals.append(f"✅ Attractive P/B {pb:.2f} + ROA {roa:.1f}%")
        elif roa > 1.5:
            score += 0.8; signals.append(f"✅ Strong ROA {roa:.1f}% for bank")
        elif roa < 0.5:
            score -= 0.8; signals.append(f"⚠ Weak ROA {roa:.1f}%")
    else:
        if dte < 0.3:
            score += 0.8; signals.append(f"✅ Low D/E {dte:.2f} — strong balance sheet")
        elif dte < 0.8:
            signals.append(f"✓ Manageable D/E {dte:.2f}")
        elif dte > 2.0:
            score -= 1.0; signals.append(f"⚠ High D/E {dte:.2f} — leverage risk")
        elif dte > 1.0:
            score -= 0.5; signals.append(f"⚠ Elevated D/E {dte:.2f}")

    # -- Profit Margins --
    margin = _f(info, "profitMargins") * 100
    if margin >= 18:
        score += 0.8; signals.append(f"✅ High profit margin {margin:.1f}%")
    elif margin >= 10:
        score += 0.3; signals.append(f"✓ Decent margin {margin:.1f}%")
    elif margin < 3:
        score -= 0.7; signals.append(f"⚠ Thin margin {margin:.1f}%")

    # -- Revenue Growth --
    rev_growth = _f(info, "revenueGrowth") * 100
    if rev_growth >= 20:
        score += 0.8; signals.append(f"✅ Strong revenue growth {rev_growth:.1f}%")
    elif rev_growth >= 10:
        score += 0.4; signals.append(f"✓ Solid revenue growth {rev_growth:.1f}%")
    elif rev_growth < 0:
        score -= 0.7; signals.append(f"⚠ Revenue declining {rev_growth:.1f}%")

    # -- EPS / Earnings Quality --
    eps = _f(info, "trailingEps")
    forward_eps = _f(info, "forwardEps")
    if eps > 0 and forward_eps > eps:
        growth_fwd = (forward_eps - eps) / eps * 100
        if growth_fwd > 15:
            score += 0.5; signals.append(f"✅ Forward EPS growth {growth_fwd:.1f}%")

    # Cap at 0-10
    return max(0.0, min(10.0, score)), signals


# ── PILLAR 2: Technical Entry Signal ─────────────────────────────────────────

def _score_technical(df_row: dict, info: dict) -> tuple[float, list[str]]:
    signals = []
    score = 5.0

    rsi = _f(df_row, "RSI")
    macd = _f(df_row, "MACD")
    macd_sig = _f(df_row, "MACD_Signal")
    price = _f(df_row, "Close")
    sma20 = _f(df_row, "SMA_20")
    sma50 = _f(df_row, "SMA_50")
    bb_width = _f(df_row, "BB_Width")
    atr = _f(df_row, "ATR")

    # RSI
    if 40 <= rsi <= 60:
        score += 0.5; signals.append(f"✓ RSI neutral zone {rsi:.0f}")
    elif rsi < 35:
        score += 0.8; signals.append(f"✅ RSI oversold {rsi:.0f} — potential entry")
    elif rsi > 75:
        score -= 0.8; signals.append(f"⚠ RSI overbought {rsi:.0f}")
    elif rsi > 65:
        score -= 0.3; signals.append(f"~ RSI elevated {rsi:.0f}")

    # MACD
    if macd > macd_sig:
        score += 0.8; signals.append("✅ MACD bullish crossover")
    else:
        score -= 0.5; signals.append("⚠ MACD below signal line")

    # Price vs MAs (trend confirmation)
    if price > sma20 > sma50:
        score += 0.8; signals.append("✅ Price above 20 & 50 SMA — uptrend")
    elif price > sma20:
        score += 0.3; signals.append("✓ Price above 20 SMA")
    elif price < sma50:
        score -= 0.8; signals.append("⚠ Price below 50 SMA — downtrend")

    # 52-week position
    high_52w = _f(info, "fiftyTwoWeekHigh")
    low_52w = _f(info, "fiftyTwoWeekLow")
    if high_52w > low_52w and price > 0:
        pos = (price - low_52w) / (high_52w - low_52w)
        if pos >= 0.85:
            score += 0.6; signals.append(f"✅ Near 52W high ({pos*100:.0f}% of range) — momentum")
        elif pos <= 0.20:
            score -= 0.3; signals.append(f"~ Near 52W low ({pos*100:.0f}% of range) — watch support")

    # BB width (volatility — squeeze = potential breakout)
    if bb_width < 0.05:
        score += 0.4; signals.append("✅ Bollinger squeeze — breakout imminent")

    return max(0.0, min(10.0, score)), signals


# ── PILLAR 3: News & Sentiment ────────────────────────────────────────────────

def _score_sentiment(sentiment_result: dict, sector: str) -> tuple[float, list[str]]:
    signals = []
    score = 5.0

    overall = _f(sentiment_result, "overall_signed_score")
    if overall == 0.0:
        overall = _f(sentiment_result, "overall_score")
    label = sentiment_result.get("overall_sentiment", "neutral")
    article_count = len(sentiment_result.get("articles", []))

    # Base sentiment score — weight higher for pharma
    multiplier = 1.5 if sector == "pharma" else 1.0
    score += overall * 3.0 * multiplier

    if label == "bullish":
        signals.append(f"✅ Bullish news sentiment ({article_count} sources)")
    elif label == "bearish":
        signals.append(f"⚠ Bearish news sentiment ({article_count} sources)")
    else:
        signals.append(f"~ Neutral news flow ({article_count} sources)")

    # Check for red-flag keywords in reasoning
    articles = sentiment_result.get("articles", [])
    for a in articles[:5]:
        headline = (a.get("headline") or a.get("title") or "").lower()
        if any(k in headline for k in ["sebi", "fraud", "scam", "penalty", "usfda", "import alert", "fir"]):
            score -= 1.5
            signals.append(f"🚨 Red-flag headline: '{headline[:60]}...'")
            break
        if any(k in headline for k in ["order win", "deal win", "expansion", "acquisition", "strong quarter"]):
            score += 0.5
            signals.append(f"✅ Positive catalyst: '{headline[:60]}'")
            break

    return max(0.0, min(10.0, score)), signals


# ── PILLAR 4: Ownership & Governance ─────────────────────────────────────────

def _score_ownership(info: dict) -> tuple[float, list[str]]:
    signals = []
    score = 5.0

    # Institutional ownership
    inst_pct = _f(info, "institutionPercentHeld") * 100
    if inst_pct >= 50:
        score += 1.0; signals.append(f"✅ Strong institutional holding {inst_pct:.1f}%")
    elif inst_pct >= 25:
        score += 0.5; signals.append(f"✓ Good institutional holding {inst_pct:.1f}%")
    elif inst_pct < 10:
        score -= 0.5; signals.append(f"~ Low institutional holding {inst_pct:.1f}%")

    # Insider/promoter holdings (proxy)
    insider_pct = _f(info, "insiderPercentHeld") * 100
    if insider_pct >= 50:
        score += 0.8; signals.append(f"✅ High promoter holding {insider_pct:.1f}% — strong alignment")
    elif insider_pct >= 25:
        score += 0.3; signals.append(f"✓ Decent insider holding {insider_pct:.1f}%")
    elif insider_pct < 10:
        score -= 0.3; signals.append(f"~ Low insider holding {insider_pct:.1f}%")

    # Shares outstanding / float (low float = volatile)
    float_shares = _f(info, "floatShares")
    shares_out = _f(info, "sharesOutstanding")
    if shares_out > 0 and float_shares > 0:
        float_ratio = float_shares / shares_out
        if float_ratio < 0.3:
            score -= 0.4; signals.append("⚠ Low free float < 30% — liquidity risk")
        elif float_ratio > 0.6:
            score += 0.3; signals.append("✅ Good free float > 60%")

    # Short interest (where available)
    short_ratio = _f(info, "shortRatio")
    if short_ratio > 5:
        score -= 0.6; signals.append(f"⚠ High short ratio {short_ratio:.1f} — bearish positioning")

    # Shares buyback signal
    if _f(info, "buyBackYield") > 0.01:
        score += 0.4; signals.append("✅ Active share buyback programme")

    return max(0.0, min(10.0, score)), signals


# ── PILLAR 5: Growth Pipeline ─────────────────────────────────────────────────

def _score_growth(info: dict, sector: str) -> tuple[float, list[str]]:
    signals = []
    score = 5.0

    # Earnings growth (forward guidance)
    eps_growth = _f(info, "earningsGrowth") * 100
    if eps_growth >= 25:
        score += 1.2; signals.append(f"✅ Earnings growth outlook {eps_growth:.1f}%")
    elif eps_growth >= 12:
        score += 0.6; signals.append(f"✓ Moderate earnings growth {eps_growth:.1f}%")
    elif eps_growth < 0:
        score -= 1.0; signals.append(f"⚠ Earnings expected to decline {eps_growth:.1f}%")

    # Revenue growth (forward)
    rev_growth = _f(info, "revenueGrowth") * 100
    if rev_growth >= 20:
        score += 0.8; signals.append(f"✅ Strong revenue growth {rev_growth:.1f}%")
    elif rev_growth >= 10:
        score += 0.4; signals.append(f"✓ Solid revenue growth {rev_growth:.1f}%")
    elif rev_growth < 0:
        score -= 0.6; signals.append(f"⚠ Revenue declining {rev_growth:.1f}%")

    # Sector-specific overlays
    if sector == "auto":
        signals.append("📋 Monitor VAHAN monthly data & EV transition pipeline")
    elif sector == "it":
        signals.append("📋 Track deal TCV wins, attrition rate & EBIT margin trend")
    elif sector == "pharma":
        signals.append("📋 Monitor USFDA clearances and pipeline R&D pipeline")
    elif sector in ("infra", "defence"):
        signals.append("📋 Track order book, government capex allocation & execution rate")

    # Market cap (size proxy for growth ceiling)
    # NOTE: yfinance marketCap is in USD. ₹500 Cr ≈ USD 60M (6e7)
    mcap = _f(info, "marketCap")
    if mcap < 6e7:   # < ₹500 Cr
        score -= 1.5; signals.append("⚠ Small cap below ₹500 Cr — liquidity risk, higher volatility")
    elif mcap < 2.5e8:  # < ₹2000 Cr
        signals.append("~ Small-mid cap — higher growth potential, higher volatility")
    elif mcap > 6e9:  # > ₹50,000 Cr
        signals.append("✓ Large cap — steady compounder, lower upside ceiling")

    return max(0.0, min(10.0, score)), signals


# ── HARD REJECT FILTERS ───────────────────────────────────────────────────────

def _check_hard_rejects(info: dict, sector: str) -> list[str]:
    rejects = []
    # yfinance marketCap is in USD. ₹100 Cr ≈ USD 12M (1.2e7)
    mcap = _f(info, "marketCap")
    if mcap > 0 and mcap < 1.2e7:   # genuinely tiny: < ₹100 Cr
        rejects.append("Market cap below ₹100 Cr — liquidity risk")

    dte = _f(info, "debtToEquity") / 100
    if sector not in ("banking",) and dte > 5.0:
        rejects.append(f"Extreme D/E ratio {dte:.1f} — potential distress")

    return rejects


# ── VERDICT ───────────────────────────────────────────────────────────────────

def _verdict(score: float) -> tuple[str, str]:
    if score >= 8.5:
        return "HIGH CONVICTION BUY ✅", "Increase position sizing. Strong fundamental and technical alignment."
    elif score >= 7.0:
        return "BUY 📈", "Initiate standard position. Good risk-reward on current fundamentals."
    elif score >= 5.5:
        return "WATCHLIST 👀", "Monitor next quarter. No urgent entry — wait for a cleaner setup."
    else:
        return "AVOID 🚫", "Insufficient conviction. High risk or weak fundamentals. Remove from watchlist."


# ── POSITION SIZING ───────────────────────────────────────────────────────────

def _position_size(score: float, mcap: float) -> str:
    if score >= 8.5:
        return "1.5–2× standard weight (high conviction)"
    elif score >= 7.0:
        return "1× standard weight"
    elif score >= 5.5:
        return "Paper position only — no capital allocation yet"
    else:
        return "Zero — exit any existing position"


# ── MAIN ENTRY POINT ─────────────────────────────────────────────────────────

def analyze_long_term(ticker: str, info: dict, df_latest: dict,
                      sentiment_result: dict) -> dict:
    """
    Run the full 5-pillar long-term scoring engine.
    Returns structured dict ready for API response.
    """
    cached = _get_cached(ticker)
    if cached:
        return cached

    sector = _detect_sector(info)
    weights = _sector_weights(sector)

    # Hard filter check
    hard_rejects = _check_hard_rejects(info, sector)

    # 5 pillars
    p1_raw, p1_signals = _score_fundamentals(info, sector)
    p2_raw, p2_signals = _score_technical(df_latest, info)
    p3_raw, p3_signals = _score_sentiment(sentiment_result, sector)
    p4_raw, p4_signals = _score_ownership(info)
    p5_raw, p5_signals = _score_growth(info, sector)

    # Weighted composite (out of 10)
    composite = (
        p1_raw * weights["fundamental"] +
        p2_raw * weights["technical"] +
        p3_raw * weights["sentiment"] +
        p4_raw * weights["ownership"] +
        p5_raw * weights["growth"]
    )

    # Hard reject → cap at 3.9 only for genuinely tiny/distressed stocks
    if hard_rejects:
        composite = min(composite, 3.9)

    composite = round(max(0.0, min(10.0, composite)), 2)
    p1 = round(p1_raw, 2)
    p2 = round(p2_raw, 2)
    p3 = round(p3_raw, 2)
    p4 = round(p4_raw, 2)
    p5 = round(p5_raw, 2)

    verdict_label, verdict_detail = _verdict(composite)
    mcap = _f(info, "marketCap")
    pos_size = _position_size(composite, mcap)

    # Strongest signal
    pillar_vals = {"Fundamental Quality": p1, "Technical Entry": p2,
                   "Sentiment": p3, "Ownership/Governance": p4, "Growth Pipeline": p5}
    strongest_pillar = max(pillar_vals, key=lambda k: pillar_vals[k])
    weakest_pillar = min(pillar_vals, key=lambda k: pillar_vals[k])

    result = {
        "ticker": ticker,
        "sector": sector,
        "sector_weights": weights,
        "composite_score": composite,
        "verdict": verdict_label,
        "verdict_detail": verdict_detail,
        "position_size": pos_size,
        "hard_rejects": hard_rejects,
        "pillars": {
            "fundamental": {"score": p1, "weight": weights["fundamental"], "signals": p1_signals},
            "technical":   {"score": p2, "weight": weights["technical"],   "signals": p2_signals},
            "sentiment":   {"score": p3, "weight": weights["sentiment"],   "signals": p3_signals},
            "ownership":   {"score": p4, "weight": weights["ownership"],   "signals": p4_signals},
            "growth":      {"score": p5, "weight": weights["growth"],      "signals": p5_signals},
        },
        "key_insight": {
            "strongest": f"{strongest_pillar} ({pillar_vals[strongest_pillar]:.1f}/10)",
            "biggest_risk": f"{weakest_pillar} ({pillar_vals[weakest_pillar]:.1f}/10)",
        },
        "rebalance_cadence": "Quarterly — after NSE/BSE earnings season",
        "exit_triggers": [
            "EPS growth negative for 2 consecutive quarters",
            "Promoter pledge crosses 35%",
            "D/E breaches sector threshold established at entry",
        ],
    }

    _set_cached(ticker, result)
    return result
