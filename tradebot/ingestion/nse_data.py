"""
ingestion/nse_data.py
NSE bulk data: FII/DII, options chain PCR, sector index data, F&O ban list.
"""
import logging
import yfinance as yf
import feedparser
import requests
import pandas as pd
from datetime import datetime, timedelta

try:
    from nsepython import (
        fii_dii_data,
        nse_optionchain_scrapper,
        nse_fo_ban,
        nsefetch,
    )
    _NSE_AVAILABLE = True
except ImportError:
    _NSE_AVAILABLE = False

log = logging.getLogger(__name__)

# NSE sector index tickers (yfinance-compatible)
SECTOR_INDICES = {
    "IT":           "^CNXIT",
    "Banking":      "^NSEBANK",
    "Auto":         "^CNXAUTO",
    "Pharma":       "^CNXPHARMA",
    "FMCG":         "^CNXFMCG",
    "Metal":        "^CNXMETAL",
    "Energy":       "^CNXENERGY",
    "Realty":       "^CNXREALTY",
    "Infrastructure":"^NIFTYINFRA",
    "Media":        "^CNXMEDIA",
}

NEWS_FEEDS = [
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.livemint.com/rss/markets",
]


# ── FII / DII ─────────────────────────────────────────────────────────────────

def get_fii_dii() -> dict:
    """Returns provisional FII/DII net figures in Crore INR."""
    if not _NSE_AVAILABLE:
        log.warning("nsepython not available — returning zeros for FII/DII")
        return {"fii_net": 0.0, "dii_net": 0.0, "date": str(datetime.today().date())}
    try:
        raw = fii_dii_data()
        fii = raw.loc[raw["category"].str.upper() == "FII", "net_value"]
        dii = raw.loc[raw["category"].str.upper() == "DII", "net_value"]
        return {
            "fii_net": float(fii.iloc[0]) if len(fii) else 0.0,
            "dii_net": float(dii.iloc[0]) if len(dii) else 0.0,
            "date":    str(datetime.today().date()),
        }
    except Exception as e:
        log.error("FII/DII fetch failed: %s", e)
        return {"fii_net": 0.0, "dii_net": 0.0, "date": str(datetime.today().date())}


# ── Options chain PCR ─────────────────────────────────────────────────────────

def get_options_pcr(symbol: str = "NIFTY") -> float:
    """Put-Call Ratio from live NSE options chain."""
    if not _NSE_AVAILABLE:
        return 1.0
    try:
        chain   = nse_optionchain_scrapper(symbol)
        records = chain.get("records", {}).get("data", [])
        put_oi  = sum(r.get("PE", {}).get("openInterest", 0) for r in records)
        call_oi = sum(r.get("CE", {}).get("openInterest", 0) for r in records)
        return round(put_oi / call_oi, 3) if call_oi > 0 else 1.0
    except Exception as e:
        log.error("PCR fetch failed for %s: %s", symbol, e)
        return 1.0


def get_fo_ban_list() -> list[str]:
    """Returns list of NSE tickers currently in F&O ban."""
    if not _NSE_AVAILABLE:
        return []
    try:
        return [s.strip().upper() for s in nse_fo_ban()]
    except Exception as e:
        log.error("F&O ban list fetch failed: %s", e)
        return []


# ── Global futures (pre-market cues) ─────────────────────────────────────────

GLOBAL_FUTURES = {
    "sgx_nifty_proxy": "EWS",    # iShares MSCI India ETF as SGX proxy
    "dow_futures":     "YM=F",
    "nasdaq_futures":  "NQ=F",
    "sp500_futures":   "ES=F",
    "crude_oil":       "CL=F",
    "gold":            "GC=F",
    "usd_inr":         "INR=X",
}


def get_global_cues() -> dict:
    """Fetch overnight % change for global futures."""
    result = {}
    for name, sym in GLOBAL_FUTURES.items():
        try:
            hist = yf.Ticker(sym).history(period="3d")
            if len(hist) >= 2:
                prev  = float(hist["Close"].iloc[-2])
                curr  = float(hist["Close"].iloc[-1])
                pct   = (curr - prev) / prev * 100 if prev else 0.0
                result[name] = {"price": round(curr, 4), "change_pct": round(pct, 3)}
            else:
                result[name] = {"price": 0.0, "change_pct": 0.0}
        except Exception as e:
            log.warning("Global cue fetch failed for %s: %s", sym, e)
            result[name] = {"price": 0.0, "change_pct": 0.0}
    return result


# ── Sector momentum ───────────────────────────────────────────────────────────

def get_sector_momentum(days: int = 5) -> dict[str, float]:
    """Returns 5-day % return for each sector index."""
    momentum = {}
    for sector, sym in SECTOR_INDICES.items():
        try:
            hist = yf.Ticker(sym).history(period="15d")
            if len(hist) >= days + 1:
                ret = (hist["Close"].iloc[-1] - hist["Close"].iloc[-(days + 1)]) / hist["Close"].iloc[-(days + 1)] * 100
                momentum[sector] = round(float(ret), 3)
            else:
                momentum[sector] = 0.0
        except Exception:
            momentum[sector] = 0.0
    return momentum


# ── News headlines ────────────────────────────────────────────────────────────

def get_news_headlines(max_per_feed: int = 20) -> list[dict]:
    headlines = []
    for url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                headlines.append({
                    "title":     entry.get("title", ""),
                    "published": entry.get("published", ""),
                    "summary":   entry.get("summary", "")[:300],
                    "source":    feed.feed.get("title", url),
                    "link":      entry.get("link", ""),
                })
        except Exception as e:
            log.warning("Feed parse failed for %s: %s", url, e)
    return headlines


# ── Historical OHLCV ──────────────────────────────────────────────────────────

def get_historical_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """Fetch using yfinance. Always append .NS for NSE stocks."""
    sym = ticker if "." in ticker else ticker + ".NS"
    df  = yf.Ticker(sym).history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No OHLCV data for {sym}")
    df.columns = [c.lower() for c in df.columns]
    df.index.name = "datetime"
    return df


def get_intraday_ohlcv(ticker: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """5-min intraday bars — max 60 days, 1-min max 7 days via yfinance."""
    sym = ticker if "." in ticker else ticker + ".NS"
    df  = yf.Ticker(sym).history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No intraday data for {sym}")
    df.columns = [c.lower() for c in df.columns]
    df.index   = pd.to_datetime(df.index)
    df.index.name = "datetime"
    return df
