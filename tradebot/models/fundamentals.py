"""
models/fundamentals.py
Piotroski F-Score + Altman Z-Score (non-manufacturing form) for NSE stocks.
Uses yfinance for financial statement data.
"""
import logging
import yfinance as yf
import numpy as np
from config import POSITIONAL

log = logging.getLogger(__name__)


# ── Piotroski F-Score (9 signals, each 0 or 1) ────────────────────────────────

def piotroski_f_score(ticker: str) -> dict:
    """
    Returns F-Score 0-9 and individual signal breakdown.
    Uses TTM financials from yfinance.
    """
    sym = ticker if "." in ticker else ticker + ".NS"
    stock = yf.Ticker(sym)
    signals = {}
    score   = 0

    try:
        info = stock.info
        fin  = stock.financials
        bs   = stock.balance_sheet
        cf   = stock.cashflow

        def safe(df, row, col=0):
            try:
                return float(df.loc[row].iloc[col])
            except Exception:
                return 0.0

        # ── Profitability (4 signals) ──────────────────────────────────────────
        net_income = safe(fin, "Net Income")
        total_assets_curr = safe(bs,  "Total Assets")
        total_assets_prev = safe(bs,  "Total Assets", 1)
        avg_assets = (total_assets_curr + total_assets_prev) / 2 or 1

        roa = net_income / avg_assets
        signals["F1_roa_positive"]   = int(roa > 0);             score += signals["F1_roa_positive"]

        op_cf = safe(cf, "Operating Cash Flow")
        signals["F2_op_cf_positive"] = int(op_cf > 0);           score += signals["F2_op_cf_positive"]

        roa_prev = safe(fin, "Net Income", 1) / avg_assets
        signals["F3_roa_increasing"] = int(roa > roa_prev);      score += signals["F3_roa_increasing"]

        signals["F4_accruals"]       = int(op_cf / avg_assets > roa); score += signals["F4_accruals"]

        # ── Leverage / Liquidity (3 signals) ──────────────────────────────────
        lt_debt_curr = safe(bs, "Long Term Debt")
        lt_debt_prev = safe(bs, "Long Term Debt", 1)
        signals["F5_leverage_dec"]  = int(lt_debt_curr < lt_debt_prev); score += signals["F5_leverage_dec"]

        curr_assets  = safe(bs, "Current Assets")
        curr_liab    = safe(bs, "Current Liabilities")
        curr_ratio   = curr_assets / curr_liab if curr_liab else 0
        curr_assets_p = safe(bs, "Current Assets", 1)
        curr_liab_p   = safe(bs, "Current Liabilities", 1)
        curr_ratio_p  = curr_assets_p / curr_liab_p if curr_liab_p else 0
        signals["F6_liquidity_inc"] = int(curr_ratio > curr_ratio_p); score += signals["F6_liquidity_inc"]

        shares_curr = info.get("sharesOutstanding", 0)
        shares_prev = info.get("impliedSharesOutstanding", shares_curr)
        signals["F7_no_dilution"]   = int(shares_curr <= shares_prev); score += signals["F7_no_dilution"]

        # ── Operating Efficiency (2 signals) ──────────────────────────────────
        rev   = safe(fin, "Total Revenue")
        rev_p = safe(fin, "Total Revenue", 1)
        gp    = safe(fin, "Gross Profit")
        gp_p  = safe(fin, "Gross Profit", 1)
        gm    = gp / rev   if rev   else 0
        gm_p  = gp_p / rev_p if rev_p else 0
        signals["F8_gm_increasing"] = int(gm > gm_p);             score += signals["F8_gm_increasing"]

        asset_to = rev / avg_assets
        rev_p_sum = safe(fin, "Total Revenue", 1)
        avg_asp = (total_assets_prev + safe(bs, "Total Assets", 2)) / 2 or 1
        at_prev = rev_p_sum / avg_asp
        signals["F9_asset_turnover_inc"] = int(asset_to > at_prev); score += signals["F9_asset_turnover_inc"]

    except Exception as e:
        log.error("Piotroski computation failed for %s: %s", ticker, e)

    label = "STRONG" if score >= 7 else "NEUTRAL" if score >= 4 else "WEAK"
    return {
        "ticker":  ticker,
        "f_score": score,
        "label":   label,
        "signals": signals,
        "gate_pass": score >= POSITIONAL.get("min_piotroski_score", 7),
    }


# ── Altman Z-Score (non-manufacturing / service firms) ────────────────────────

