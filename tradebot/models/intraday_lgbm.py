"""
models/intraday_lgbm.py
LightGBM intraday classifier with SHAP explainability.
Trains on 5-min bar features, predicts bullish move probability.
"""
import logging
import numpy as np
import pandas as pd
import lightgbm as lgb
import shap
import mlflow
import mlflow.lightgbm
import joblib
from pathlib import Path
from features.technical import INTRADAY_FEATURE_COLS

log = logging.getLogger(__name__)
MODEL_PATH = Path("models/saved/lgbm_intraday.pkl")
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)


LGBM_PARAMS = {
    "objective":         "binary",
    "metric":            ["binary_logloss", "auc"],
    "is_unbalance":      True,
    "learning_rate":     0.05,
    "num_leaves":        63,
    "max_depth":         -1,
    "min_child_samples": 50,
    "feature_fraction":  0.8,
    "bagging_fraction":  0.8,
    "bagging_freq":      5,
    "lambda_l1":         0.1,
    "lambda_l2":         0.1,
    "verbose":           -1,
}


def _prepare_label(df: pd.DataFrame, horizon: int = 3, threshold: float = 0.3) -> pd.Series:
    """
    Binary label: 1 if close rises by >threshold% within `horizon` bars, else 0.
    """
    future_close = df["close"].shift(-horizon)
    ret = (future_close - df["close"]) / df["close"] * 100
    return (ret > threshold).astype(int)


def train(
    df: pd.DataFrame,
    val_df: pd.DataFrame | None = None,
    horizon: int = 3,
    label_threshold: float = 0.3,
    num_rounds: int = 1000,
) -> lgb.Booster:
    from features.technical import build_intraday_features

    df = build_intraday_features(df)
    df["label"] = _prepare_label(df, horizon, label_threshold)
    df.dropna(subset=INTRADAY_FEATURE_COLS + ["label"], inplace=True)

    feat_cols = [c for c in INTRADAY_FEATURE_COLS if c in df.columns]
    X_train = df[feat_cols].values
    y_train = df["label"].values

    dtrain = lgb.Dataset(X_train, label=y_train, feature_name=feat_cols)
    valid_sets = [dtrain]

    if val_df is not None:
        val_df = build_intraday_features(val_df)
        val_df["label"] = _prepare_label(val_df, horizon, label_threshold)
        val_df.dropna(subset=feat_cols + ["label"], inplace=True)
        dval = lgb.Dataset(val_df[feat_cols].values, label=val_df["label"].values, reference=dtrain)
        valid_sets.append(dval)

    with mlflow.start_run(run_name="lgbm_intraday_train"):
        mlflow.log_params(LGBM_PARAMS)
        mlflow.log_param("horizon_bars", horizon)
        mlflow.log_param("label_threshold_pct", label_threshold)

        model = lgb.train(
            LGBM_PARAMS,
            dtrain,
            num_boost_round=num_rounds,
            valid_sets=valid_sets,
            callbacks=[lgb.early_stopping(50, verbose=False),
                       lgb.log_evaluation(200)],
        )

        mlflow.log_metric("best_iteration", model.best_iteration)
        mlflow.lightgbm.log_model(model, "lgbm_intraday")

    joblib.dump({"model": model, "feature_cols": feat_cols}, MODEL_PATH)
    log.info("LightGBM intraday model saved → %s", MODEL_PATH)
    return model


def load() -> tuple[lgb.Booster, list[str]]:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"No saved model at {MODEL_PATH}. Run train() first.")
    bundle = joblib.load(MODEL_PATH)
    return bundle["model"], bundle["feature_cols"]


def predict_with_shap(model: lgb.Booster, feature_cols: list[str],
                      X_row: np.ndarray) -> tuple[float, str]:
    """
    Returns:
        prob    – float 0-1 (bullish probability)
        reason  – one-sentence SHAP explanation
    """
    prob = float(model.predict(X_row.reshape(1, -1))[0])

    explainer = shap.TreeExplainer(model)
    sv        = explainer.shap_values(X_row.reshape(1, -1))
    # For binary: sv may be list of two arrays or single array
    vals = sv[1][0] if isinstance(sv, list) else sv[0]

    top2_idx   = np.argsort(np.abs(vals))[-2:][::-1]
    top2_names = [feature_cols[i] for i in top2_idx]
    top2_dir   = ["↑" if vals[i] > 0 else "↓" for i in top2_idx]

    direction = "Bullish" if prob >= 0.5 else "Bearish"
    reason = (
        f"{direction} signal driven by "
        f"{top2_names[0]} ({top2_dir[0]}) "
        f"and {top2_names[1]} ({top2_dir[1]})."
    )
    return prob, reason


def predict_for_ticker(ticker_df_5min: pd.DataFrame) -> dict:
    """
    End-to-end: takes raw 5-min OHLCV → returns prediction dict.
    """
    from features.technical import build_intraday_features, INTRADAY_FEATURE_COLS
    model, feat_cols = load()
    df = build_intraday_features(ticker_df_5min)
    df.dropna(subset=[c for c in feat_cols if c in df.columns], inplace=True)

    if df.empty:
        return {"prob": 0.5, "reason": "Insufficient data", "confidence": 50.0}

    X = df.iloc[-1][[c for c in feat_cols if c in df.columns]].values.astype(float)
    prob, reason = predict_with_shap(model, feat_cols, X)

    return {
        "prob":       round(prob, 4),
        "direction":  "LONG" if prob >= 0.5 else "SHORT",
        "reason":     reason,
        "last_close": float(df["close"].iloc[-1]),
        "rsi":        float(df.get("RSI_14", pd.Series([50])).iloc[-1]),
        "vsr":        float(df.get("vsr", pd.Series([1.0])).iloc[-1]),
        "atr":        float(df.get("ATRr_14", pd.Series([0])).iloc[-1]),
        "vwap_dev":   float(df.get("vwap_dev_pct", pd.Series([0])).iloc[-1]),
    }
