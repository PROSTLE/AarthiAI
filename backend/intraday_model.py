"""
Intraday XGBoost model for short-term price movement forecasting.
Predicts next 3-5 bar (minute) returns using tabular features.
Used exclusively by the Auto Trade tab.

Includes:
- In-memory model cache (10-min TTL) to avoid retraining every tick
- Sector-strength feature
- generate_intraday_signal() - full pipeline producing structured signals
"""

import time
import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error
from stock_data import (
    fetch_intraday_data,
    add_intraday_indicators,
    fetch_india_vix,
    fetch_nifty_trend,
    detect_ipo_stock,
)
from trader import (
    compute_dynamic_levels,
    detect_market_regime,
)


# Features the model uses (must match columns from add_intraday_indicators)
FEATURE_COLS = [
    # Price & returns
    "returns_1bar", "returns_5bar", "returns_15bar",
    # Moving average distances
    "price_vs_ema9", "price_vs_ema21", "price_vs_sma50",
    # Momentum
    "RSI", "MACD", "MACD_Signal", "MACD_Hist",
    # Volatility
    "ATR", "BB_Width", "BB_Position",
    # Volume
    "volume_ratio", "price_vs_vwap",
    # Trend
    "Supertrend_Dir", "supertrend_dist",
    # Time
    "minute_of_day", "is_first_hour", "is_last_hour",
]

# Market context features (appended at prediction time)
MARKET_FEATURES = ["vix_level", "vix_change_5d", "nifty_trend_dir", "sector_strength"]

FORWARD_BARS = 5  # Predict return over next 5 minutes
MODEL_CACHE_TTL = 600  # 10 minutes in seconds

# --- In-memory model cache ---
_model_cache: dict = {}  # ticker -> {model, feature_names, metrics, timestamp}


def _cache_valid(ticker: str) -> bool:
    """Check if cached model for ticker is still within TTL."""
    if ticker not in _model_cache:
        return False
    return (time.time() - _model_cache[ticker]["timestamp"]) < MODEL_CACHE_TTL


# --- Sector strength helper ---
SECTOR_INDEX_MAP = {
    "Financial Services": "^NSEBANK",
    "Information Technology": "^CNXIT",
    "Pharmaceuticals": "^CNXPHARMA",
    "Energy": "^CNXENERGY",
    "Automobile": "^CNXAUTO",
    "FMCG": "^CNXFMCG",
    "Metals & Mining": "^CNXMETAL",
    "Realty": "^CNXREALTY",
    "Media": "^CNXMEDIA",
}


def _fetch_sector_strength(ticker: str) -> float:
    """
    Compute sector relative strength vs Nifty 50 over last 5 days.
    Returns a float: >0 means sector outperforming, <0 underperforming.
    """
    import yfinance as yf
    try:
        stock_info = yf.Ticker(ticker).info
        sector = stock_info.get("sector", "")
        idx_symbol = SECTOR_INDEX_MAP.get(sector)
        if not idx_symbol:
            return 0.0

        idx = yf.Ticker(idx_symbol)
        hist = idx.history(period="5d")
        if len(hist) < 2:
            return 0.0

        sector_ret = (float(hist["Close"].iloc[-1]) / float(hist["Close"].iloc[0]) - 1) * 100

        nifty = yf.Ticker("^NSEI")
        nh = nifty.history(period="5d")
        if len(nh) < 2:
            return 0.0
        nifty_ret = (float(nh["Close"].iloc[-1]) / float(nh["Close"].iloc[0]) - 1) * 100

        return round(sector_ret - nifty_ret, 4)
    except Exception:
        return 0.0


# --- Core model functions ---

def _build_target(df: pd.DataFrame, forward_bars: int = FORWARD_BARS) -> pd.Series:
    """Target = percentage return over the next N bars."""
    future_close = df["Close"].shift(-forward_bars)
    target = ((future_close - df["Close"]) / df["Close"]) * 100
    return target


def _add_market_context(df: pd.DataFrame, vix: dict, nifty: dict,
                        sector_strength: float = 0.0) -> pd.DataFrame:
    """Append market-level context features to every row."""
    df["vix_level"] = vix.get("vix_level", 15.0)
    df["vix_change_5d"] = vix.get("vix_change_5d", 0.0)
    trend_map = {"bullish": 1, "flat": 0, "bearish": -1}
    df["nifty_trend_dir"] = trend_map.get(nifty.get("trend", "flat"), 0)
    df["sector_strength"] = sector_strength
    return df


def _prepare_features(df: pd.DataFrame) -> tuple:
    """Select feature columns and return X matrix + available column names."""
    all_cols = FEATURE_COLS + MARKET_FEATURES
    available = [c for c in all_cols if c in df.columns]
    X = df[available].values.astype(np.float32)
    return X, available


