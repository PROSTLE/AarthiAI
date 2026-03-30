import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.preprocessing import MinMaxScaler
from datetime import datetime, timedelta
import time
import hashlib

from enterprise_models import (
    get_enterprise_predictions,
    blend_enterprise_predictions,
)

FEATURE_COLS = ["Close", "SMA_20", "EMA_20", "RSI", "MACD", "Volume",
                "BB_Upper", "BB_Lower", "BB_Width", "ATR"]
LOOK_BACK = 60       # Number of historical days used as LSTM input window
PREDICT_DAYS = 5     # Number of days to forecast

# ── 5-Factor Prediction Weights ────────────────────────────────────────────
# IMPORTANT: LLM weight reduced 32%→13% because Gemini does not have
# real-time NSE price data. It makes qualitative assessments, not 
# quantitative ones. LSTM is now dominant for price trajectory.
# Technical weight raised: RSI/MACD are grounded to actual candlestick data.
W_LSTM         = 0.30   # Day-by-day price shape  (was 0.15)
W_ENTERPRISE   = 0.25   # H2O + DataRobot + Alteryx magnitude
W_TECHNICAL    = 0.20   # RSI / MACD / SMA trend scoring  (was 0.13)
W_SENTIMENT    = 0.12   # FinBERT + VADER news sentiment  (was 0.15)
W_LLM          = 0.13   # Google Gemini market analysis   (was 0.32)

# Max price adjustment from directional factors (% of price)
# Reduced 3.0→1.2: prevents LLM/Sentiment from overriding quantitative signal
MAX_DIRECTIONAL_IMPACT_PCT = 1.2

# Max single-day move as % of previous-day price (realistic large-cap cap)
# TCS, RELIANCE etc rarely move >2.5% in a single session without news
MAX_DAILY_MOVE_PCT = 2.5

# Live-price anchor tolerance: Day 1 must be within this % of the actual
# current traded price. Prevents gap-up/gap-down hallucinations.
DAY1_ANCHOR_PCT = 1.8

# Drawdown dampening: when recent 2-day drop > 3%, reduce rubber-band bounce
DRAWDOWN_THRESHOLD_PCT = 2.9
DAMPER_STRENGTH = 0.45  # moderate damping; too high creates flatline

# Minimum daily price movement as % of price (prevents dead-pulse flat lines)
MIN_DAILY_MOVE_PCT = 0.15

# Deterministic seed for reproducibility
RANDOM_SEED = 42

# ── Prediction cache ─────────────────────────────────────
# Cache predictions keyed by (ticker_hash, last_close_price_rounded).
# TTL = 15 minutes. Only re-trains when market data actually changes.
CACHE_TTL_SECONDS = 15 * 60  # 15 minutes
_prediction_cache = {}  # {cache_key: {"result": ..., "timestamp": ...}}


def _make_cache_key(df: pd.DataFrame) -> str:
    """Build a stable cache key. Uses last close rounded to integer + date + data length.
    This prevents re-training on every intraday tick while still invalidating
    when a new trading day's data arrives."""
    close = df["Close"].values
    # Round last close to nearest integer — small intraday changes don't bust cache
    last_close_rounded = round(float(close[-1]))
    # Use the date of the last data point if available
    if "Date" in df.columns:
        last_date = str(df["Date"].iloc[-1])[:10]
    else:
        last_date = datetime.now().strftime("%Y-%m-%d")
    fingerprint = f"{len(df)}_{last_close_rounded}_{last_date}"
    return hashlib.md5(fingerprint.encode()).hexdigest()


def _get_cached(key: str) -> dict | None:
    """Return cached prediction if still valid, else None."""
    entry = _prediction_cache.get(key)
    if entry and (time.time() - entry["timestamp"]) < CACHE_TTL_SECONDS:
        return entry["result"]
    return None


def _set_cache(key: str, result: dict):
    """Store prediction in cache."""
    _prediction_cache[key] = {"result": result, "timestamp": time.time()}
    # Evict old entries (keep max 20)
    if len(_prediction_cache) > 20:
        oldest = min(_prediction_cache, key=lambda k: _prediction_cache[k]["timestamp"])
        del _prediction_cache[oldest]


