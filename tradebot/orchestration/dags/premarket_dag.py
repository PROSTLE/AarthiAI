"""
orchestration/dags/premarket_dag.py
Three Airflow DAGs:
 1. premarket_pipeline    — 9:00 AM IST (fetch context)
 2. market_open_scanner  — 9:15 AM IST (generate + execute signals)
 3. eod_model_updater    — 4:00 PM IST  (log outcomes, drift check, retrain)
"""
import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator

IST = pendulum.timezone("Asia/Kolkata")


# ════════════════════════════════════════════════════════════════════════════
# DAG 1 — PREMARKET PIPELINE  (9:00 AM IST)
# ════════════════════════════════════════════════════════════════════════════

def _fetch_global_cues(**ctx):
    from ingestion.nse_data import get_global_cues
    cues = get_global_cues()
    ctx["ti"].xcom_push(key="global_cues", value=cues)

def _fetch_fii_dii(**ctx):
    from ingestion.nse_data import get_fii_dii
    data = get_fii_dii()
    ctx["ti"].xcom_push(key="fii_dii", value=data)

def _fetch_options_pcr(**ctx):
    from ingestion.nse_data import get_options_pcr
    pcr = get_options_pcr("NIFTY")
    ctx["ti"].xcom_push(key="nifty_pcr", value=pcr)

def _fetch_sector_momentum(**ctx):
    from ingestion.nse_data import get_sector_momentum
    mom = get_sector_momentum(days=5)
    ctx["ti"].xcom_push(key="sector_momentum", value=mom)

def _fetch_news_score(**ctx):
    from ingestion.nse_data import get_news_headlines
    headlines = get_news_headlines()
    ctx["ti"].xcom_push(key="headlines", value=headlines)

def _build_premarket_context(**ctx):
    import redis, json
    from datetime import date
    ti = ctx["ti"]
    context = {
        "global_cues":      ti.xcom_pull(key="global_cues"),
        "fii":              ti.xcom_pull(key="fii_dii"),
        "nifty_pcr":        ti.xcom_pull(key="nifty_pcr"),
        "sector_momentum":  ti.xcom_pull(key="sector_momentum"),
        "headlines":        ti.xcom_pull(key="headlines"),
    }
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.set(f"premarket:{date.today().isoformat()}", json.dumps(context), ex=86400)


with DAG(
    dag_id="premarket_pipeline",
    start_date=pendulum.datetime(2024, 1, 1, tz=IST),
    schedule="0 9 * * MON-FRI",
    catchup=False,
    tags=["tradebot", "premarket"],
    description="Fetch global cues, FII/DII, PCR, sector momentum, and news at 9:00 AM IST",
) as premarket_dag:

    t_gcues  = PythonOperator(task_id="fetch_global_cues",    python_callable=_fetch_global_cues)
    t_fii    = PythonOperator(task_id="fetch_fii_dii",        python_callable=_fetch_fii_dii)
    t_pcr    = PythonOperator(task_id="fetch_options_pcr",    python_callable=_fetch_options_pcr)
    t_mom    = PythonOperator(task_id="fetch_sector_momentum", python_callable=_fetch_sector_momentum)
    t_news   = PythonOperator(task_id="fetch_news_score",     python_callable=_fetch_news_score)
    t_ctx    = PythonOperator(task_id="build_context",        python_callable=_build_premarket_context)

    [t_gcues, t_fii, t_pcr, t_mom, t_news] >> t_ctx


# ════════════════════════════════════════════════════════════════════════════
# DAG 2 — MARKET OPEN SCANNER  (9:15 AM IST)
# ════════════════════════════════════════════════════════════════════════════

def _is_market_day(**ctx):
    """Skip on NSE holidays (simple weekday check — extend with holiday calendar)."""
    import pendulum
    return pendulum.now(IST).day_of_week not in (5, 6)  # Sat=5, Sun=6

def _rank_and_signal(**ctx):
    import redis, json
    from datetime import date
    from signals.signal_engine import run_premarket_scan

    r   = redis.Redis(host="localhost", port=6379, decode_responses=True)
    raw = r.get(f"premarket:{date.today().isoformat()}")
    if not raw:
        raise ValueError("Premarket context not found — premarket_pipeline may not have run")

    context = json.loads(raw)
    signals = run_premarket_scan(context)
    ctx["ti"].xcom_push(key="signals", value=signals)

def _publish_brief(**ctx):
    import redis
    from datetime import date
    from signals.brief_generator import generate_brief, generate_brief_json
    from behavioral.mood import get_trade_mode

    ti       = ctx["ti"]
    signals  = ti.xcom_pull(key="signals")
    user_id  = "default"
    mode     = get_trade_mode(user_id, 100_000)

    brief_text = generate_brief(signals, mode)
    brief_json = generate_brief_json(signals, mode)

    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    today = str(date.today())
    r.set(f"signals:{today}",          __import__("json").dumps(brief_json), ex=86400)
    r.set(f"brief:{user_id}:{today}",  brief_text,                           ex=86400)

