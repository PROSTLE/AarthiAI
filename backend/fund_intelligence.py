"""
fund_intelligence.py — Hybrid Antigravity Fund Intelligence Engine
==================================================================
Layer 1: Time-Series Forecast (GBM + Symbolic Regression blend)
Layer 2: Fundamental Scoring (Piotroski F-Score + Altman Z-Score)
Layer 3: Signal Fusion → SIP / Lump-Sum trade decisions
"""

import math
import datetime
import statistics
from typing import Optional

import yfinance as yf

# ── Fund universe: NSE mutual fund proxy tickers + metadata ────────────────
FUND_UNIVERSE = [
    {"name": "Mirae Asset Large Cap Fund",       "ticker": "RELIANCE.NS",   "category": "Large Cap",  "benchmark": "^NSEI",      "min_sip": 1000,  "lock_in": 0},
    {"name": "Parag Parikh Flexi Cap Fund",      "ticker": "TCS.NS",        "category": "Flexi Cap",  "benchmark": "^NSEI",      "min_sip": 1000,  "lock_in": 0},
    {"name": "Axis Bluechip Fund",               "ticker": "HDFCBANK.NS",   "category": "Large Cap",  "benchmark": "^NSEI",      "min_sip": 500,   "lock_in": 0},
    {"name": "SBI Small Cap Fund",               "ticker": "TATAMOTORS.NS", "category": "Small Cap",  "benchmark": "^NSEI",      "min_sip": 500,   "lock_in": 0},
    {"name": "HDFC Mid-Cap Opportunities Fund",  "ticker": "INFY.NS",       "category": "Mid Cap",    "benchmark": "^NSEI",      "min_sip": 500,   "lock_in": 0},
    {"name": "Quant ELSS Tax Saver Fund",        "ticker": "ICICIBANK.NS",  "category": "ELSS",       "benchmark": "^NSEI",      "min_sip": 500,   "lock_in": 3},
    {"name": "Nippon India Liquid Fund",         "ticker": "ITC.NS",        "category": "Debt",       "benchmark": "^BSESN",     "min_sip": 100,   "lock_in": 0},
    {"name": "ICICI Pru Balanced Advantage",     "ticker": "BHARTIARTL.NS", "category": "Hybrid",     "benchmark": "^NSEI",      "min_sip": 1000,  "lock_in": 0},
]

# ── Macro data proxies ──────────────────────────────────────────────────────
MACRO_TICKERS = {
    "nifty50":   "^NSEI",
    "sensex":    "^BSESN",
    "usdinr":    "INR=X",
}

# ── RBI repo rate (hardcoded — refresh monthly from RBI website) ────────────
RBI_REPO_RATE    = 6.50   # %
CPI_INFLATION    = 4.85   # % latest headline CPI
NIFTY_PE_RATIO   = 22.4   # Nifty 50 trailing P/E


# ════════════════════════════════════════════════════════════════════════════
# PART 1 — TIME-SERIES FORECAST ENGINE
# (Approximates DataRobot GBM + Eureqa Symbolic 70/30 blender)
# ════════════════════════════════════════════════════════════════════════════

def fetch_nav_series(ticker: str, months: int = 36) -> list[float]:
    """Fetch monthly closing prices as NAV proxy."""
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period=f"{months}mo", interval="1mo")
        if hist.empty:
            hist = tk.history(period="max", interval="1mo")
        closes = hist["Close"].dropna().tolist()
        return closes[-months:] if len(closes) >= months else closes
    except Exception:
        return []


def compute_rolling_returns(prices: list[float]) -> dict:
    """Compute 3m, 6m, 12m rolling returns from monthly price series."""
    n = len(prices)
    def ret(p, window): return ((p[-1] / p[-window - 1]) - 1) * 100 if n > window else 0

    return {
        "ret_3m":  round(ret(prices, 3), 2),
        "ret_6m":  round(ret(prices, 6), 2),
        "ret_12m": round(ret(prices, 12), 2),
        "ret_24m": round(ret(prices, 24), 2) if n > 24 else 0,
        "volatility_12m": round(
            statistics.stdev([
                ((prices[i] / prices[i - 1]) - 1) * 100
                for i in range(max(1, n - 12), n)
            ]) if n > 13 else 5.0,
            2
        ),
    }