def _set_deterministic_seeds():
    """Set all random seeds for reproducible LSTM training."""
    torch.manual_seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(RANDOM_SEED)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def _apply_drawdown_dampening(
    predicted_prices: list[float],
    current_price: float,
    df: pd.DataFrame,
) -> list[float]:
    if len(df) < 3 or len(predicted_prices) != PREDICT_DAYS:
        return predicted_prices

    close = df["Close"].values
    ret_1d = (float(close[-1]) / float(close[-2]) - 1) * 100 if len(close) >= 2 and close[-2] else 0
    ret_2d = (float(close[-1]) / float(close[-3]) - 1) * 100 if len(close) >= 3 and close[-3] else 0
    worst_return = min(ret_1d, ret_2d)

    if worst_return > -DRAWDOWN_THRESHOLD_PCT:
        return predicted_prices

    day1_pred = predicted_prices[0]
    if day1_pred <= current_price:
        return predicted_prices

    recent_slope = worst_return / 100
    damped = []
    for i in range(PREDICT_DAYS):
        t = (i + 1) / PREDICT_DAYS
        momentum_factor = recent_slope * 0.3 * (1 - t)
        recovery_factor = t * (predicted_prices[-1] - current_price) / current_price * 0.5
        slope_val = current_price * (1 + momentum_factor + recovery_factor)
        blended = (1 - DAMPER_STRENGTH) * predicted_prices[i] + DAMPER_STRENGTH * slope_val
        damped.append(round(blended, 2))
    return damped


def _anchor_to_live_price(
    predicted_prices: list[float],
    live_price: float,
) -> list[float]:
    """
    Hard-anchor Day 1 within DAY1_ANCHOR_PCT of the actual live traded price.
    This prevents the model from predicting a ₹400 gap-up when the stock is
    actually trading at ₹2365 right now.
    The remaining days are scaled proportionally so the curve shape is preserved.
    """
    if not predicted_prices or live_price <= 0:
        return predicted_prices

    day1 = predicted_prices[0]
    max_deviation = live_price * DAY1_ANCHOR_PCT / 100.0

    if abs(day1 - live_price) <= max_deviation:
        return predicted_prices  # Already within tolerance — no adjustment needed

    # Pull Day 1 back to the edge of the tolerance band
    if day1 > live_price:
        anchored_day1 = live_price + max_deviation
    else:
        anchored_day1 = live_price - max_deviation

    # Scale remaining days to preserve the curve shape
    shift = anchored_day1 - day1
    result = []
    for i, p in enumerate(predicted_prices):
        # Shift fades over the 5 days: Day 1 gets full shift, Day 5 gets 20%
        fade = 1.0 - (i * 0.15)  # 1.0, 0.85, 0.70, 0.55, 0.40
        result.append(round(p + shift * fade, 2))
    return result


def _cap_daily_moves(
    predicted_prices: list[float],
    current_price: float,
) -> list[float]:
    """
    Enforce a per-day move cap of MAX_DAILY_MOVE_PCT.
    Large-cap Indian stocks (TCS, RELIANCE, HDFC, etc.) almost never move
    more than 2.5% in a single session without a major event.
    Caps both upside and downside to prevent fantasy trajectories.
    """
    result = []
    prev = current_price
    for i, p in enumerate(predicted_prices):
        max_move = prev * MAX_DAILY_MOVE_PCT / 100.0
        if p > prev + max_move:
            p = prev + max_move
        elif p < prev - max_move:
            p = prev - max_move
        result.append(round(p, 2))
        prev = p
    return result