def _execute_autotrade(**ctx):
    from signals.brief_generator import generate_brief_json
    from behavioral.mood import get_trade_mode, get_mood, Mood
    from config import CONFIDENCE

    ti      = ctx["ti"]
    signals = ti.xcom_pull(key="signals")
    user_id = "default"
    mood    = get_mood(user_id)

    if mood == Mood.OUT:
        return   # No AutoTrade today

    mode            = get_trade_mode(user_id, 100_000)
    if not mode.auto_entry:
        return   # Supervised mode — user approves manually

    threshold   = mode.confidence_threshold
    picks       = signals.get("intraday_picks", [])
    eligible    = [p for p in picks if p["confidence"] >= threshold]

    for pick in eligible[:mode.max_trades]:
        from execution.order_manager import execute_trade
        execute_trade(
            ticker=pick["ticker"],
            signal=pick["signal"],
            entry_price=pick["entry"],
            stop_price=pick["stop"],
            target_price=pick["target"],
            capital=100_000,
            trade_type="intraday",
            size_multiplier=mode.position_size_multiplier,
            user_id=user_id,
        )


with DAG(
    dag_id="market_open_scanner",
    start_date=pendulum.datetime(2024, 1, 1, tz=IST),
    schedule="15 9 * * MON-FRI",
    catchup=False,
    tags=["tradebot", "signals"],
    description="Score + rank stocks, generate signals, execute AutoTrade at 9:15 AM IST",
) as scanner_dag:

    t_market_check = ShortCircuitOperator(task_id="is_market_day", python_callable=_is_market_day)
    t_signal       = PythonOperator(task_id="rank_and_signal",     python_callable=_rank_and_signal)
    t_brief        = PythonOperator(task_id="publish_brief",        python_callable=_publish_brief)
    t_execute      = PythonOperator(task_id="execute_autotrade",    python_callable=_execute_autotrade)

    t_market_check >> t_signal >> [t_brief, t_execute]


# ════════════════════════════════════════════════════════════════════════════
# DAG 3 — EOD MODEL UPDATER  (4:00 PM IST)
# ════════════════════════════════════════════════════════════════════════════

def _log_trade_outcomes(**ctx):
    """Compare today's signals vs actual close price and write outcomes to DB."""
    import redis, json
    from datetime import date
    import yfinance as yf

    r   = redis.Redis(host="localhost", port=6379, decode_responses=True)
    raw = r.get(f"signals:{date.today().isoformat()}")
    if not raw:
        return

    signals = json.loads(raw)
    outcomes = []
    for pick in signals.get("top_signals", []):
        try:
            hist  = yf.Ticker(pick["ticker"]).history(period="1d", interval="1m")
            close = float(hist["Close"].iloc[-1]) if not hist.empty else pick["entry"]
            hit_target = close >= pick["target"] if pick["signal"] == "LONG" else close <= pick["target"]
            hit_stop   = close <= pick["stop"]   if pick["signal"] == "LONG" else close >= pick["stop"]
            outcomes.append({
                "ticker":      pick["ticker"],
                "signal":      pick["signal"],
                "entry":       pick["entry"],
                "close":       round(close, 2),
                "target":      pick["target"],
                "stop":        pick["stop"],
                "hit_target":  hit_target,
                "hit_stop":    hit_stop,
                "confidence":  pick["confidence"],
                "date":        str(date.today()),
            })
        except Exception:
            continue

    r.set(f"outcomes:{date.today().isoformat()}", json.dumps(outcomes), ex=30 * 86400)

def _run_drift_detection(**ctx):
    from monitoring.drift import run_weekly_drift_check
    import pandas as pd, json, redis
    from datetime import date, timedelta

    r = redis.Redis(host="localhost", port=6379, decode_responses=True)

    # Collect last 7 days of outcomes for drift check
    records = []
    for i in range(7):
        d   = str((date.today() - timedelta(days=i)).isoformat())
        raw = r.get(f"outcomes:{d}")
        if raw:
            records.extend(json.loads(raw))

    if len(records) < 10:
        return  # Not enough data

    df = pd.DataFrame(records)
    baseline = df.iloc[:len(df)//2]
    current  = df.iloc[len(df)//2:]
    run_weekly_drift_check(baseline, current)

def _conditional_retrain(**ctx):
    """Retrain LightGBM only if drift detected."""
    import redis
    from datetime import date, timedelta
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    drift_key = f"drift_detected:{date.today().isoformat()}"
    if r.get(drift_key) != "1":
        return  # No drift — skip retrain

    # In production: pull historical data and retrain
    import yfinance as yf, pandas as pd
    from models.intraday_lgbm import train as train_lgbm
    # Placeholder — real implementation loads from PostgreSQL
    pass

def _update_user_profiles(**ctx):
    """Weekly behavioral model retrain (runs on Fridays)."""
    import pendulum
    if pendulum.now(IST).day_of_week != 4:  # 4=Friday
        return
    # Load interaction logs from DB and retrain
    # from behavioral.profiler import train_behavioral_models
    pass


with DAG(
    dag_id="eod_model_updater",
    start_date=pendulum.datetime(2024, 1, 1, tz=IST),
    schedule="0 16 * * MON-FRI",
    catchup=False,
    tags=["tradebot", "ml", "eod"],
    description="Log outcomes, drift detection, conditional retrain at 4:00 PM IST",
) as eod_dag:

    e_outcomes  = PythonOperator(task_id="log_trade_outcomes",   python_callable=_log_trade_outcomes)
    e_drift     = PythonOperator(task_id="drift_detection",      python_callable=_run_drift_detection)
    e_retrain   = PythonOperator(task_id="conditional_retrain",  python_callable=_conditional_retrain)
    e_profiles  = PythonOperator(task_id="update_user_profiles", python_callable=_update_user_profiles)

    e_outcomes >> e_drift >> e_retrain
    e_outcomes >> e_profiles
