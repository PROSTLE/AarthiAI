"""
features/technical.py
Full feature engineering pipeline for intraday and swing signals.
Uses pandas-ta for all indicators — single-line calls on the DataFrame.
"""
import pandas as pd
import numpy as np
import pandas_ta as ta
from scipy import stats
from config import INTRADAY, SWING

# ── Column name constants (pandas-ta defaults) ────────────────────────────────
RSI_COL     = "RSI_14"
MACD_COL    = "MACD_12_26_9"
MACDH_COL   = "MACDh_12_26_9"
BBU_COL     = "BBU_20_2.0"
BBL_COL     = "BBL_20_2.0"
BBM_COL     = "BBM_20_2.0"
BBB_COL     = "BBB_20_2.0"   # bandwidth
ATR_COL     = "ATRr_14"
VWAP_COL    = "VWAP_D"
OBV_COL     = "OBV"
EMA9_COL    = "EMA_9"
EMA21_COL   = "EMA_21"
EMA50_COL   = "EMA_50"
EMA200_COL  = "EMA_200"


def build_intraday_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input : OHLCV DataFrame with DatetimeIndex (5-min bars, IST tz-aware)
    Output: same df enriched with ~30 features ready for LightGBM
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]

    # ── Core indicators ────────────────────────────────────────────────────────
    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.obv(append=True)
    df.ta.ema(length=9,   append=True)
    df.ta.ema(length=21,  append=True)
    df.ta.ema(length=50,  append=True)
    df.ta.ema(length=200, append=True)

    # VWAP — pandas-ta uses VWAP_D (daily reset)
    df.ta.vwap(append=True)

    # ── Derived features ───────────────────────────────────────────────────────
    df["vwap_dev_pct"] = (df["close"] - df[VWAP_COL]) / df[VWAP_COL] * 100

    # Bollinger squeeze: width < 20-period min of width
    if BBB_COL in df.columns:
        df["bb_width"]   = df[BBB_COL]
        df["bb_squeeze"] = (df["bb_width"] < df["bb_width"].rolling(20).min()).astype(int)
        df["bb_pct_b"]   = (df["close"] - df[BBL_COL]) / (df[BBU_COL] - df[BBL_COL])
    else:
        df["bb_width"] = df["bb_squeeze"] = df["bb_pct_b"] = 0.0

    # Volume Surge Ratio
    # rolling 20-day window at same bar-of-day (78 bars per day for 5-min)
    df["vol_sma_20d"] = df["volume"].rolling(window=78 * 20, min_periods=78).mean()
    df["vsr"]         = df["volume"] / df["vol_sma_20d"].replace(0, np.nan)
    df["vsr"]         = df["vsr"].fillna(1.0)

    # ATR-based stop / target
    if ATR_COL in df.columns:
        atr = INTRADAY.get("atr_stop_multiplier", 1.5)
        tgt = INTRADAY.get("atr_target_multiplier", 2.5)
        df["stop_dist"]   = df[ATR_COL] * atr
        df["target_dist"] = df[ATR_COL] * tgt

    # EMA crossover flag
    if EMA9_COL in df.columns and EMA21_COL in df.columns:
        df["ema_cross_bull"] = ((df[EMA9_COL] > df[EMA21_COL]) &
                                (df[EMA9_COL].shift(1) <= df[EMA21_COL].shift(1))).astype(int)
        df["ema_cross_bear"] = ((df[EMA9_COL] < df[EMA21_COL]) &
                                (df[EMA9_COL].shift(1) >= df[EMA21_COL].shift(1))).astype(int)

    # Price returns
    df["ret_1bar"]  = df["close"].pct_change(1) * 100
    df["ret_5bar"]  = df["close"].pct_change(5) * 100
    df["ret_15bar"] = df["close"].pct_change(15) * 100

    # Z-score normalisation for ML input
    for col in [RSI_COL, "vwap_dev_pct", "vsr", ATR_COL, MACD_COL,
                "ret_1bar", "ret_5bar", "ret_15bar", "bb_width"]:
        if col in df.columns:
            vals = df[col].fillna(0).values
            df[f"{col}_z"] = stats.zscore(vals, nan_policy="omit")

    df.dropna(subset=[RSI_COL, ATR_COL], inplace=True)
    return df