def altman_z_score(ticker: str) -> dict:
    """
    Non-manufacturing Z-Score:
    Z = 6.56*(WC/TA) + 3.26*(RE/TA) + 6.72*(EBIT/TA) + 1.05*(BVE/BVTL)
    Safe: Z > 2.6    Grey zone: 1.1–2.6    Distress: Z < 1.1
    """
    sym   = ticker if "." in ticker else ticker + ".NS"
    stock = yf.Ticker(sym)

    try:
        fin = stock.financials
        bs  = stock.balance_sheet

        def safe(df, row, col=0):
            try: return float(df.loc[row].iloc[col])
            except: return 0.0

        total_assets       = safe(bs, "Total Assets")
        current_assets     = safe(bs, "Current Assets")
        current_liab       = safe(bs, "Current Liabilities")
        retained_earnings  = safe(bs, "Retained Earnings")
        ebit               = safe(fin, "EBIT")
        book_equity        = safe(bs, "Stockholders Equity")
        total_liab         = safe(bs, "Total Liabilities Net Minority Interest")

        wc = current_assets - current_liab

        if total_assets == 0:
            return {"ticker": ticker, "z_score": 0.0, "zone": "UNKNOWN", "gate_pass": False}

        x1 = wc / total_assets
        x2 = retained_earnings / total_assets
        x3 = ebit / total_assets
        x4 = book_equity / total_liab if total_liab else 0

        z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

        zone = "SAFE" if z >= 2.6 else "GREY" if z >= 1.1 else "DISTRESS"
        return {
            "ticker":    ticker,
            "z_score":   round(z, 3),
            "zone":      zone,
            "x1_wc_ta":  round(x1, 4),
            "x2_re_ta":  round(x2, 4),
            "x3_ebit_ta": round(x3, 4),
            "x4_bve_bvl": round(x4, 4),
            "gate_pass": z >= POSITIONAL.get("min_altman_z", 1.1),
        }
    except Exception as e:
        log.error("Altman Z failed for %s: %s", ticker, e)
        return {"ticker": ticker, "z_score": 0.0, "zone": "UNKNOWN", "gate_pass": False}


# ── EPS Growth Trend ──────────────────────────────────────────────────────────

def eps_growth_trend(ticker: str, required_quarters: int = 3) -> dict:
    """
    Check N consecutive quarters of positive YoY EPS growth.
    EPS growth = (current_Q_EPS - same_Q_last_year_EPS) / |same_Q_last_year_EPS| * 100
    """
    sym   = ticker if "." in ticker else ticker + ".NS"
    stock = yf.Ticker(sym)

    try:
        qfin = stock.quarterly_financials
        if qfin is None or qfin.empty:
            return {"gate_pass": False, "quarters_positive": 0, "message": "No quarterly data"}

        net_row = "Net Income" if "Net Income" in qfin.index else None
        if net_row is None:
            return {"gate_pass": False, "quarters_positive": 0, "message": "No Net Income row"}

        eps_series = qfin.loc[net_row]
        # Need at least required_quarters + 4 (for YoY comparison) data points
        if len(eps_series) < required_quarters + 4:
            return {"gate_pass": False, "quarters_positive": 0, "message": "Insufficient history"}

        growth_flags = []
        for i in range(required_quarters):
            curr = float(eps_series.iloc[i])
            prev = float(eps_series.iloc[i + 4])   # same Q last year
            if prev == 0:
                growth_flags.append(False)
            else:
                growth_pct = (curr - prev) / abs(prev) * 100
                growth_flags.append(growth_pct > 0)

        quarters_ok = sum(growth_flags)
        return {
            "gate_pass":         all(growth_flags),
            "quarters_positive": quarters_ok,
            "required":          required_quarters,
            "flags":             growth_flags,
        }
    except Exception as e:
        log.error("EPS growth check failed for %s: %s", ticker, e)
        return {"gate_pass": False, "quarters_positive": 0, "message": str(e)}


# ── Combined fundamental gate ─────────────────────────────────────────────────

def fundamental_gate(ticker: str) -> dict:
    """
    Runs all positional fundamental checks.
    Returns fundamental_score 0-1 (normalised) and full breakdown.
    """
    ps  = piotroski_f_score(ticker)
    az  = altman_z_score(ticker)
    eps = eps_growth_trend(ticker)

    # Normalise F-score to 0-1
    f_norm = ps["f_score"] / 9.0

    # Normalise Z-score: 0 → 0, 2.6 → 1
    z_norm = min(1.0, max(0.0, az["z_score"] / 2.6))

    # EPS gate: 0 or 1
    eps_score = 1.0 if eps["gate_pass"] else 0.0

    # Weighted fundamental gate score
    fund_score = 0.50 * f_norm + 0.35 * z_norm + 0.15 * eps_score

    all_pass = ps["gate_pass"] and az["gate_pass"] and eps["gate_pass"]
    return {
        "ticker":          ticker,
        "all_gates_pass":  all_pass,
        "fundamental_score": round(fund_score, 4),
        "piotroski":       ps,
        "altman":          az,
        "eps_growth":      eps,
    }
