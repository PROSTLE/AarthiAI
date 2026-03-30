"""
Enterprise ML ensemble: H2O.ai, DataRobot-style, Alteryx-style.
Provides 75% of final prediction blend (dominant signal source).
Quality-weighted: H2O 40% + DataRobot 40% + Alteryx 20%.
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

# Optional: H2O AutoML (pip install h2o)
H2O_AVAILABLE = False
try:
    import h2o
    from h2o.automl import H2OAutoML
    H2O_AVAILABLE = True
except ImportError:
    pass

# Optional: DataRobot API (pip install datarobot)
DATAROBOT_AVAILABLE = False
try:
    import datarobot as dr
    DATAROBOT_AVAILABLE = True
except ImportError:
    pass

FEATURE_COLS = ["Close", "SMA_20", "EMA_20", "RSI", "MACD", "Volume",
                "BB_Upper", "BB_Lower", "BB_Width", "ATR"]
PREDICT_DAYS = 5


def _build_tabular_dataset(df: pd.DataFrame, target_shift: int = PREDICT_DAYS):
    """Build tabular X, y for regression. Target = close at t+target_shift."""
    available = [c for c in FEATURE_COLS if c in df.columns]
    if len(available) < 2:
        available = ["Close"]

    df = df.dropna(subset=available)
    if len(df) < 80:
        return None, None, None

    # Add returns and volatility features
    df = df.copy()
    df["ret_1d"] = df["Close"].pct_change(1)
    df["ret_3d"] = df["Close"].pct_change(3)
    df["ret_5d"] = df["Close"].pct_change(5)
    df["ret_10d"] = df["Close"].pct_change(10)
    df["vol_5d"] = df["ret_1d"].rolling(5).std()
    df["vol_10d"] = df["ret_1d"].rolling(10).std()
    df["momentum_5d"] = df["Close"] / df["Close"].shift(5) - 1
    if "SMA_20" in df.columns:
        df["dist_sma20"] = (df["Close"] - df["SMA_20"]) / df["SMA_20"].replace(0, np.nan)
    if "SMA_50" in df.columns:
        df["dist_sma50"] = (df["Close"] - df["SMA_50"]) / df["SMA_50"].replace(0, np.nan)
    if "EMA_20" in df.columns:
        df["dist_ema20"] = (df["Close"] - df["EMA_20"]) / df["EMA_20"].replace(0, np.nan)

    feature_cols = [c for c in available + [
        "ret_1d", "ret_3d", "ret_5d", "ret_10d", "vol_5d", "vol_10d",
        "momentum_5d", "dist_sma20", "dist_sma50", "dist_ema20",
    ] if c in df.columns]
    df = df.dropna(subset=feature_cols)

    # Target: close price at t+target_shift
    df["target"] = df["Close"].shift(-target_shift)
    df = df.dropna(subset=["target"])

    if len(df) < 50:
        return None, None, None

    X = df[feature_cols].values.astype(np.float64)
    y = df["target"].values.astype(np.float64)
    return X, y, df[feature_cols]


def _quadratic_interpolate(current_price: float, pred_day3: float, pred_day5: float) -> list[float]:
    """
    Generate a 5-day curve using quadratic interpolation through
    (day0=current, day3=pred_day3, day5=pred_day5).
    Produces realistic acceleration instead of straight lines.
    """
    # Fit quadratic: p(t) = at^2 + bt + c through t=0,3,5
    # p(0) = current, p(3) = pred_day3, p(5) = pred_day5
    c = current_price
    # Solving: 9a + 3b = pred_day3 - c,  25a + 5b = pred_day5 - c
    d3 = pred_day3 - current_price
    d5 = pred_day5 - current_price
    # From linear algebra: a = (5*d3 - 3*d5) / (9*5 - 3*25) = (5*d3 - 3*d5) / (-30)
    denom = (9 * 5 - 3 * 25)  # = -30
    if denom == 0:
        denom = -30  # safety (always -30)
    a = (5 * d3 - 3 * d5) / denom
    b = (d3 - 9 * a) / 3 if abs(3) > 1e-9 else d5 / 5

    prices = []
    for t in range(1, PREDICT_DAYS + 1):
        p = a * t * t + b * t + c
        prices.append(round(p, 2))
    return prices


def _dual_target_predict(df, current_price, fit_fn):
    """
    Predict day-3 and day-5 targets separately, then produce a
    quadratic interpolated 5-day curve. Much more realistic than linear.
    fit_fn(X_train, y_train) -> model with .predict(X) method.
    """
    X3, y3, _ = _build_tabular_dataset(df, target_shift=3)
    X5, y5, _ = _build_tabular_dataset(df, target_shift=5)
    if X3 is None or X5 is None or len(X3) < 50 or len(X5) < 50:
        return None

    split3 = int(len(X3) * 0.85)
    split5 = int(len(X5) * 0.85)

    model3 = fit_fn(X3[:split3], y3[:split3])
    model5 = fit_fn(X5[:split5], y5[:split5])

    pred_day3 = float(model3.predict(X3[-1:])[0])
    pred_day5 = float(model5.predict(X5[-1:])[0])

    return _quadratic_interpolate(current_price, pred_day3, pred_day5)


def _predict_h2o_local(df: pd.DataFrame, current_price: float) -> list[float] | None:
    """H2O AutoML local prediction (fallback if h2o not installed uses sklearn)."""
    from sklearn.ensemble import GradientBoostingRegressor

    def make_model(X_train, y_train):
        m = GradientBoostingRegressor(
            n_estimators=120, max_depth=5, learning_rate=0.04,
            subsample=0.85, random_state=42,
        )
        m.fit(X_train, y_train)
        return m

    return _dual_target_predict(df, current_price, make_model)


def predict_h2o(df: pd.DataFrame, current_price: float) -> list[float] | None:
    """H2O.ai AutoML prediction. Uses H2O if available, else sklearn fallback."""
    if H2O_AVAILABLE:
        try:
            X, y, frame = _build_tabular_dataset(df)
            if X is None or len(X) < 80:
                return _predict_h2o_local(df, current_price)

            h2o.init(verbose=False)
            train_df = pd.DataFrame(X, columns=frame.columns)
            train_df["target"] = y
            hf = h2o.H2OFrame(train_df)
            x_cols = list(frame.columns)
            aml = H2OAutoML(max_models=5, max_runtime_secs=60, seed=42)
            aml.train(x=x_cols, y="target", training_frame=hf)

            last_row = pd.DataFrame(X[-1:], columns=x_cols)
            hf_pred = h2o.H2OFrame(last_row)
            pred = aml.predict(hf_pred)
            pred_day5 = float(pred.as_data_frame().iloc[0, 0])
            h2o.shutdown(prompt=False)

            # H2O only predicts day-5, so we use linear interpolation for now.
            # TODO: Implement dual-target for H2O if possible.
            return [round(current_price + (i / PREDICT_DAYS) * (pred_day5 - current_price), 2)
                    for i in range(1, PREDICT_DAYS + 1)]
        except Exception:
            pass
    return _predict_h2o_local(df, current_price)


def predict_datarobot(df: pd.DataFrame, current_price: float) -> list[float] | None:
    """
    DataRobot-style prediction. Uses DataRobot API if configured,
    else local XGBoost/RandomForest ensemble.
    """
    dr_url = os.environ.get("DATAROBOT_API_URL")
    dr_key = os.environ.get("DATAROBOT_API_TOKEN")
    deployment_id = os.environ.get("DATAROBOT_DEPLOYMENT_ID")

    if DATAROBOT_AVAILABLE and dr_url and dr_key and deployment_id:
        try:
            dr.Client(token=dr_key, endpoint=dr_url)
            X, y, frame = _build_tabular_dataset(df)
            if X is None:
                return None
            last_row = pd.DataFrame(X[-1:], columns=frame.columns)
            pred = dr.PredictionEndpoint.predict(deployment_id, last_row)
            pred_day5 = float(pred.loc[0, "prediction"])
            return [round(current_price + (i / PREDICT_DAYS) * (pred_day5 - current_price), 2)
                    for i in range(1, PREDICT_DAYS + 1)]
        except Exception:
            pass

    # Local DataRobot-style: diverse 3-model ensemble (RF + GBM + HistGBM)
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor

    def make_model(X_train, y_train):
        rf = RandomForestRegressor(n_estimators=150, max_depth=7, random_state=43)
        gbm = GradientBoostingRegressor(n_estimators=100, max_depth=5, learning_rate=0.04, random_state=44)
        hgbm = HistGradientBoostingRegressor(max_iter=120, max_depth=6, learning_rate=0.05, random_state=47)
        rf.fit(X_train, y_train)
        gbm.fit(X_train, y_train)
        hgbm.fit(X_train, y_train)

        class TripleEnsemble:
            def predict(self, X):
                return 0.35 * rf.predict(X) + 0.35 * gbm.predict(X) + 0.30 * hgbm.predict(X)
        return TripleEnsemble()

    return _dual_target_predict(df, current_price, make_model)


def predict_alteryx(df: pd.DataFrame, current_price: float) -> list[float] | None:
    """
    Alteryx-style prediction. Blends ExtraTrees + Ridge regression
    with dual-target (day-3 + day-5) quadratic interpolation.
    """
    _scaler = StandardScaler()

    def make_model(X_train, y_train):
        X_train_scaled = _scaler.fit_transform(X_train)
        et = ExtraTreesRegressor(n_estimators=120, max_depth=8, random_state=45)
        ridge = Ridge(alpha=1.0)
        et.fit(X_train, y_train)
        ridge.fit(X_train_scaled, y_train)

        class TreeLinearBlend:
            def predict(self, X):
                X_s = _scaler.transform(X)
                return 0.6 * et.predict(X) + 0.4 * ridge.predict(X_s)
        return TreeLinearBlend()

    return _dual_target_predict(df, current_price, make_model)


def get_enterprise_predictions(
    df: pd.DataFrame,
    current_price: float,
) -> tuple[list[float] | None, list[float] | None, list[float] | None]:
    """Return (h2o_pred, datarobot_pred, alteryx_pred). Any may be None on failure."""
    h2o_p = predict_h2o(df, current_price)
    dr_p = predict_datarobot(df, current_price)
    alt_p = predict_alteryx(df, current_price)
    return h2o_p, dr_p, alt_p


# Quality weights: H2O and DataRobot are stronger models, Alteryx is supplementary
_MODEL_WEIGHTS = {
    "h2o": 0.40,
    "datarobot": 0.40,
    "alteryx": 0.20,
}


def blend_enterprise_predictions(
    h2o_pred: list[float] | None,
    datarobot_pred: list[float] | None,
    alteryx_pred: list[float] | None,
) -> list[float] | None:
    """
    Blend H2O, DataRobot, Alteryx with quality-based weights (40/40/20).
    If one model is missing, redistribute its weight proportionally.
    Returns None if no models succeeded.
    """
    available = []
    if h2o_pred is not None and len(h2o_pred) == PREDICT_DAYS:
        available.append(("h2o", h2o_pred))
    if datarobot_pred is not None and len(datarobot_pred) == PREDICT_DAYS:
        available.append(("datarobot", datarobot_pred))
    if alteryx_pred is not None and len(alteryx_pred) == PREDICT_DAYS:
        available.append(("alteryx", alteryx_pred))

    if not available:
        return None
    if len(available) == 1:
        return available[0][1]

    # Normalize weights for available models
    raw_weights = {name: _MODEL_WEIGHTS[name] for name, _ in available}
    total_w = sum(raw_weights.values())
    norm_weights = {name: w / total_w for name, w in raw_weights.items()}

    blended = []
    for i in range(PREDICT_DAYS):
        val = sum(norm_weights[name] * pred[i] for name, pred in available)
        blended.append(round(val, 2))
    return blended
