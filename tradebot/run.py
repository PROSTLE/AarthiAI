#!/usr/bin/env python3
"""
run.py — TradeBot startup script
Usage:
    python run.py api           # Start FastAPI server on port 8001
    python run.py scan          # Run one manual pre-market scan now
    python run.py train         # Train intraday LightGBM model
    python run.py monitor       # Start intraday position monitor loop
"""
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tradebot")


def _start_api():
    import uvicorn
    log.info("Starting AarthiAI TradeBot API on http://0.0.0.0:8001")
    uvicorn.run("api.main:app", host="0.0.0.0", port=8001, reload=False)


def _run_scan():
    from ingestion.nse_data import (
        get_fii_dii, get_options_pcr, get_global_cues,
        get_sector_momentum, get_news_headlines
    )
    from signals.signal_engine import run_premarket_scan
    from signals.brief_generator import generate_brief
    from behavioral.mood import Mood, MOOD_CONFIG

    log.info("Fetching premarket context...")
    context = {
        "fii":             get_fii_dii(),
        "nifty_pcr":       get_options_pcr("NIFTY"),
        "global_cues":     get_global_cues(),
        "sector_momentum": get_sector_momentum(),
        "headlines":       get_news_headlines(),
    }
    log.info("Running signal scan...")
    signals = run_premarket_scan(context)
    mode    = MOOD_CONFIG[Mood.FOCUSED]
    mode.remaining_budget = 5000.0

    brief = generate_brief(signals, mode)
    print("\n" + brief)

    n = len(signals.get("intraday_picks", []))
    log.info("Scan complete. %d intraday signal(s) generated.", n)


def _train_models():
    from ingestion.nse_data import get_historical_ohlcv, get_intraday_ohlcv
    from models.intraday_lgbm import train as train_lgbm

    log.info("Fetching training data for RELIANCE.NS (5d intraday)...")
    df = get_intraday_ohlcv("RELIANCE.NS", period="5d", interval="5m")
    log.info("Training LightGBM intraday model on %d bars...", len(df))
    model = train_lgbm(df)
    log.info("Training complete. Model saved to models/saved/lgbm_intraday.pkl")


def _start_monitor():
    from execution.order_manager import start_intraday_monitor
    import time
    log.info("Starting 5-minute intraday position monitor...")
    t = start_intraday_monitor("default")
    log.info("Monitor running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("Monitor stopped.")


COMMANDS = {
    "api":     _start_api,
    "scan":    _run_scan,
    "train":   _train_models,
    "monitor": _start_monitor,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "api"
    fn  = COMMANDS.get(cmd)
    if not fn:
        print(f"Unknown command: {cmd}")
        print(f"Available: {list(COMMANDS.keys())}")
        sys.exit(1)
    fn()