def build_swing_features(df_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Daily OHLCV → swing trading features.
    Adds EMA structure, BB squeeze, relative strength support.
    """
    df = df_daily.copy()
    df.columns = [c.lower() for c in df.columns]

    df.ta.rsi(length=14, append=True)
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    df.ta.bbands(length=20, std=2, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.ema(length=9,  append=True)
    df.ta.ema(length=21, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.obv(append=True)

    # Swing-specific: 9 EMA x 21 EMA on daily
    if EMA9_COL in df.columns and EMA21_COL in df.columns:
        df["ema_cross_bull_daily"] = (
            (df[EMA9_COL] > df[EMA21_COL]) &
            (df[EMA9_COL].shift(1) <= df[EMA21_COL].shift(1))
        ).astype(int)

        # Trend quality: above 50 EMA AND 50 EMA slope positive
        if EMA50_COL in df.columns:
            df["trend_valid"] = (
                (df["close"] > df[EMA50_COL]) &
                (df[EMA50_COL] > df[EMA50_COL].shift(5))
            ).astype(int)

    # BB squeeze on daily — breakout signal
    if BBB_COL in df.columns:
        df["bb_width"]    = df[BBB_COL]
        df["bb_squeeze"]  = (df["bb_width"] < df["bb_width"].rolling(20).min()).astype(int)
        df["bb_breakout_long"]  = (
            (df["bb_squeeze"].shift(1) == 1) &
            (df["close"] > df[BBU_COL])
        ).astype(int)
        df["bb_breakout_short"] = (
            (df["bb_squeeze"].shift(1) == 1) &
            (df["close"] < df[BBL_COL])
        ).astype(int)

    # Swing low / high for stop placement
    df["swing_low_20"]  = df["low"].rolling(20).min()
    df["swing_high_20"] = df["high"].rolling(20).max()

    # OBV momentum
    if OBV_COL in df.columns:
        df["obv_slope"] = df[OBV_COL].diff(5)

    df.dropna(inplace=True)
    return df


def compute_relative_strength(
    stock_returns_20d: float,
    sector_returns_20d: float,
) -> float:
    """RS = stock 20-day return minus sector 20-day return."""
    return round(stock_returns_20d - sector_returns_20d, 4)


def get_opening_range(df_5min: pd.DataFrame) -> dict:
    """
    Compute ORB levels from 9:15–9:30 candles.
    Returns orb_high, orb_low, and current breakout signal.
    """
    try:
        orb = df_5min.between_time("09:15", "09:29")
    except TypeError:
        # Index not tz-aware — localise
        df_5min.index = df_5min.index.tz_localize("Asia/Kolkata")
        orb = df_5min.between_time("09:15", "09:29")

    if orb.empty:
        return {"signal": "NONE", "orb_high": None, "orb_low": None}

    orb_high = float(orb["high"].max())
    orb_low  = float(orb["low"].min())
    threshold = INTRADAY.get("orb_breakout_pct", 0.25) / 100
    vol_mult  = INTRADAY.get("volume_confirm_multiplier", 1.5)

    current = df_5min.iloc[-1]
    vol_confirmed = float(current.get("vsr", 1.0)) >= vol_mult

    if float(current["close"]) > orb_high * (1 + threshold) and vol_confirmed:
        signal = "LONG"
    elif float(current["close"]) < orb_low * (1 - threshold) and vol_confirmed:
        signal = "SHORT"
    else:
        signal = "NONE"

    return {"signal": signal, "orb_high": orb_high, "orb_low": orb_low,
            "vol_confirmed": vol_confirmed, "vsr": float(current.get("vsr", 1.0))}


INTRADAY_FEATURE_COLS = [
    f"{RSI_COL}_z", "vwap_dev_pct_z", "vsr", f"{ATR_COL}_z",
    f"{MACD_COL}_z", "bb_width_z", "bb_squeeze", "ema_cross_bull",
    f"ret_1bar_z", f"ret_5bar_z", f"ret_15bar_z",
]

SWING_FEATURE_COLS = [
    RSI_COL, MACD_COL, MACDH_COL, "bb_width", "bb_squeeze",
    "ema_cross_bull_daily", "trend_valid", "obv_slope",
    "bb_breakout_long", "bb_breakout_short",
]