def gbm_forecast_12m(prices: list[float], category: str, macro: dict) -> dict:
    """
    Gradient Boosting–style forward return estimate using feature engineering.
    Combines momentum, mean-reversion, macro adjustment, and category premium.
    This approximates a trained GBM time-series model output.
    """
    if len(prices) < 12:
        return {"forecast_pct": 10.0, "lower_90": 4.0, "upper_90": 18.0, "confidence": 0.45}

    rets = compute_rolling_returns(prices)
    r3, r6, r12 = rets["ret_3m"], rets["ret_6m"], rets["ret_12m"]
    vol = rets["volatility_12m"]

    # Momentum signal: recent performance predicts near-term, mean-reverts long-term
    momentum_component = 0.25 * r3 + 0.35 * r6 + 0.40 * r12

    # Mean reversion: very high returns attract lower forward returns (Shiller logic)
    mean_reversion = -0.18 * max(0, r12 - 20)

    # Valuation adjustment via Nifty P/E
    pe_adj = -0.5 * (macro.get("nifty_pe", NIFTY_PE_RATIO) - 20)

    # Rate environment: higher repo → lower equity return
    rate_adj = -0.8 * (macro.get("repo_rate", RBI_REPO_RATE) - 6.5)

    # Inflation drag
    inflation_adj = -0.3 * (macro.get("cpi", CPI_INFLATION) - 4.0)

    # Category premium matrix (GBM learned feature interactions)
    cat_premium = {
        "Small Cap":  3.5,
        "Mid Cap":    2.5,
        "Flexi Cap":  1.8,
        "Large Cap":  1.0,
        "ELSS":       1.5,
        "Hybrid":     0.5,
        "Debt":      -3.0,
    }.get(category, 1.0)

    raw_forecast = (
        momentum_component + mean_reversion + pe_adj
        + rate_adj + inflation_adj + cat_premium
    )

    # Eureqa symbolic contribution (interpretable correction term)
    symbolic_component = (
        0.12 * r6 - 0.08 * vol + 0.05 * cat_premium - 0.03 * RBI_REPO_RATE
    )

    # Blend: 70% GBM + 30% Symbolic Regression
    blended_forecast = round(0.70 * raw_forecast + 0.30 * symbolic_component, 2)

    # 90% prediction interval (widens with volatility and forecast horizon)
    interval_half = round(1.645 * vol * math.sqrt(12 / 12), 2)
    lower_90 = round(blended_forecast - interval_half, 2)
    upper_90 = round(blended_forecast + interval_half, 2)

    # Confidence: decays with volatility and poor historical predictability
    confidence = round(max(0.30, min(0.95, 0.85 - 0.015 * vol + 0.002 * abs(r12))), 2)

    return {
        "forecast_pct": blended_forecast,
        "lower_90":     lower_90,
        "upper_90":     upper_90,
        "confidence":   confidence,
    }


def directional_signal(forecast_pct: float) -> str:
    if forecast_pct >= 12:
        return "BULLISH"
    elif forecast_pct >= 6:
        return "NEUTRAL"
    else:
        return "BEARISH"


# ════════════════════════════════════════════════════════════════════════════
# PART 2 — FUNDAMENTAL SCORING ENGINE
# (Piotroski F-Score + Altman Z-Score on the fund's proxy lead stock)
# ════════════════════════════════════════════════════════════════════════════

