"""
models/swing_xgb.py
XGBoost swing trade regressor: predicts 10-day forward return.
"""
import numpy as np
import pandas as pd
import xgboost as xgb
import shap
import mlflow
import mlflow.xgboost
import joblib
from pathlib import Path

MODEL_PATH = Path("models/saved/xgb_swing.pkl")
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

SWING_PARAMS = {
    "tree_method":       "hist",
    "n_estimators":      600,
    "learning_rate":     0.04,
    "max_depth":         5,
    "subsample":         0.8,
    "colsample_bytree":  0.8,
    "objective":         "reg:squarederror",
    "eval_metric":       "rmse",
    "early_stopping_rounds": 50,
    "random_state":      42,
    "verbosity":         0,
}

SWING_FEATURE_COLS = [
    "RSI_14", "MACD_12_26_9", "MACDh_12_26_9", "ATRr_14",
    "bb_width", "bb_squeeze", "ema_cross_bull_daily", "trend_valid",
    "obv_slope", "bb_breakout_long", "rel_strength_vs_sector",
    "volume_ratio_20d",
]


def _prepare_target(df: pd.DataFrame, horizon: int = 10) -> pd.Series:
    """10-day forward % return."""
    return ((df["close"].shift(-horizon) - df["close"]) / df["close"] * 100).fillna(0)


def train(df: pd.DataFrame, val_df: pd.DataFrame | None = None, horizon: int = 10):
    from features.technical import build_swing_features
    df = build_swing_features(df)
    df["target"] = _prepare_target(df, horizon)
    df.dropna(inplace=True)

    feat_cols = [c for c in SWING_FEATURE_COLS if c in df.columns]
    X_train, y_train = df[feat_cols].values, df["target"].values

    eval_set = [(X_train, y_train)]
    if val_df is not None:
        val_df = build_swing_features(val_df)
        val_df["target"] = _prepare_target(val_df, horizon)
        val_df.dropna(inplace=True)
        eval_set.append((val_df[feat_cols].values, val_df["target"].values))

    model = xgb.XGBRegressor(**SWING_PARAMS)

    with mlflow.start_run(run_name="xgb_swing_train"):
        mlflow.log_params(SWING_PARAMS)
        model.fit(X_train, y_train, eval_set=eval_set, verbose=False)
        mlflow.xgboost.log_model(model, "xgb_swing")

    joblib.dump({"model": model, "feature_cols": feat_cols}, MODEL_PATH)
    return model


def load() -> tuple[xgb.XGBRegressor, list[str]]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError("No swing model. Run train() first.")
    bundle = joblib.load(MODEL_PATH)
    return bundle["model"], bundle["feature_cols"]


def predict_with_shap(model, feature_cols: list[str], X_row: np.ndarray) -> tuple[float, str]:
    forecast_10d = float(model.predict(X_row.reshape(1, -1))[0])

    explainer = shap.TreeExplainer(model)
    vals      = explainer.shap_values(X_row.reshape(1, -1))[0]
    top2_idx  = np.argsort(np.abs(vals))[-2:][::-1]
    top2_names = [feature_cols[i] for i in top2_idx]
    top2_dir   = ["↑" if vals[i] > 0 else "↓" for i in top2_idx]

    reason = (
        f"{'Bullish' if forecast_10d > 0 else 'Bearish'} swing: "
        f"{top2_names[0]} ({top2_dir[0]}) "
        f"and {top2_names[1]} ({top2_dir[1]}) are primary drivers."
    )
    return round(forecast_10d, 3), reason