def train_intraday_model(df: pd.DataFrame, vix: dict, nifty: dict,
                         sector_strength: float = 0.0) -> dict:
    """
    Train an XGBoost regressor on intraday data.
    Returns dict with model, scaler info, feature names, and metrics.
    """
    df = _add_market_context(df, vix, nifty, sector_strength)

    # Build target
    df["target"] = _build_target(df, FORWARD_BARS)

    # Drop rows where target is NaN (last FORWARD_BARS rows)
    df_clean = df.dropna(subset=["target"]).copy()

    if len(df_clean) < 100:
        raise ValueError(f"Insufficient data for training: {len(df_clean)} rows (need >=100)")

    X, feature_names = _prepare_features(df_clean)
    y = df_clean["target"].values.astype(np.float32)

    # Replace any remaining NaN/inf in features
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Time-series split: train on first 80%, test on last 20%
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    model = XGBRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        verbosity=0,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # Evaluate
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    rmse = float(np.sqrt(mse))

    # Directional accuracy (did we predict the right direction?)
    dir_correct = np.sum(np.sign(y_pred) == np.sign(y_test))
    dir_accuracy = float(dir_correct / len(y_test)) * 100 if len(y_test) > 0 else 0

    return {
        "model": model,
        "feature_names": feature_names,
        "rmse": round(rmse, 4),
        "dir_accuracy": round(dir_accuracy, 1),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
    }


def compute_confidence(expected_return: float, rmse: float,
                       dir_accuracy: float, regime_str: str) -> float:
    """
    Compute a confidence score (0-100) for the prediction.
    Factors: magnitude of expected return vs model RMSE,
    directional accuracy, and current market regime.
    """
    # Signal-to-noise ratio: how big is the predicted move vs model error
    snr = abs(expected_return) / rmse if rmse > 0 else 0
    snr_score = min(40, snr * 20)  # 0-40 points

    # Directional accuracy contribution
    dir_score = min(35, max(0, (dir_accuracy - 45) * 0.7))  # 0-35 points

    # Regime bonus/penalty
    regime_bonus = {
        "BULL_LOW_VOL": 15,
        "BULL_HIGH_VOL": 10,
        "SIDEWAYS": 0,
        "BEAR_HIGH_VOL": -5,
    }.get(regime_str, 5)

    # Return-direction bonus: predicted returns in the direction we'd trade
    dir_bonus = 10 if expected_return > 0.3 else (5 if expected_return > 0 else 0)

    confidence = snr_score + dir_score + regime_bonus + dir_bonus
    return round(max(0, min(100, confidence)), 1)


def intraday_predict(ticker: str) -> dict:
    """
    Full pipeline: fetch data -> add indicators -> add market context ->
    train XGBoost -> predict next bars -> return raw prediction data.
    Uses cache when available.
    """
    # 1. Fetch intraday data
    df = fetch_intraday_data(ticker, period="5d", interval="1m")
    df = add_intraday_indicators(df)

    if len(df) < 120:
        return {
            "ticker": ticker,
            "status": "insufficient_data",
            "message": f"Only {len(df)} bars available (need >=120)",
        }

    # 2. Fetch market context
    vix = fetch_india_vix()
    nifty = fetch_nifty_trend()
    sector_str = _fetch_sector_strength(ticker)

    # 3. Train model or use cache
    if _cache_valid(ticker):
        cached = _model_cache[ticker]
        model = cached["model"]
        feature_names = cached["feature_names"]
        result_metrics = {
            "rmse": cached["rmse"],
            "dir_accuracy": cached["dir_accuracy"],
            "train_samples": cached["train_samples"],
            "test_samples": cached["test_samples"],
        }
    else:
        try:
            result = train_intraday_model(df.copy(), vix, nifty, sector_str)
        except ValueError as e:
            return {"ticker": ticker, "status": "train_error", "message": str(e)}

        model = result["model"]
        feature_names = result["feature_names"]
        result_metrics = {
            "rmse": result["rmse"],
            "dir_accuracy": result["dir_accuracy"],
            "train_samples": result["train_samples"],
            "test_samples": result["test_samples"],
        }

        # Cache the trained model
        _model_cache[ticker] = {
            "model": model,
            "feature_names": feature_names,
            "timestamp": time.time(),
            **result_metrics,
        }

    # 4. Predict on latest bar
    df_latest = _add_market_context(df, vix, nifty, sector_str)
    X_latest, _ = _prepare_features(df_latest)
    X_latest = np.nan_to_num(X_latest, nan=0.0, posinf=0.0, neginf=0.0)

    # Predict for the last bar
    last_features = X_latest[-1:].reshape(1, -1)
    expected_return = float(model.predict(last_features)[0])

    # 5. Get current indicators for the signal
    last_row = df.iloc[-1]
    current_price = float(last_row["Close"])
    current_atr = float(last_row["ATR"])
    current_rsi = float(last_row["RSI"])
    current_supertrend_dir = int(last_row["Supertrend_Dir"])
    current_vwap = float(last_row["VWAP"])
    current_volume_ratio = float(last_row["volume_ratio"])

    # 6. Feature importances (top 5)
    importances = model.feature_importances_
    top_indices = np.argsort(importances)[-5:][::-1]
    top_features = [
        {"name": feature_names[i], "importance": round(float(importances[i]), 3)}
        for i in top_indices if i < len(feature_names)
    ]

    return {
        "ticker": ticker,
        "status": "ok",
        "expected_return_pct": round(expected_return, 4),
        "forward_bars": FORWARD_BARS,
        "current_price": round(current_price, 2),
        "current_atr": round(current_atr, 4),
        "current_rsi": round(current_rsi, 2),
        "supertrend_dir": current_supertrend_dir,
        "vwap": round(current_vwap, 2),
        "volume_ratio": round(current_volume_ratio, 2),
        "model_rmse": result_metrics["rmse"],
        "model_dir_accuracy": result_metrics["dir_accuracy"],
        "train_samples": result_metrics["train_samples"],
        "vix": vix,
        "nifty_trend": nifty,
        "sector_strength": sector_str,
        "top_features": top_features,
    }