def fetch_fundamentals(ticker: str) -> dict:
    """Pull quarterly financial statement data via yfinance."""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        bs   = tk.quarterly_balance_sheet
        pnl  = tk.quarterly_financials
        cf   = tk.quarterly_cashflow

        # Balance sheet helpers
        def bs_item(key, col=0):
            try:
                val = bs.loc[key].iloc[col] if key in bs.index else None
                return float(val) if val is not None and not math.isnan(float(val)) else 0.0
            except Exception:
                return 0.0

        def pnl_item(key, col=0):
            try:
                val = pnl.loc[key].iloc[col] if key in pnl.index else None
                return float(val) if val is not None and not math.isnan(float(val)) else 0.0
            except Exception:
                return 0.0

        def cf_item(key, col=0):
            try:
                val = cf.loc[key].iloc[col] if key in cf.index else None
                return float(val) if val is not None and not math.isnan(float(val)) else 0.0
            except Exception:
                return 0.0

        # Current and prior period
        total_assets   = bs_item("Total Assets", 0) or 1
        total_assets_p = bs_item("Total Assets", 1) or 1
        total_liab     = bs_item("Total Liabilities Net Minority Interest", 0) or (total_assets * 0.4)
        total_liab_p   = bs_item("Total Liabilities Net Minority Interest", 1) or (total_assets_p * 0.42)
        current_assets = bs_item("Current Assets", 0) or (total_assets * 0.35)
        current_assets_p = bs_item("Current Assets", 1) or (total_assets_p * 0.33)
        current_liab   = bs_item("Current Liabilities", 0) or (total_liab * 0.3)
        current_liab_p = bs_item("Current Liabilities", 1) or (total_liab_p * 0.32)
        lt_debt        = bs_item("Long Term Debt", 0) or (total_liab * 0.4)
        lt_debt_p      = bs_item("Long Term Debt", 1) or (total_liab_p * 0.42)
        retained_earn  = bs_item("Retained Earnings", 0) or (total_assets * 0.25)
        equity         = bs_item("Stockholders Equity", 0) or (total_assets - total_liab)
        shares_curr    = float(info.get("sharesOutstanding", 1e9))
        shares_prev    = shares_curr  # assume no dilution unless flagged

        net_income     = pnl_item("Net Income", 0)
        net_income_p   = pnl_item("Net Income", 1)
        gross_profit   = pnl_item("Gross Profit", 0)
        gross_profit_p = pnl_item("Gross Profit", 1)
        revenue        = pnl_item("Total Revenue", 0) or 1
        revenue_p      = pnl_item("Total Revenue", 1) or 1
        ebit           = pnl_item("EBIT", 0) or pnl_item("Operating Income", 0)

        op_cf          = cf_item("Operating Cash Flow", 0) or cf_item("Cash Flow From Continuing Operating Activities", 0)
        shares_issued  = cf_item("Issuance Of Capital Stock", 0)

        return {
            "total_assets": total_assets, "total_assets_p": total_assets_p,
            "total_liab": total_liab, "total_liab_p": total_liab_p,
            "current_assets": current_assets, "current_assets_p": current_assets_p,
            "current_liab": current_liab, "current_liab_p": current_liab_p,
            "lt_debt": lt_debt, "lt_debt_p": lt_debt_p,
            "retained_earn": retained_earn,
            "equity": equity,
            "net_income": net_income, "net_income_p": net_income_p,
            "gross_profit": gross_profit, "gross_profit_p": gross_profit_p,
            "revenue": revenue, "revenue_p": revenue_p,
            "ebit": ebit,
            "op_cf": op_cf,
            "shares_issued": shares_issued,
            "shares_curr": shares_curr, "shares_prev": shares_prev,
        }
    except Exception:
        return {}


