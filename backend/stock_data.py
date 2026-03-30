
import yfinance as yf
import pandas as pd
import ta
from datetime import datetime


def fetch_stock_data(ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No data found for ticker: {ticker}")
    df.reset_index(inplace=True)
    return df


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    df["SMA_20"] = ta.trend.sma_indicator(close, window=20)
    df["SMA_50"] = ta.trend.sma_indicator(close, window=50)
    df["EMA_20"] = ta.trend.ema_indicator(close, window=20)
    df["RSI"] = ta.momentum.rsi(close, window=14)

    macd = ta.trend.MACD(close)
    df["MACD"] = macd.macd()
    df["MACD_Signal"] = macd.macd_signal()
    df["MACD_Hist"] = macd.macd_diff()

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["BB_Upper"] = bb.bollinger_hband()
    df["BB_Lower"] = bb.bollinger_lband()
    df["BB_Width"] = bb.bollinger_wband()

    df["ATR"] = ta.volatility.average_true_range(high, low, close, window=14)

    df["Volume_SMA_20"] = ta.trend.sma_indicator(volume, window=20)
    df.dropna(inplace=True)
    return df


def get_stock_info(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    info = stock.info
    return {
        "name": info.get("shortName", ticker),
        "sector": info.get("sector", "N/A"),
        "currency": info.get("currency", "INR"),
        "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
        "market_cap": info.get("marketCap", 0),
        "day_high": info.get("dayHigh", 0),
        "day_low": info.get("dayLow", 0),
        "prev_close": info.get("previousClose", 0),
        "open": info.get("open", 0),
        "volume": info.get("volume", 0),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
    }


def fetch_live_price(ticker: str) -> dict:
    stock = yf.Ticker(ticker)
    info = stock.info

    current = info.get("currentPrice", info.get("regularMarketPrice", 0))
    prev_close = info.get("previousClose", 0)

    change = round(current - prev_close, 2) if current and prev_close else 0
    change_pct = round((change / prev_close) * 100, 2) if prev_close else 0

    return {
        "ticker": ticker,
        "price": current,
        "change": change,
        "change_pct": change_pct,
        "direction": "up" if change >= 0 else "down",
        "day_high": info.get("dayHigh", 0),
        "day_low": info.get("dayLow", 0),
        "volume": info.get("volume", 0),
        "timestamp": datetime.now().isoformat(),
    }


TIMEFRAME_MAP = {
    "1d": ("1d", "5m"),
    "5d": ("5d", "15m"),
    "1wk": ("5d", "15m"),
    "1mo": ("1mo", "1h"),
    "3mo": ("3mo", "1d"),
    "6mo": ("6mo", "1d"),
    "1y": ("1y", "1d"),
    "2y": ("2y", "1wk"),
}


def fetch_chart_data(ticker: str, timeframe: str) -> list[dict]:
    period, interval = TIMEFRAME_MAP.get(timeframe, ("1mo", "1h"))
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No chart data for {ticker}")
    df.reset_index(inplace=True)

    records = []
    date_col = "Datetime" if "Datetime" in df.columns else "Date"
    for _, row in df.iterrows():
        records.append({
            "time": str(row[date_col]),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })
    return records


# ─────────────────────────────────────────────────
#  INTRADAY DATA & FEATURES  (for Auto Trade only)
# ─────────────────────────────────────────────────

import numpy as np


def fetch_intraday_data(ticker: str, period: str = "5d", interval: str = "1m") -> pd.DataFrame:
    """Fetch 1-min intraday bars (max 7 days with yfinance)."""
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No intraday data for {ticker}")
    df.reset_index(inplace=True)
    col = "Datetime" if "Datetime" in df.columns else "Date"
    df.rename(columns={col: "Datetime"}, inplace=True)
    df["Datetime"] = pd.to_datetime(df["Datetime"])
    return df


def _supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    """Compute Supertrend indicator (period, multiplier)."""
    hl2 = (df["High"] + df["Low"]) / 2
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=period)

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(0.0, index=df.index)
    direction = pd.Series(1, index=df.index)  # 1 = bullish, -1 = bearish

    for i in range(1, len(df)):
        if df["Close"].iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif df["Close"].iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
            if direction.iloc[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i - 1]:
                lower_band.iloc[i] = lower_band.iloc[i - 1]
            if direction.iloc[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i - 1]:
                upper_band.iloc[i] = upper_band.iloc[i - 1]

        supertrend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]

    return supertrend, direction


