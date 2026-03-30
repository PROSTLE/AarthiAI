"""
signals/signal_engine.py
Core signal generation pipeline — runs at 9:15 AM.
Takes premarket context → scores stocks → generates Daily Signal Brief.
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from config import INTRADAY, SWING, POSITIONAL, CONFIDENCE

log = logging.getLogger(__name__)

# Universe of stocks to scan (expand as needed)
SCAN_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "WIPRO.NS", "BAJFINANCE.NS", "AXISBANK.NS", "MARUTI.NS", "TATAMOTORS.NS",
    "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "ONGC.NS", "COALINDIA.NS",
    "NTPC.NS", "POWERGRID.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "ULTRACEMCO.NS", "SHREECEM.NS",
    "ASIANPAINT.NS", "NESTLEIND.NS", "HINDUNILVR.NS", "TITAN.NS",
    "BAJAJFINSV.NS", "SBILIFE.NS", "HCLTECH.NS", "TECHM.NS", "LTI.NS",
    "DIVISLAB.NS", "APOLLOHOSP.NS", "HDFCLIFE.NS", "ICICIGI.NS",
]


def generate_intraday_signal(
    ticker: str,
    df_5min: pd.DataFrame,
    sector_heat: float,
    sentiment_score: float,
    ban_list: list[str],
) -> dict | None:
    """
    Full intraday signal pipeline for one ticker.
    Returns signal dict or None if no setup.
    """
    # F&O ban check
    clean = ticker.replace(".NS", "").replace(".BO", "")
    if clean in ban_list:
        log.debug("Skipping %s — in F&O ban", ticker)
        return None

    from features.technical import build_intraday_features, get_opening_range
    from features.sector_heat import compute_confidence_score

    try:
        df = build_intraday_features(df_5min)
        if df.empty:
            return None

        last = df.iloc[-1]
        rsi  = float(last.get("RSI_14", 50))

        # ── RSI exhaustion filter ──────────────────────────────────────────────
        rsi_hi = INTRADAY.get("rsi_exhaustion_high", 80)
        rsi_lo = INTRADAY.get("rsi_exhaustion_low", 20)
        if rsi > rsi_hi or rsi < rsi_lo:
            return None

        # ── ORB signal ────────────────────────────────────────────────────────
        orb = get_opening_range(df)
        if orb["signal"] == "NONE":
            return None

        signal    = orb["signal"]
        entry     = float(last["close"])
        atr       = float(last.get("ATRr_14", entry * 0.01))
        stop_dist = atr * INTRADAY.get("atr_stop_multiplier", 1.5)
        tgt_dist  = atr * INTRADAY.get("atr_target_multiplier", 2.5)

        if signal == "LONG":
            stop   = entry - stop_dist
            target = entry + tgt_dist
        else:
            stop   = entry + stop_dist
            target = entry - tgt_dist

        vsr      = float(last.get("vsr", 1.0))
        vwap_dev = float(last.get("vwap_dev_pct", 0.0))

        # ── VWAP confirmation ─────────────────────────────────────────────────
        vwap_min = INTRADAY.get("vwap_deviation_pct", 0.4)
        rsi_long_ok  = INTRADAY.get("rsi_long_min", 55) <= rsi <= INTRADAY.get("rsi_long_max", 75)
        rsi_short_ok = INTRADAY.get("rsi_short_min", 25) <= rsi <= INTRADAY.get("rsi_short_max", 45)

        if signal == "LONG"  and not (vwap_dev >  vwap_min and rsi_long_ok):
            return None
        if signal == "SHORT" and not (vwap_dev < -vwap_min and rsi_short_ok):
            return None

        # ── ML model score ────────────────────────────────────────────────────
        ml_prob = 0.5
        ml_reason = "ML model unavailable — using ORB only"
        try:
            from models.intraday_lgbm import predict_for_ticker
            pred     = predict_for_ticker(df)
            ml_prob  = pred["prob"] if signal == "LONG" else 1 - pred["prob"]
            ml_reason = pred["reason"]
        except Exception as e:
            log.debug("ML prediction skipped for %s: %s", ticker, e)

        # ── Technical score (0-1) heuristic ──────────────────────────────────
        tech_score = 0.0
        tech_score += 0.30 if orb["vol_confirmed"] else 0.0
        tech_score += 0.20 if vsr >= INTRADAY.get("vsr_strong", 2.5) else vsr / 10
        tech_score += 0.25 if (signal == "LONG" and rsi_long_ok) or (signal == "SHORT" and rsi_short_ok) else 0.0
        tech_score += 0.25 if abs(vwap_dev) >= vwap_min else 0.0
        tech_score = min(1.0, tech_score)

        # ── Composite confidence ──────────────────────────────────────────────
        sent_01 = (sentiment_score + 1) / 2
        confidence = compute_confidence_score(
            ml_prob, tech_score, sector_heat, 0.5, sent_01
        )

        # ── VSR extreme: reduce size warning ─────────────────────────────────
        vsr_flag = vsr >= INTRADAY.get("vsr_extreme", 4.0)

        return {
            "ticker":          ticker,
            "signal":          signal,
            "trade_type":      "intraday",
            "entry":           round(entry, 2),
            "stop":            round(stop, 2),
            "target":          round(target, 2),
            "rr_ratio":        round(tgt_dist / stop_dist, 2),
            "rsi":             round(rsi, 1),
            "vsr":             round(vsr, 2),
            "vwap_dev_pct":    round(vwap_dev, 3),
            "atr":             round(atr, 2),
            "confidence":      round(confidence, 1),
            "ml_prob":         round(ml_prob, 4),
            "shap_reason":     ml_reason,
            "vsr_extreme_flag": vsr_flag,
            "orb_high":        orb.get("orb_high"),
            "orb_low":         orb.get("orb_low"),
            "generated_at":    datetime.now().isoformat(),
        }

    except Exception as e:
        log.error("Signal generation failed for %s: %s", ticker, e)
        return None


def run_premarket_scan(
    premarket_context: dict,          # from premarket_pipeline DAG
    top_n_intraday: int = 3,
    top_n_swing: int = 2,
) -> dict:
    """
    Master scan at 9:15 AM.
    Returns structured signal output for the Daily Signal Brief.
    """
    from ingestion.nse_data import (
        get_intraday_ohlcv, get_fo_ban_list, get_sector_momentum, get_news_headlines
    )
    from sentiment.finbert import batch_score_market
    from features.sector_heat import compute_sector_heat, rank_sectors

    log.info("Starting pre-market scan at %s", datetime.now().strftime("%H:%M:%S"))

    ban_list      = get_fo_ban_list()
    headlines     = premarket_context.get("headlines", [])
    fii           = premarket_context.get("fii", {})
    sector_mom    = premarket_context.get("sector_momentum", {})
    global_cues   = premarket_context.get("global_cues", {})
    nifty_pcr     = premarket_context.get("nifty_pcr", 1.0)

    # Sentiment for all tickers
    clean_tickers    = [t.replace(".NS", "") for t in SCAN_UNIVERSE]
    sentiment_scores = batch_score_market(headlines, clean_tickers)

    # Sector heat scores
    global_avg = np.mean([v["change_pct"] for v in global_cues.values()]) if global_cues else 0.0
    sector_heats: dict[str, float] = {}
    for sector, mom in sector_mom.items():
        sector_heats[sector] = compute_sector_heat(
            news_sentiment=0.0,
            fii_flow_crore=fii.get("fii_net", 0),
            sector_return_5d=mom,
            global_change_pct=global_avg,
            pcr=nifty_pcr,
        )

    top_sectors = rank_sectors(sector_heats)
    best_heat   = top_sectors[0]["heat"] if top_sectors else 50.0

    # Intraday signals
    intraday_signals = []
    for ticker in SCAN_UNIVERSE:
        clean = ticker.replace(".NS", "")
        if clean in ban_list:
            continue
        try:
            df_5min = get_intraday_ohlcv(ticker, period="1d", interval="5m")
            sent    = sentiment_scores.get(clean, 0.0)
            sig     = generate_intraday_signal(ticker, df_5min, best_heat, sent, ban_list)
            if sig:
                intraday_signals.append(sig)
        except Exception as e:
            log.debug("Scan failed for %s: %s", ticker, e)

    intraday_signals.sort(key=lambda x: x["confidence"], reverse=True)

    return {
        "intraday_picks": intraday_signals[:top_n_intraday],
        "swing_picks":    [],          # populated by separate swing scanner
        "positional_pick": None,       # populated by fundamental scanner
        "sector_heats":   top_sectors,
        "market_context": premarket_context,
        "scan_time":      datetime.now().isoformat(),
        "ban_list":       ban_list,
    }