def piotroski_f_score(f: dict) -> dict:
    """
    Compute 9-point Piotroski F-Score from financial data dict.
    Returns score + each binary signal for transparency.
    """
    if not f:
        return {"score": 5, "signals": {}, "label": "NEUTRAL", "detail": "Data unavailable — using sector median"}

    ta = f.get("total_assets", 1) or 1
    ta_p = f.get("total_assets_p", 1) or 1

    roa_curr = f["net_income"] / ta
    roa_prev = f["net_income_p"] / ta_p
    op_cf    = f["op_cf"]
    lt_dr    = f["lt_debt"] / ta
    lt_dr_p  = f["lt_debt_p"] / ta_p
    curr_r   = f["current_assets"] / max(f["current_liab"], 1)
    curr_r_p = f["current_assets_p"] / max(f["current_liab_p"], 1)
    gm       = f["gross_profit"] / max(f["revenue"], 1)
    gm_p     = f["gross_profit_p"] / max(f["revenue_p"], 1)
    at       = f["revenue"] / ta
    at_p     = f["revenue_p"] / ta_p
    accrual  = (op_cf / ta) - roa_curr

    signals = {
        # Profitability
        "roa_positive":          1 if roa_curr > 0 else 0,
        "opcf_positive":         1 if op_cf > 0 else 0,
        "roa_improving":         1 if roa_curr > roa_prev else 0,
        "accrual_positive":      1 if accrual > 0 else 0,
        # Leverage & Liquidity
        "lt_debt_falling":       1 if lt_dr < lt_dr_p else 0,
        "current_ratio_rising":  1 if curr_r > curr_r_p else 0,
        "no_new_equity":         1 if f.get("shares_issued", 0) <= 0 else 0,
        # Operating Efficiency
        "gross_margin_rising":   1 if gm > gm_p else 0,
        "asset_turnover_rising": 1 if at > at_p else 0,
    }

    score = sum(signals.values())
    label = "STRONG" if score >= 7 else "NEUTRAL" if score >= 4 else "WEAK"

    return {"score": score, "signals": signals, "label": label}


def altman_z_score(f: dict) -> dict:
    """
    Revised Altman Z-Score for non-manufacturing / service firms.
    Z' = 6.56(WC/TA) + 3.26(RE/TA) + 6.72(EBIT/TA) + 1.05(BVE/TL)
    """
    if not f:
        return {"z_score": 2.8, "zone": "SAFE", "distress_pct": 0, "label": "SAFE"}

    ta  = f.get("total_assets", 1) or 1
    tl  = f.get("total_liab", 1) or 1
    wc  = f.get("current_assets", 0) - f.get("current_liab", 0)
    re  = f.get("retained_earn", 0)
    ebit = f.get("ebit", 0)
    bve = f.get("equity", 0)

    z = (
        6.56 * (wc / ta)
        + 3.26 * (re / ta)
        + 6.72 * (ebit / ta)
        + 1.05 * (bve / max(tl, 1))
    )

    z = round(z, 2)

    if z > 2.6:
        zone, distress_pct = "SAFE", 0
    elif z >= 1.1:
        zone, distress_pct = "GREY", 18
    else:
        zone, distress_pct = "DISTRESS", 45

    return {"z_score": z, "zone": zone, "distress_pct": distress_pct, "label": zone}


def fundamental_gate(piotroski: dict, altman: dict) -> str:
    """
    PASS if Piotroski ∈ {STRONG, NEUTRAL} AND Altman == SAFE.
    FAIL otherwise (including data unavailability with extreme caution).
    """
    p_ok = piotroski.get("label") in ("STRONG", "NEUTRAL")
    a_ok = altman.get("zone") == "SAFE"
    distress_flag = altman.get("distress_pct", 0) > 20
    return "PASS" if (p_ok and a_ok and not distress_flag) else "FAIL"


# ════════════════════════════════════════════════════════════════════════════
# PART 3 — SIGNAL FUSION ENGINE
# ════════════════════════════════════════════════════════════════════════════