def add_intraday_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all intraday trading indicators to a DataFrame of 1-min bars."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"].astype(float)

    # Moving averages
    df["EMA_9"] = ta.trend.ema_indicator(close, window=9)
    df["EMA_21"] = ta.trend.ema_indicator(close, window=21)
    df["SMA_50"] = ta.trend.sma_indicator(close, window=50)

    # Price vs MAs (percentage distance)
    df["price_vs_ema9"] = ((close - df["EMA_9"]) / df["EMA_9"]) * 100
    df["price_vs_ema21"] = ((close - df["EMA_21"]) / df["EMA_21"]) * 100
    df["price_vs_sma50"] = ((close - df["SMA_50"]) / df["SMA_50"]) * 100

    # Returns
    df["returns_1bar"] = close.pct_change(1) * 100
    df["returns_5bar"] = close.pct_change(5) * 100
    df["returns_15bar"] = close.pct_change(15) * 100

    # Momentum
    df["RSI"] = ta.momentum.rsi(close, window=14)
    macd_obj = ta.trend.MACD(close, window_fast=12, window_slow=26, window_sign=9)
    df["MACD"] = macd_obj.macd()
    df["MACD_Signal"] = macd_obj.macd_signal()
    df["MACD_Hist"] = macd_obj.macd_diff()

    # Volatility
    df["ATR"] = ta.volatility.average_true_range(high, low, close, window=14)
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["BB_Upper"] = bb.bollinger_hband()
    df["BB_Lower"] = bb.bollinger_lband()
    df["BB_Width"] = bb.bollinger_wband()
    bb_range = df["BB_Upper"] - df["BB_Lower"]
    df["BB_Position"] = np.where(bb_range > 0, (close - df["BB_Lower"]) / bb_range, 0.5)

    # VWAP
    cumvol = volume.cumsum()
    cumtp = (((high + low + close) / 3) * volume).cumsum()
    df["VWAP"] = np.where(cumvol > 0, cumtp / cumvol, close)
    df["price_vs_vwap"] = ((close - df["VWAP"]) / df["VWAP"]) * 100

    # Volume ratio
    vol_sma20 = volume.rolling(window=20).mean()
    df["volume_ratio"] = np.where(vol_sma20 > 0, volume / vol_sma20, 1.0)

    # Supertrend
    st_val, st_dir = _supertrend(df, period=10, multiplier=3.0)
    df["Supertrend"] = st_val
    df["Supertrend_Dir"] = st_dir  # 1=bullish, -1=bearish
    df["supertrend_dist"] = ((close - st_val) / close) * 100

    # Time features
    if "Datetime" in df.columns:
        dt = pd.to_datetime(df["Datetime"])
        df["minute_of_day"] = dt.dt.hour * 60 + dt.dt.minute
        df["is_first_hour"] = (dt.dt.hour == 9).astype(int)
        df["is_last_hour"] = (dt.dt.hour >= 15).astype(int)
    else:
        df["minute_of_day"] = 0
        df["is_first_hour"] = 0
        df["is_last_hour"] = 0

    df.dropna(inplace=True)
    return df


def fetch_india_vix() -> dict:
    """Fetch India VIX current level and recent change."""
    try:
        stock = yf.Ticker("^INDIAVIX")
        hist = stock.history(period="7d")
        if hist.empty:
            return {"vix_level": 15.0, "vix_change_5d": 0.0, "available": False}
        current = float(hist["Close"].iloc[-1])
        if len(hist) >= 5:
            prev = float(hist["Close"].iloc[-5])
        else:
            prev = float(hist["Close"].iloc[0])
        change = round(current - prev, 2)
        return {"vix_level": round(current, 2), "vix_change_5d": change, "available": True}
    except Exception:
        return {"vix_level": 15.0, "vix_change_5d": 0.0, "available": False}


def fetch_nifty_trend() -> dict:
    """Fetch Nifty 50 trend vs EMA-9 and EMA-21."""
    try:
        stock = yf.Ticker("^NSEI")
        hist = stock.history(period="1mo", interval="1d")
        if len(hist) < 21:
            return {"nifty_price": 0, "trend": "flat", "above_ema9": False,
                    "above_ema21": False, "available": False}
        close = hist["Close"]
        ema9 = ta.trend.ema_indicator(close, window=9)
        ema21 = ta.trend.ema_indicator(close, window=21)
        price = float(close.iloc[-1])
        e9 = float(ema9.iloc[-1])
        e21 = float(ema21.iloc[-1])

        above_ema9 = price > e9
        above_ema21 = price > e21

        if above_ema9 and above_ema21:
            trend = "bullish"
        elif not above_ema9 and not above_ema21:
            trend = "bearish"
        else:
            trend = "flat"

        return {
            "nifty_price": round(price, 2),
            "ema9": round(e9, 2),
            "ema21": round(e21, 2),
            "trend": trend,
            "above_ema9": above_ema9,
            "above_ema21": above_ema21,
            "available": True,
        }
    except Exception:
        return {"nifty_price": 0, "trend": "flat", "above_ema9": False,
                "above_ema21": False, "available": False}


def detect_ipo_stock(ticker: str) -> dict:
    """Check if stock was listed recently (IPO < 180 days)."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="max")
        if hist.empty:
            return {"is_ipo": False, "ipo_age_days": 999, "listing_date": None}
        first_date = hist.index[0]
        if hasattr(first_date, "date"):
            first_date = first_date.date()
        age_days = (datetime.now().date() - first_date).days
        return {
            "is_ipo": age_days < 180,
            "ipo_age_days": age_days,
            "listing_date": str(first_date),
        }
    except Exception:
        return {"is_ipo": False, "ipo_age_days": 999, "listing_date": None}