def _add_minimum_volatility(
    predicted_prices: list[float],
    current_price: float,
    df: pd.DataFrame,
) -> list[float]:
    """
    Prevent 'dead pulse' flat lines by adding natural wave-like fluctuation.
    Uses recent historical daily return PATTERN (up/down sequence) as a
    template for realistic micro-movements, instead of pushing all days
    in the same direction (which creates a straight line).
    """
    if len(predicted_prices) != PREDICT_DAYS:
        return predicted_prices

    close = df["Close"].values
    if len(close) >= 6:
        daily_rets = np.diff(close[-6:]) / close[-6:-1]
        avg_daily_vol = max(float(np.std(daily_rets)), MIN_DAILY_MOVE_PCT / 100)
        # Use the SIGN pattern of recent returns for natural up/down alternation
        ret_signs = np.sign(daily_rets).tolist()
    else:
        avg_daily_vol = MIN_DAILY_MOVE_PCT / 100
        ret_signs = [1, -1, 1, -1, 1]  # default alternating

    min_move = current_price * max(MIN_DAILY_MOVE_PCT / 100, avg_daily_vol * 0.3)

    result = list(predicted_prices)
    prev = current_price
    for i in range(len(result)):
        diff = abs(result[i] - prev)
        if diff < min_move:
            # Use historical sign pattern for natural alternation
            sign_idx = i % len(ret_signs)
            direction = ret_signs[sign_idx] if ret_signs[sign_idx] != 0 else 1
            # Scale the jitter — smaller near endpoints, larger in middle
            middle_factor = 1.0 + 0.5 * (1 - abs(2 * i / (PREDICT_DAYS - 1) - 1))
            result[i] = round(prev + direction * min_move * middle_factor, 2)
        prev = result[i]

    # Preserve the original endpoint — scale back so day-5 matches
    if abs(result[-1] - predicted_prices[-1]) > 0.01:
        shift = predicted_prices[-1] - result[-1]
        # Gradually apply the shift more toward the end
        for i in range(len(result)):
            t = (i + 1) / len(result)
            result[i] = round(result[i] + shift * t, 2)

    return result



class StockLSTM(nn.Module):
    def __init__(self, input_size: int = 10, hidden_size: int = 128,
                 num_layers: int = 3, output_size: int = 5, dropout: float = 0.3):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size, hidden_size, num_layers,
            batch_first=True, dropout=dropout if num_layers > 1 else 0.0,
        )

        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size // 2, output_size),
        )

    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size, device=x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size, device=x.device)
        out, _ = self.lstm(x, (h0, c0))
        out = self.head(out[:, -1, :])
        return out


def _prepare_features(df: pd.DataFrame):
    available = [c for c in FEATURE_COLS if c in df.columns]
    if len(available) < 2:
        available = ["Close"]

    features = df[available].values.astype(np.float32)
    close = df["Close"].values.astype(np.float32)
    return features, close, len(available)


def _prepare_data(features: np.ndarray, close_col_idx: int = 0):
    n_samples = len(features)
    split = int(n_samples * 0.85)

    scaler = MinMaxScaler()
    scaler.fit(features[:split])

    scaled = scaler.transform(features)

    X, y = [], []
    for i in range(LOOK_BACK, len(scaled) - PREDICT_DAYS):
        X.append(scaled[i - LOOK_BACK:i])
        y.append(scaled[i:i + PREDICT_DAYS, close_col_idx])

    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.float32)

    adj_split = split - LOOK_BACK
    adj_split = max(1, min(adj_split, len(X) - 1))

    return X, y, scaler, adj_split



def detect_crisis_mode(sentiment_score: float, atr_pct: float, vix_level: float) -> tuple[bool, str]:
    """
    Detect if the market is in 'Crisis Mode' based on sentiment and volatility.
    Triggers:
    1. Severe negative sentiment (<-0.5)
    2. High ATR (>3.0%) indicating panic
    3. High VIX (>24) indicating fear
    """
    reasons = []
    if sentiment_score <= -0.5:
        reasons.append("Severe Negative Sentiment")
    if atr_pct > 3.0:
        reasons.append("High Volatility (ATR > 3%)")
    if vix_level > 24.0:
        reasons.append("High Fear (VIX > 24)")
    
    if reasons:
        return True, ", ".join(reasons)
    return False, ""