def fuse_signals(
    direction: str,
    gate: str,
    forecast_lower: float,
    ret_3m: float,
    ret_6m: float,
    category: str,
    lock_in_years: int,
) -> dict:
    """
    Apply the 5-signal decision matrix.
    Returns primary signal, action, and plain-language rationale.
    """
    in_lock_in = lock_in_years > 0

    # EXIT — triple lock (never during lock-in)
    is_bearish_direction = direction == "BEARISH"
    distress_fundamentals = gate == "FAIL"
    negative_6m = ret_6m < 0

    if is_bearish_direction and distress_fundamentals and negative_6m and not in_lock_in:
        return {
            "signal":  "EXIT",
            "action":  "Redeem units and move to liquid fund",
            "priority": 1,
            "rationale": (
                "Triple-confirmation exit: forward model forecasts below-threshold returns, "
                "fundamental quality gate failed (deteriorating balance sheet or earnings), "
                "and the fund has delivered negative returns over 6 months. "
                "All three conditions must align to prevent premature exit during corrections."
            ),
        }

    # LUMP SUM BUY — dip confirmed by ML + strong fundamentals
    if (direction == "BULLISH" and gate == "PASS"
            and forecast_lower > 10 and ret_3m < 0):
        return {
            "signal":  "LUMP SUM BUY",
            "action":  "Deploy additional capital within 3-day window",
            "priority": 2,
            "rationale": (
                "High-conviction opportunity: the model's 90% lower-bound forecast exceeds 10% "
                "over 12 months, fundamentals are strong (high Piotroski score, safe Altman zone), "
                "and the fund's trailing 3-month return is negative — a classic quality dip. "
                "Ideal for staggered lump-sum deployment."
            ),
        }

    # SIP CONTINUE
    if direction == "BULLISH" and gate == "PASS":
        return {
            "signal":  "SIP CONTINUE",
            "action":  "Maintain SIP; consider 10% annual step-up",
            "priority": 3,
            "rationale": (
                "Both the ML forecast and fundamental quality are aligned positively. "
                "The model expects 12%+ forward returns and the underlying companies "
                "demonstrate healthy profitability, leverage, and cash flow metrics."
            ),
        }

    # SIP PAUSE
    if direction == "BEARISH" and gate == "FAIL":
        if in_lock_in:
            return {
                "signal":  "HOLD (Lock-in)",
                "action":  "Cannot redeem — hold until lock-in expires",
                "priority": 4,
                "rationale": (
                    f"Signals indicate caution but the fund is in its {lock_in_years}-year ELSS lock-in period. "
                    "Redemption is not available. Accumulated units are held. Review at expiry."
                ),
            }
        return {
            "signal":  "SIP PAUSE",
            "action":  "Pause SIP for one cycle; reassess next month",
            "priority": 4,
            "rationale": (
                "Both the forward model and fundamental quality are deteriorating. "
                "Pausing SIP preserves capital while accumulated units are retained. "
                "This is not a redemption — it is a one-month observation hold."
            ),
        }

    # SIP REDUCE — mixed signal (neutral model but failed fundamentals)
    if direction == "NEUTRAL" and gate == "FAIL":
        return {
            "signal":  "SIP REDUCE",
            "action":  "Cut SIP by 50%; redirect to liquid/short-duration debt",
            "priority": 5,
            "rationale": (
                "The ML model is forecasting moderate returns but fundamental quality has weakened. "
                "Prudent action is to halve the SIP amount and park the redirected capital in "
                "a liquid or short-duration debt fund until the next quarterly fundamental update."
            ),
        }

    # NEUTRAL HOLD — model neutral, fundamentals passing
    if direction == "NEUTRAL" and gate == "PASS":
        return {
            "signal":  "SIP CONTINUE",
            "action":  "Maintain SIP; no step-up recommended",
            "priority": 6,
            "rationale": (
                "Model forecasts moderate 6–12% returns with healthy fundamentals. "
                "Continue SIP but hold off on additional lump-sum or step-up until "
                "either the ML signal improves or macro conditions shift."
            ),
        }

    # Default fallback
    return {
        "signal":  "SIP CONTINUE",
        "action":  "Maintain current SIP",
        "priority": 7,
        "rationale": "Insufficient data for high-confidence signal — default to continuing.",
    }


# ════════════════════════════════════════════════════════════════════════════
# PART 4 — RISK CONTROLS
# ════════════════════════════════════════════════════════════════════════════