# --- Full signal generator ---

def generate_intraday_signal(ticker: str) -> dict:
    """
    Full pipeline: predict -> detect regime -> compute dynamic SL/TP ->
    apply entry threshold -> return structured trading signal.

    Output example:
    {
        "action": "BUY",
        "ticker": "RELIANCE.NS",
        "entry_price": 2987.40,
        "sl_price": 2952.20, "sl_pct": -1.18,
        "tp1_price": 3024.60, "tp1_pct": 1.24,
        "tp2_price": 3057.80, "tp2_pct": 2.35,
        "confidence": 67.3,
        "expected_return_pct": 1.12,
        "regime": "BULL_LOW_VOL",
        ...
    }
    """
    # 1. Get raw prediction
    pred = intraday_predict(ticker)

    if pred.get("status") != "ok":
        return {
            "action": "SKIP",
            "ticker": ticker,
            "reason": pred.get("message", "Prediction failed"),
            "status": pred.get("status", "error"),
        }

    expected_return = pred["expected_return_pct"]
    current_price = pred["current_price"]
    current_atr = pred["current_atr"]

    # 2. Build stock-level indicators for regime detection
    stock_indicators = {
        "RSI": pred["current_rsi"],
        "price": current_price,
        "Supertrend_Dir": pred["supertrend_dir"],
        "MACD": 0,
        "MACD_Signal": 0,
    }

    # 3. Detect regime (uses VIX + Nifty + stock signals)
    regime_info = detect_market_regime(
        indicators=stock_indicators,
        vix=pred["vix"],
        nifty=pred["nifty_trend"],
    )
    regime = regime_info["regime"]
    entry_threshold = regime_info["entry_threshold"]
    min_confidence = regime_info["min_confidence"]

    # 4. Check IPO status
    ipo_info = detect_ipo_stock(ticker)
    is_ipo = ipo_info.get("is_ipo", False)

    # 5. Compute dynamic SL/TP
    levels = compute_dynamic_levels(current_price, current_atr, regime, is_ipo)

    # 6. Compute confidence
    confidence = compute_confidence(
        expected_return,
        pred["model_rmse"],
        pred["model_dir_accuracy"],
        regime,
    )

    # 7. Apply entry threshold
    if expected_return >= entry_threshold and confidence >= min_confidence:
        action = "BUY"
    elif expected_return > 0 and confidence >= min_confidence * 1.3:
        # Relaxed entry if confidence is very high
        action = "BUY"
    else:
        action = "WAIT"

    # Build reason string for WAIT
    reason = None
    if action == "WAIT":
        parts = []
        if expected_return < entry_threshold:
            parts.append(
                f"Expected return {expected_return:.2f}% < threshold {entry_threshold}%"
            )
        if confidence < min_confidence:
            parts.append(
                f"Confidence {confidence} < minimum {min_confidence}"
            )
        reason = "; ".join(parts) if parts else "Conditions not met"

    signal = {
        "action": action,
        "ticker": ticker,
        "entry_price": current_price,
        "sl_price": levels["sl_price"],
        "sl_pct": levels["sl_pct"],
        "tp1_price": levels["tp1_price"],
        "tp1_pct": levels["tp1_pct"],
        "tp2_price": levels["tp2_price"] if levels["include_tp2"] else None,
        "tp2_pct": levels["tp2_pct"] if levels["include_tp2"] else None,
        "confidence": confidence,
        "expected_return_pct": round(expected_return, 4),
        "regime": regime,
        "regime_details": regime_info,
        "is_ipo": is_ipo,
        "ipo_age_days": ipo_info.get("ipo_age_days"),
        "current_atr": pred["current_atr"],
        "current_rsi": pred["current_rsi"],
        "supertrend_dir": pred["supertrend_dir"],
        "vwap": pred["vwap"],
        "volume_ratio": pred["volume_ratio"],
        "sector_strength": pred.get("sector_strength", 0),
        "model_metrics": {
            "rmse": pred["model_rmse"],
            "dir_accuracy": pred["model_dir_accuracy"],
            "train_samples": pred["train_samples"],
        },
        "top_features": pred["top_features"],
        "vix": pred["vix"],
        "nifty_trend": pred["nifty_trend"],
    }

    if reason:
        signal["reason"] = reason

    return signal
