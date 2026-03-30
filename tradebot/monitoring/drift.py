"""
monitoring/drift.py
Evidently drift detection + MLflow logging.
Runs weekly on Friday EOD via eod_model_updater DAG.
"""
import logging
import pandas as pd
from pathlib import Path
from datetime import date

log = logging.getLogger(__name__)
REPORTS_DIR = Path("monitoring/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def run_weekly_drift_check(
    baseline_df: pd.DataFrame,
    current_df: pd.DataFrame,
    label_col: str = "hit_target",
) -> dict:
    """
    Compares feature distributions baseline vs current week.
    Logs results to MLflow, saves HTML report.
    Returns dict with drift_detected flag.
    """
    import mlflow
    from evidently.report import Report
    from evidently.metric_preset import DataDriftPreset, TargetDriftPreset
    from evidently.pipeline.column_mapping import ColumnMapping

    col_map = ColumnMapping(target=label_col)
    report  = Report(metrics=[DataDriftPreset(), TargetDriftPreset()])

    try:
        report.run(
            reference_data=baseline_df,
            current_data=current_df,
            column_mapping=col_map,
        )
        result = report.as_dict()

        drift_detected = result["metrics"][0]["result"].get("dataset_drift", False)
        n_drifted      = result["metrics"][0]["result"].get("number_of_drifted_columns", 0)

        report_path = REPORTS_DIR / f"drift_{date.today().isoformat()}.html"
        report.save_html(str(report_path))

        with mlflow.start_run(run_name=f"drift_check_{date.today().isoformat()}"):
            mlflow.log_metric("dataset_drift",          int(drift_detected))
            mlflow.log_metric("drifted_features_count", n_drifted)
            mlflow.log_artifact(str(report_path))

        # Flag in Redis for conditional retrain
        if drift_detected:
            import redis
            from config import SECRETS
            r = redis.Redis(
                host=SECRETS.get("redis", {}).get("host", "localhost"),
                port=SECRETS.get("redis", {}).get("port", 6379),
                decode_responses=True,
            )
            r.set(f"drift_detected:{date.today().isoformat()}", "1", ex=86400)

        log.info(
            "Drift check complete. Detected=%s, Drifted columns=%d",
            drift_detected, n_drifted,
        )
        return {
            "drift_detected": drift_detected,
            "drifted_columns": n_drifted,
            "report_path": str(report_path),
        }

    except Exception as e:
        log.error("Drift detection failed: %s", e)
        return {"drift_detected": False, "error": str(e)}


def log_prediction_outcome(
    ticker: str,
    features: dict,
    prediction: float,
    confidence: float,
    actual_outcome: int,   # 1 = hit target, 0 = hit stop, -1 = expired
) -> None:
    """
    Logs every prediction with ground truth to MLflow.
    Builds the growing truth dataset for model retraining.
    """
    import mlflow
    with mlflow.start_run(run_name=f"prediction_{ticker}_{date.today().isoformat()}"):
        mlflow.log_param("ticker",     ticker)
        mlflow.log_param("date",       str(date.today()))
        mlflow.log_metric("prediction",    prediction)
        mlflow.log_metric("confidence",    confidence)
        mlflow.log_metric("actual_outcome", actual_outcome)
        for k, v in features.items():
            try:
                mlflow.log_metric(f"feat_{k}", float(v))
            except (TypeError, ValueError):
                pass