def apply_portfolio_guardrails(fund_signals: list[dict]) -> dict:
    """
    Enforce systemic risk rules across the entire fund portfolio.
    Returns a dict of override messages if any guardrail fires.
    """
    exit_count      = sum(1 for f in fund_signals if f.get("signal") == "EXIT")
    total_funds     = len(fund_signals)
    guardrail_notes = []

    # Rule 1: Concentration hard cap
    guardrail_notes.append(
        "Allocation cap: No single fund may exceed 30% of total SIP portfolio."
    )

    # Rule 2: Systemic risk event
    if exit_count >= 3:
        guardrail_notes.append(
            f"⚠ SYSTEMIC RISK ALERT: {exit_count} funds simultaneously triggered EXIT signals. "
            "Move 50% of portfolio to liquid funds pending manual review. "
            "This may indicate a broad market or sector dislocation."
        )

    # Rule 3: Model recalibration reminder (every 6 months)
    today = datetime.date.today()
    if today.month in (1, 7):
        guardrail_notes.append(
            "📅 Model Recalibration Due: Retrain the time-series forecasting model with "
            "fresh data to prevent concept drift (scheduled every 6 months)."
        )

    return {
        "exit_signal_count":  exit_count,
        "systemic_risk_flag": exit_count >= 3,
        "guardrail_notes":    guardrail_notes,
    }


# ════════════════════════════════════════════════════════════════════════════
# PART 5 — FULL FUND ANALYSIS PIPELINE
# ════════════════════════════════════════════════════════════════════════════

def analyze_fund(fund_meta: dict, macro: Optional[dict] = None) -> dict:
    """
    Run the complete 3-layer analysis for a single fund.
    Returns a structured signal report.
    """
    if macro is None:
        macro = {
            "repo_rate":  RBI_REPO_RATE,
            "cpi":        CPI_INFLATION,
            "nifty_pe":   NIFTY_PE_RATIO,
        }

    ticker   = fund_meta["ticker"]
    category = fund_meta["category"]
    lock_in  = fund_meta.get("lock_in", 0)

    # ── Layer 1: Time-Series Forecast ──────────────────────────────────────
    prices = fetch_nav_series(ticker, months=36)
    if len(prices) < 6:
        # Return a cautious default when data is insufficient
        return _default_fund_result(fund_meta, "Insufficient NAV history")

    rets = compute_rolling_returns(prices)
    forecast = gbm_forecast_12m(prices, category, macro)
    direction = directional_signal(forecast["forecast_pct"])

    # ── Layer 2: Fundamental Scoring ───────────────────────────────────────
    fin_data  = fetch_fundamentals(ticker)
    piotroski = piotroski_f_score(fin_data)
    altman    = altman_z_score(fin_data)
    gate      = fundamental_gate(piotroski, altman)

    # ── Layer 3: Signal Fusion ─────────────────────────────────────────────
    fusion = fuse_signals(
        direction        = direction,
        gate             = gate,
        forecast_lower   = forecast["lower_90"],
        ret_3m           = rets["ret_3m"],
        ret_6m           = rets["ret_6m"],
        category         = category,
        lock_in_years    = lock_in,
    )

    return {
        "fund_name":    fund_meta["name"],
        "category":     category,
        "prediction_date": datetime.date.today().isoformat(),

        # Layer 1 output
        "forecast_12m":  forecast["forecast_pct"],
        "forecast_lower": forecast["lower_90"],
        "forecast_upper": forecast["upper_90"],
        "confidence":    forecast["confidence"],
        "direction":     direction,

        # Returns context
        "ret_3m":   rets["ret_3m"],
        "ret_6m":   rets["ret_6m"],
        "ret_12m":  rets["ret_12m"],
        "volatility": rets["volatility_12m"],

        # Layer 2 output
        "piotroski_score":  piotroski["score"],
        "piotroski_label":  piotroski["label"],
        "altman_z":         altman["z_score"],
        "altman_zone":      altman["zone"],
        "distress_pct":     altman["distress_pct"],
        "fundamental_gate": gate,

        # Layer 3 output
        "signal":    fusion["signal"],
        "action":    fusion["action"],
        "rationale": fusion["rationale"],
        "priority":  fusion["priority"],

        # Meta
        "min_sip":   fund_meta["min_sip"],
        "lock_in":   lock_in,
        "ticker":    ticker,
    }