def train_and_predict(
    df: pd.DataFrame,
    epochs: int = 35,
    lr: float = 0.001,
    batch_size: int = 32,
    patience: int = 7,
    sentiment_score: float = 0.0,
    technical_score: float = 0.0,
    llm_score: float = 0.0,
    sentiment_label: str = "neutral",
    technical_direction: str = "neutral",
    llm_direction: str = "neutral",
    atr_pct: float = 0.0,
    vix_level: float = 0.0,
):
    # ── Cache check: return existing prediction if data hasn't changed ──
    # Note: If crisis condition changes within TTL, cache might be stale, 
    # but 15 min TTL is acceptable trade-off vs retraining.
    cache_key = _make_cache_key(df)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # ── Set deterministic seeds for reproducibility ──
    _set_deterministic_seeds()

    # ── Crisis Mode Detection ──
    is_crisis, crisis_reason = detect_crisis_mode(sentiment_score, atr_pct, vix_level)

    # Dynamic weighting — in crisis, emphasise sentiment + LLM more
    # but LLM is still capped to prevent hallucinations
    if is_crisis:
        w_lstm = 0.25
        w_enterprise = 0.20
        w_technical = 0.18
        w_sentiment = 0.20
        w_llm = 0.17
    else:
        w_lstm = W_LSTM
        w_enterprise = W_ENTERPRISE
        w_technical = W_TECHNICAL
        w_sentiment = W_SENTIMENT
        w_llm = W_LLM

    features, close, n_features = _prepare_features(df)
    X, y, scaler, split = _prepare_data(features)

    X_train, y_train = X[:split], y[:split]
    X_test, y_test = X[split:], y[split:]

    X_train_t = torch.tensor(X_train)
    y_train_t = torch.tensor(y_train)
    X_test_t = torch.tensor(X_test)
    y_test_t = torch.tensor(y_test)

    train_ds = TensorDataset(X_train_t, y_train_t)
    # Use seeded generator for deterministic shuffling
    g = torch.Generator()
    g.manual_seed(RANDOM_SEED)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, generator=g)

    model = StockLSTM(
        input_size=n_features,
        hidden_size=128,
        num_layers=3,
        output_size=PREDICT_DAYS,
    )
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5, min_lr=1e-6,
    )

    best_val_loss = float("inf")
    epochs_no_improve = 0

    for epoch in range(epochs):
        model.train()
        for xb, yb in train_loader:
            optimizer.zero_grad()
            preds = model(xb)
            loss = criterion(preds, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_preds = model(X_test_t)
            val_loss = float(criterion(val_preds, y_test_t))

        scheduler.step(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            epochs_no_improve = 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience:
                break

    if best_val_loss < float("inf"):
        model.load_state_dict(best_state)

    model.eval()
    with torch.no_grad():
        test_preds = model(X_test_t).numpy()
        test_loss = float(criterion(torch.tensor(test_preds), y_test_t))

    confidence = max(0, min(100, round((1 - test_loss * 10) * 100, 1)))
    if confidence >= 70:
        risk = "Low"
    elif confidence >= 45:
        risk = "Medium"
    else:
        risk = "High"

    last_window = features[-LOOK_BACK:]
    last_scaled = scaler.transform(last_window).reshape(1, LOOK_BACK, n_features)
    last_seq = torch.tensor(last_scaled, dtype=torch.float32)

    with torch.no_grad():
        raw_pred = model(last_seq).numpy().flatten()

    dummy = np.zeros((len(raw_pred), n_features), dtype=np.float32)
    dummy[:, 0] = raw_pred
    lstm_prices = scaler.inverse_transform(dummy)[:, 0].tolist()
    current_price = float(close[-1])

    # ── Enterprise ensemble ──
    h2o_p, dr_p, alt_p = get_enterprise_predictions(df, current_price)
    enterprise_blend = blend_enterprise_predictions(h2o_p, dr_p, alt_p)

    # ── Build base prediction from LSTM shape + enterprise magnitude ──
    lstm_enterprise_weight = w_lstm + w_enterprise 
    lstm_frac = w_lstm / lstm_enterprise_weight      
    ent_frac = w_enterprise / lstm_enterprise_weight  

    if enterprise_blend is not None:
        # Sanity-check enterprise: if Day 1 is >8% from current price,
        # it's predicting a mean-reversion from historical highs — dampen it.
        ent_day1 = enterprise_blend[0]
        ent_deviation_pct = abs(ent_day1 - current_price) / current_price * 100
        if ent_deviation_pct > 8.0:
            # Pull enterprise predictions toward current price proportionally
            pull_factor = 8.0 / ent_deviation_pct  # e.g., 8/30 = 0.27
            enterprise_blend = [
                round(current_price + (p - current_price) * pull_factor, 2)
                for p in enterprise_blend
            ]

        # Shift LSTM to match enterprise endpoint, preserving curvature
        ent_day5 = enterprise_blend[-1]
        lstm_day5 = lstm_prices[-1]
        endpoint_shift = ent_day5 - lstm_day5

        base_prices = []
        for i in range(PREDICT_DAYS):
            t = (i + 1) / PREDICT_DAYS
            shifted_lstm = lstm_prices[i] + endpoint_shift * t
            blended = lstm_frac * shifted_lstm + ent_frac * enterprise_blend[i]
            base_prices.append(blended)
        models_used = ["LSTM", "H2O", "DataRobot", "Alteryx"]
    else:
        base_prices = list(lstm_prices)
        models_used = ["LSTM"]

    # ── Apply directional factors (sentiment + technical + LLM) ──
    # Each factor nudges prices — total impact capped at MAX_DIRECTIONAL_IMPACT_PCT
    # LLM and sentiment can push direction but cannot override price level
    directional_weight = w_sentiment + w_technical + w_llm 
    if directional_weight > 0:
        # Weighted directional score
        weighted_dir_score = (
            w_sentiment * sentiment_score +
            w_technical * technical_score +
            w_llm * llm_score
        ) / directional_weight

        # Cap maximum impact
        max_impact = current_price * MAX_DIRECTIONAL_IMPACT_PCT / 100
        dir_adjustment = weighted_dir_score * max_impact

        predicted_prices = []
        for i in range(PREDICT_DAYS):
            t = (i + 1) / PREDICT_DAYS  # builds over time: 0.2 to 1.0
            # Directional push increases toward day 5
            adjusted = base_prices[i] + dir_adjustment * t
            predicted_prices.append(round(adjusted, 2))
    else:
        predicted_prices = [round(p, 2) for p in base_prices]

    # ── Post-processing: apply physical constraints ──
    # Order matters:
    #   1. Drawdown dampening (handles crash-bounce hallucinations)
    #   2. Daily move cap    (prevents >2.5%/day fantasy moves)
    #   3. Live price anchor (pins Day 1 to actual traded price)
    #   4. Min volatility    (prevents dead-pulse flat lines)
    predicted_prices = _apply_drawdown_dampening(predicted_prices, current_price, df)
    predicted_prices = _cap_daily_moves(predicted_prices, current_price)
    predicted_prices = _anchor_to_live_price(predicted_prices, current_price)
    predicted_prices = _add_minimum_volatility(predicted_prices, current_price, df)

    # ── Factor breakdown for the API response ──
    factor_breakdown = {
        "lstm": {
            "weight": int(w_lstm * 100),
            "contribution": "shape",
            "description": "Day-by-day price dynamics",
        },
        "enterprise": {
            "weight": int(w_enterprise * 100),
            "contribution": "magnitude",
            "models": [m for m in models_used if m != "LSTM"],
            "description": "H2O + DataRobot + Alteryx ensemble",
        },
        "technical": {
            "weight": int(w_technical * 100),
            "score": round(technical_score, 3),
            "direction": technical_direction,
            "description": "RSI / MACD / SMA trend analysis",
        },
        "sentiment": {
            "weight": int(w_sentiment * 100),
            "score": round(sentiment_score, 3),
            "direction": sentiment_label,
            "description": "FinBERT + VADER news analysis",
        },
        "llm": {
            "weight": int(w_llm * 100),
            "score": round(llm_score, 3),
            "direction": llm_direction,
            "description": "Gemini AI market reasoning",
        },
        "mode": "Crisis" if is_crisis else "Normal",
        "crisis_reason": crisis_reason,
    }

    historical_prices = close[-30:].tolist()

    if "Date" in df.columns:
        last_dates = df["Date"].iloc[-30:]
        hist_dates = [str(d.date()) if hasattr(d, 'date') else str(d)[:10] for d in last_dates]
    else:
        hist_dates = [(datetime.now() - timedelta(days=30-i)).strftime("%Y-%m-%d") for i in range(30)]

    last_date = datetime.now()
    pred_dates = []
    bdays = 0
    d = last_date
    while bdays < PREDICT_DAYS:
        d += timedelta(days=1)
        if d.weekday() < 5:
            pred_dates.append(d.strftime("%Y-%m-%d"))
            bdays += 1

    result = {
        "predicted_prices": predicted_prices,
        "confidence": confidence,
        "risk": risk,
        "test_mse": round(test_loss, 6),
        "historical_last_30": [round(float(p), 2) for p in historical_prices],
        "historical_dates": hist_dates,
        "prediction_dates": pred_dates,
        "blend": f"LSTM {int(W_LSTM*100)}% + Enterprise {int(W_ENTERPRISE*100)}% + Technical {int(W_TECHNICAL*100)}% + News {int(W_SENTIMENT*100)}% + LLM {int(W_LLM*100)}%",
        "models_used": models_used,
        "factor_breakdown": factor_breakdown,
    }

    # ── Store in cache ──
    _set_cache(cache_key, result)

    return result