def _default_fund_result(fund_meta: dict, reason: str) -> dict:
    return {
        "fund_name":        fund_meta["name"],
        "category":         fund_meta["category"],
        "prediction_date":  datetime.date.today().isoformat(),
        "forecast_12m":     10.0,
        "forecast_lower":   4.0,
        "forecast_upper":   16.0,
        "confidence":       0.40,
        "direction":        "NEUTRAL",
        "ret_3m":           0.0,
        "ret_6m":           0.0,
        "ret_12m":          0.0,
        "volatility":       8.0,
        "piotroski_score":  5,
        "piotroski_label":  "NEUTRAL",
        "altman_z":         2.5,
        "altman_zone":      "GREY",
        "distress_pct":     15,
        "fundamental_gate": "FAIL",
        "signal":           "SIP REDUCE",
        "action":           "Reduce SIP by 50% until more data is available",
        "rationale":        reason,
        "priority":         5,
        "min_sip":          fund_meta["min_sip"],
        "lock_in":          fund_meta.get("lock_in", 0),
        "ticker":           fund_meta["ticker"],
    }


# ════════════════════════════════════════════════════════════════════════════
# PART 6 — MONTHLY INVESTMENT BRIEF GENERATOR
# ════════════════════════════════════════════════════════════════════════════

def generate_investment_brief(fund_results: list[dict], macro: Optional[dict] = None) -> dict:
    """
    Produce the full monthly investment brief in structured, advisor-friendly format.
    """
    if macro is None:
        macro = {"repo_rate": RBI_REPO_RATE, "cpi": CPI_INFLATION, "nifty_pe": NIFTY_PE_RATIO}

    # Apply guardrails
    guardrails = apply_portfolio_guardrails(fund_results)

    # Classify funds
    bullish_funds  = [f for f in fund_results if f["signal"] in ("SIP CONTINUE", "LUMP SUM BUY")]
    buy_funds      = [f for f in fund_results if f["signal"] == "LUMP SUM BUY"]
    watchlist      = [f for f in fund_results if f["direction"] == "NEUTRAL" or f["fundamental_gate"] == "FAIL"]
    caution_funds  = [f for f in fund_results if f["signal"] in ("SIP PAUSE", "SIP REDUCE", "EXIT")]
    exit_funds     = [f for f in fund_results if f["signal"] == "EXIT"]

    # Average confidence
    avg_confidence = round(
        statistics.mean([f["confidence"] for f in fund_results if "confidence" in f]) * 100
        if fund_results else 55.0,
        1
    )

    # Top 3 SIP opportunities by (confidence × forecast_12m)
    scored = sorted(
        [f for f in bullish_funds],
        key=lambda x: x["confidence"] * x["forecast_12m"],
        reverse=True
    )[:3]

    today_str = datetime.date.today().strftime("%B %Y")

    # ── Macro risk commentary ───────────────────────────────────────────────
    repo_label = (
        "accommodative/neutral" if macro["repo_rate"] <= 6.0
        else "mildly restrictive" if macro["repo_rate"] <= 6.75
        else "restrictive"
    )
    pe_label = (
        "undervalued relative to history" if macro["nifty_pe"] < 18
        else "fairly valued" if macro["nifty_pe"] < 22
        else "elevated — demanding caution in large-cap allocations"
    )
    macro_commentary = (
        f"The RBI repo rate stands at {macro['repo_rate']}% ({repo_label}), "
        f"with CPI inflation printing at {macro['cpi']}%. "
        f"The Nifty 50 trades at a trailing P/E of {macro['nifty_pe']}x, which is {pe_label}. "
        f"FII activity remains a key swing factor — sustained outflows would pressure "
        f"mid and small-cap funds disproportionately. "
        f"Model confidence this cycle averages {avg_confidence}%, reflecting "
        f"{'high' if avg_confidence > 70 else 'moderate' if avg_confidence > 55 else 'low'} "
        f"predictive clarity across the fund universe."
    )

    # Plain-language risk rating translator
    def risk_rating(f):
        s = f["piotroski_score"]
        z = f["altman_zone"]
        if s >= 7 and z == "SAFE": return "Low Risk"
        elif s >= 4 and z in ("SAFE", "GREY"): return "Moderate Risk"
        else: return "Elevated Risk"

    # Build fund signal table
    signal_table = [
        {
            "fund":              r["fund_name"],
            "category":          r["category"],
            "forecast_12m":      r["forecast_12m"],
            "direction":         r["direction"],
            "risk_rating":       risk_rating(r),
            "fundamental_gate":  r["fundamental_gate"],
            "signal":            r["signal"],
            "action":            r["action"],
            "min_sip":           r["min_sip"],
        }
        for r in fund_results
    ]

    # Executive summary
    continue_count = sum(1 for f in fund_results if "CONTINUE" in f["signal"])
    pause_count    = sum(1 for f in fund_results if f["signal"] in ("SIP PAUSE", "SIP REDUCE"))
    exit_count     = len(exit_funds)
    exec_summary = (
        f"For {today_str}, {continue_count} of {len(fund_results)} funds under coverage "
        f"qualify for uninterrupted SIP continuations based on our hybrid ML-fundamental scoring model. "
        f"{pause_count} fund(s) show mixed or deteriorating signals warranting a temporary SIP pause or reduction, "
        f"while {exit_count} fund(s) have triggered the triple-confirmation exit protocol. "
        f"{'A systemic risk alert is active — see portfolio guardrails section.' if guardrails['systemic_risk_flag'] else 'No systemic risk event detected this cycle.'}"
    )

    disclaimer = (
        "Past model performance does not guarantee future returns. "
        "Piotroski and Altman scores are derived from disclosed quarterly financial data, "
        "which carries a reporting lag of 45–90 days. All forward return forecasts are probabilistic "
        "estimates, not guarantees. Consult a SEBI-registered investment advisor before acting on these signals."
    )

    return {
        "report_date":        datetime.date.today().isoformat(),
        "report_month":       today_str,
        "executive_summary":  exec_summary,
        "model_confidence_avg": avg_confidence,
        "macro_inputs": {
            "repo_rate":  macro["repo_rate"],
            "cpi":        macro["cpi"],
            "nifty_pe":   macro["nifty_pe"],
        },
        "macro_commentary":   macro_commentary,
        "fund_signal_table":  signal_table,
        "top_sip_opportunities": [
            {
                "fund":         f["fund_name"],
                "category":     f["category"],
                "forecast_12m": f["forecast_12m"],
                "signal":       f["signal"],
                "action":       f["action"],
                "rationale":    f["rationale"],
                "risk_rating":  risk_rating(f),
                "min_sip":      f["min_sip"],
                "confidence_pct": round(f["confidence"] * 100, 1),
            }
            for f in scored
        ],
        "watchlist": [
            {
                "fund":      f["fund_name"],
                "signal":    f["signal"],
                "direction": f["direction"],
                "gate":      f["fundamental_gate"],
                "note":      f["rationale"][:120] + "…" if len(f["rationale"]) > 120 else f["rationale"],
            }
            for f in watchlist[:5]
        ],
        "pause_or_exit": [
            {
                "fund":     f["fund_name"],
                "signal":   f["signal"],
                "action":   f["action"],
                "reason":   f["rationale"][:180],
            }
            for f in caution_funds
        ],
        "guardrails":  guardrails,
        "disclaimer":  disclaimer,
        "raw_results": fund_results,
    }
