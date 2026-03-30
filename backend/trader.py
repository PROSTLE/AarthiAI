
import json
import os
from datetime import datetime
from threading import Lock

INITIAL_BALANCE = 1_000_000.00
MAX_HOLD_BARS = 60          # ~60 min max hold for intraday
DEFAULT_POSITION_PCT = 10.0 # fallback if dynamic sizing unavailable
RISK_PER_TRADE_MIN = 0.008  # 0.8% of capital
RISK_PER_TRADE_MAX = 0.015  # 1.5% of capital
RISK_PER_TRADE_DEFAULT = 0.01  # 1.0% default

DATA_FILE = "portfolio.json"
_lock = Lock()


def _default_state():
    return {
        "balance": INITIAL_BALANCE,
        "initial_balance": INITIAL_BALANCE,
        "positions": {},
        "trade_history": [],
        "bot_active": True,  # Bot starts as ACTIVE by default
        "created_at": datetime.now().isoformat(),
    }


def _load_state() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return _default_state()


def _save_state(state: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def get_portfolio() -> dict:
    with _lock:
        state = _load_state()
    return state


def reset_portfolio() -> dict:
    with _lock:
        state = _default_state()
        _save_state(state)
    return state


def toggle_bot() -> dict:
    with _lock:
        state = _load_state()
        state["bot_active"] = not state["bot_active"]
        _save_state(state)
    return {"bot_active": state["bot_active"]}


def add_to_balance(amount: float, payment_id: str = "") -> dict:
    """Add funds to the portfolio balance (wallet top-up)."""
    with _lock:
        state = _load_state()
        state["balance"] += amount
        state["balance"] = round(state["balance"], 2)
        # Also bump initial_balance so reset reflects deposits
        state["initial_balance"] = round(state.get("initial_balance", INITIAL_BALANCE) + amount, 2)
        # Record transaction
        txn = {
            "type": "credit",
            "amount": amount,
            "payment_id": payment_id,
            "timestamp": datetime.now().isoformat(),
            "status": "success",
        }
        state.setdefault("wallet_transactions", []).append(txn)
        _save_state(state)
    return {"status": "success", "new_balance": state["balance"], "transaction": txn}


def withdraw_from_balance(amount: float) -> dict:
    """Withdraw funds from the portfolio balance."""
    with _lock:
        state = _load_state()
        if amount > state["balance"]:
            return {"status": "error", "message": "Insufficient balance"}
        state["balance"] -= amount
        state["balance"] = round(state["balance"], 2)
        state["initial_balance"] = round(state.get("initial_balance", INITIAL_BALANCE) - amount, 2)
        txn = {
            "type": "debit",
            "amount": amount,
            "timestamp": datetime.now().isoformat(),
            "status": "success",
        }
        state.setdefault("wallet_transactions", []).append(txn)
        _save_state(state)
    return {"status": "success", "new_balance": state["balance"], "transaction": txn}


def get_wallet_transactions() -> list:
    """Return wallet transaction history."""
    with _lock:
        state = _load_state()
    return state.get("wallet_transactions", [])


def record_portfolio_snapshot(total_value: float):
    """Record a portfolio value snapshot for the account value chart."""
    with _lock:
        state = _load_state()
        snapshots = state.setdefault("value_history", [])
        snapshots.append({
            "timestamp": datetime.now().isoformat(),
            "value": round(total_value, 2),
        })
        # Keep at most 500 snapshots
        if len(snapshots) > 500:
            snapshots[:] = snapshots[-500:]
        _save_state(state)


def get_value_history() -> list:
    """Return portfolio value snapshots for the account value chart."""
    with _lock:
        state = _load_state()

    snapshots = list(state.get("value_history", []))

    # If no snapshots yet, synthesize from trade history
    if not snapshots:
        initial = state.get("initial_balance", INITIAL_BALANCE)
        created = state.get("created_at", datetime.now().isoformat())
        snapshots.append({"timestamp": created, "value": initial})

        running = initial
        for t in state.get("trade_history", []):
            running += t.get("profit", 0)
            snapshots.append({
                "timestamp": t.get("sell_time", t.get("buy_time", "")),
                "value": round(running, 2),
            })

    return snapshots


def compute_dynamic_levels(
    current_price: float,
    atr: float,
    regime: str = "SIDEWAYS",
    is_ipo: bool = False,
) -> dict:
    """
    Compute ATR-based dynamic SL / TP1 / TP2 levels.
    Regime and IPO flag modulate width.
    """
    if atr <= 0:
        atr = current_price * 0.005  # fallback: 0.5% of price

    # Base multipliers (in ATR units)
    sl_mult = 1.5
    tp1_mult = 2.5
    tp2_mult = 3.5

    # Regime modifiers
    regime_mod = {
        "BULL_LOW_VOL":  {"sl": 0.9,  "tp": 1.2},
        "BULL_HIGH_VOL": {"sl": 1.1,  "tp": 1.0},
        "BEAR_HIGH_VOL": {"sl": 1.3,  "tp": 0.7},
        "SIDEWAYS":      {"sl": 1.0,  "tp": 0.8},
    }.get(regime, {"sl": 1.0, "tp": 1.0})

    sl_mult  *= regime_mod["sl"]
    tp1_mult *= regime_mod["tp"]
    tp2_mult *= regime_mod["tp"]

    # IPO boost: more upside room, tighter stop
    if is_ipo:
        tp1_mult *= 1.5
        tp2_mult *= 1.8
        sl_mult  *= 0.8

    sl_distance  = atr * sl_mult
    tp1_distance = atr * tp1_mult
    tp2_distance = atr * tp2_mult

    sl_price  = round(current_price - sl_distance, 2)
    tp1_price = round(current_price + tp1_distance, 2)
    tp2_price = round(current_price + tp2_distance, 2)

    sl_pct  = round(((sl_price - current_price) / current_price) * 100, 2)
    tp1_pct = round(((tp1_price - current_price) / current_price) * 100, 2)
    tp2_pct = round(((tp2_price - current_price) / current_price) * 100, 2)

    # Clamp target pct to [0.5%, 5.0%]
    tp1_pct = max(0.5, min(5.0, tp1_pct))
    tp2_pct = max(tp1_pct + 0.3, min(5.0, tp2_pct))
    tp1_price = round(current_price * (1 + tp1_pct / 100), 2)
    tp2_price = round(current_price * (1 + tp2_pct / 100), 2)

    # Include TP2 only in bullish regimes or IPO stocks
    include_tp2 = is_ipo or regime in ("BULL_LOW_VOL", "BULL_HIGH_VOL")

    return {
        "sl_price": sl_price, "sl_pct": sl_pct,
        "tp1_price": tp1_price, "tp1_pct": tp1_pct,
        "tp2_price": tp2_price, "tp2_pct": tp2_pct,
        "include_tp2": include_tp2,
        "atr_used": round(atr, 4),
    }


def risk_check_position_size(
    balance: float,
    current_price: float,
    sl_price: float,
    risk_pct: float = RISK_PER_TRADE_DEFAULT,
) -> int:
    """
    Compute position size so that the max loss (entry→SL) ≤ risk_pct of capital.
    Returns number of shares.
    """
    risk_pct = max(RISK_PER_TRADE_MIN, min(RISK_PER_TRADE_MAX, risk_pct))
    risk_amount = balance * risk_pct
    per_share_risk = abs(current_price - sl_price)
    if per_share_risk <= 0:
        per_share_risk = current_price * 0.01  # fallback 1%
    shares = int(risk_amount // per_share_risk)
    # Also cap at DEFAULT_POSITION_PCT of balance
    max_by_balance = int((balance * DEFAULT_POSITION_PCT / 100) // current_price)
    shares = min(shares, max_by_balance)
    return max(shares, 0)


def execute_buy(
    ticker: str,
    current_price: float,
    predicted_prices: list,
    confidence: float,
    sl_price: float | None = None,
    tp1_price: float | None = None,
    tp2_price: float | None = None,
    regime: str = "SIDEWAYS",
) -> dict:
    with _lock:
        state = _load_state()

        if ticker in state["positions"]:
            return {"status": "skipped", "reason": f"Already holding {ticker}"}

        # Dynamic position sizing based on risk
        if sl_price and sl_price < current_price:
            shares = risk_check_position_size(state["balance"], current_price, sl_price)
        else:
            position_value = state["balance"] * (DEFAULT_POSITION_PCT / 100)
            shares = int(position_value // current_price)
            # Fallback SL/TP if not provided
            if sl_price is None:
                sl_price = round(current_price * 0.985, 2)
            if tp1_price is None:
                tp1_price = round(current_price * 1.02, 2)

        if shares == 0:
            return {"status": "skipped", "reason": "Position too small after risk check"}

        cost = shares * current_price
        if cost > state["balance"]:
            shares = int(state["balance"] // current_price)
            if shares == 0:
                return {"status": "skipped", "reason": "Insufficient balance"}
            cost = shares * current_price

        # Trailing stop starts at the hard SL
        trailing_stop = sl_price

        position = {
            "ticker": ticker,
            "shares": shares,
            "buy_price": current_price,
            "cost": round(cost, 2),
            "stop_loss": sl_price,
            "tp1": tp1_price,
            "tp2": tp2_price,
            "trailing_stop": trailing_stop,
            "peak_price": current_price,
            "predicted_prices": predicted_prices,
            "confidence": confidence,
            "regime": regime,
            "buy_time": datetime.now().isoformat(),
            "bar_count": 0,
        }

        state["balance"] -= cost
        state["balance"] = round(state["balance"], 2)
        state["positions"][ticker] = position
        _save_state(state)

        snapshot_value = state["balance"]
        result = {
            "status": "bought",
            "ticker": ticker,
            "shares": shares,
            "price": current_price,
            "cost": round(cost, 2),
            "stop_loss": sl_price,
            "tp1": tp1_price,
            "tp2": tp2_price,
            "regime": regime,
            "balance": state["balance"],
        }

    # Record portfolio value snapshot OUTSIDE the lock to avoid deadlock
    try:
        pos_value = sum(p["shares"] * p["buy_price"] for p in state["positions"].values())
        record_portfolio_snapshot(snapshot_value + pos_value)
    except Exception:
        pass

    return result


def execute_sell(ticker: str, current_price: float, reason: str) -> dict:
    with _lock:
        state = _load_state()

        if ticker not in state["positions"]:
            return {"status": "skipped", "reason": f"No position in {ticker}"}

        pos = state["positions"][ticker]
        revenue = pos["shares"] * current_price
        profit = revenue - pos["cost"]
        profit_pct = (profit / pos["cost"]) * 100

        trade = {
            "ticker": ticker,
            "shares": pos["shares"],
            "buy_price": pos["buy_price"],
            "sell_price": current_price,
            "cost": pos["cost"],
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 2),
            "buy_time": pos["buy_time"],
            "sell_time": datetime.now().isoformat(),
            "reason": reason,
            "confidence": pos["confidence"],
        }

        state["balance"] += revenue
        state["balance"] = round(state["balance"], 2)
        state["trade_history"].append(trade)
        del state["positions"][ticker]
        _save_state(state)

        snapshot_value = state["balance"]
        remaining_positions = dict(state["positions"])
        result = {
            "status": "sold",
            "ticker": ticker,
            "shares": trade["shares"],
            "price": current_price,
            "profit": trade["profit"],
            "profit_pct": trade["profit_pct"],
            "reason": reason,
            "balance": state["balance"],
        }

    # Record portfolio value snapshot OUTSIDE the lock to avoid deadlock
    try:
        pos_value = sum(p["shares"] * p["buy_price"] for p in remaining_positions.values())
        record_portfolio_snapshot(snapshot_value + pos_value)
    except Exception:
        pass

    return result


def check_position(ticker: str, current_price: float) -> dict:
    with _lock:
        state = _load_state()

    if ticker not in state["positions"]:
        return {"action": "none", "reason": "No position"}

    pos = state["positions"][ticker]
    buy_price = pos["buy_price"]
    change_pct = ((current_price - buy_price) / buy_price) * 100

    sl = pos["stop_loss"]
    tp1 = pos.get("tp1") or pos.get("take_profit", buy_price * 1.02)

    # Hard stop-loss
    if current_price <= sl:
        sl_pct = round(((sl - buy_price) / buy_price) * 100, 2)
        return {"action": "sell", "reason": f"Stop-loss triggered ({sl_pct}%)"}

    # Take-profit 1 hit
    if current_price >= tp1:
        tp_pct = round(((tp1 - buy_price) / buy_price) * 100, 2)
        return {"action": "sell", "reason": f"Target 1 reached (+{tp_pct}%)"}

    # Trailing stop: move up as price makes new highs
    if current_price > pos["peak_price"]:
        with _lock:
            state = _load_state()
            if ticker in state["positions"]:
                state["positions"][ticker]["peak_price"] = current_price
                # Trailing stop = 50% of the distance from entry to SL
                trail_dist = abs(buy_price - sl) * 0.5
                new_trailing = round(current_price - trail_dist, 2)
                if new_trailing > state["positions"][ticker]["trailing_stop"]:
                    state["positions"][ticker]["trailing_stop"] = new_trailing
                _save_state(state)
    elif current_price <= pos["trailing_stop"]:
        trail_pct = round(((pos["trailing_stop"] - buy_price) / buy_price) * 100, 2)
        return {"action": "sell", "reason": f"Trailing stop triggered ({trail_pct}%)"}

    # Max hold bars (intraday) — persist incremented bar_count
    new_bar_count = pos.get("bar_count", pos.get("day_count", 0)) + 1
    with _lock:
        state = _load_state()
        if ticker in state["positions"]:
            state["positions"][ticker]["bar_count"] = new_bar_count
            _save_state(state)
    if new_bar_count >= MAX_HOLD_BARS:
        return {"action": "sell", "reason": f"Max hold period ({MAX_HOLD_BARS} bars)"}

    return {
        "action": "hold",
        "reason": "Within thresholds",
        "current_pnl": round(change_pct, 2),
        "current_price": current_price,
        "stop_loss": sl,
        "tp1": tp1,
        "trailing_stop": pos["trailing_stop"],
    }


def compute_technical_score(indicators: dict) -> float:
    score = 50.0

    rsi = indicators.get("RSI", 50)
    macd = indicators.get("MACD", 0)
    macd_signal = indicators.get("MACD_Signal", 0)
    sma_20 = indicators.get("SMA_20", 0)
    sma_50 = indicators.get("SMA_50", 0)
    price = indicators.get("price", 0)

    if rsi < 25:
        score += 20
    elif rsi < 35:
        score += 12
    elif rsi < 45:
        score += 5
    elif rsi > 75:
        score -= 20
    elif rsi > 65:
        score -= 12
    elif rsi > 55:
        score -= 5

    macd_diff = macd - macd_signal
    if macd_diff > 0:
        score += min(15, macd_diff * 100)
    else:
        score += max(-15, macd_diff * 100)

    if sma_20 > 0 and price > sma_20:
        score += 8
    elif sma_20 > 0:
        score -= 8

    if sma_50 > 0 and price > sma_50:
        score += 7
    elif sma_50 > 0:
        score -= 7

    if sma_20 > 0 and sma_50 > 0:
        if sma_20 > sma_50:
            score += 5
        else:
            score -= 5

    return max(0, min(100, score))


# Plausible 5-day move cap: avoid impossible V-spikes / apocalyptic plunges from raw LSTM
PRED_CHANGE_PCT_CAP = 4.0  # ±4% over 5 days used for scoring; raw pred still reported


def compute_composite_score(
    predicted_prices: list,
    current_price: float,
    confidence: float,
    indicators: dict | None = None,
    sentiment_score: float | None = None,
    xgb_score: float | None = None,
    regime: str | None = None,
) -> dict:
    pred_day5 = predicted_prices[-1]
    pred_change_pct = ((pred_day5 - current_price) / current_price) * 100
    days_above = sum(1 for p in predicted_prices if p > current_price)

    # Cap extreme LSTM moves for scoring so one-off model spikes don't dominate
    effective_pred_pct = max(-PRED_CHANGE_PCT_CAP, min(PRED_CHANGE_PCT_CAP, pred_change_pct))

    lstm_score = 50.0
    lstm_score += effective_pred_pct * 5
    lstm_score += (days_above - 2.5) * 6
    lstm_score += (confidence - 50) * 0.3
    lstm_score = max(0, min(100, lstm_score))

    # XGBoost score: if not provided, fallback to 50
    if xgb_score is None:
        xgb_score = 50.0

    if sentiment_score is not None:
        sent_score = 50 + sentiment_score * 50
        sent_score = max(0, min(100, sent_score))
    else:
        sent_score = 50.0

    # High-vol regimes: downweight news so isolated headlines (e.g. one positive in a sell-off)
    # don't override macro; keep 45% LSTM, 45% XGBoost, 10% news in calm regimes only
    high_vol = regime in ("BEAR_HIGH_VOL", "BULL_HIGH_VOL")
    if high_vol:
        LSTM_W, XGB_W, SENT_W = 0.485, 0.485, 0.03   # 3% news in high vol
    else:
        LSTM_W, XGB_W, SENT_W = 0.45, 0.45, 0.10

    composite = (lstm_score * LSTM_W) + (xgb_score * XGB_W) + (sent_score * SENT_W)
    composite = round(max(0, min(100, composite)), 1)

    return {
        "composite_score": composite,
        "lstm_score": round(lstm_score, 1),
        "xgb_score": round(xgb_score, 1),
        "sent_score": round(sent_score, 1),
        "pred_change_pct": round(pred_change_pct, 2),
        "pred_change_pct_capped": round(effective_pred_pct, 2),
        "days_above": days_above,
        "sentiment_weight_used": SENT_W,
    }


def detect_market_regime(
    indicators: dict | None = None,
    vix: dict | None = None,
    nifty: dict | None = None,
) -> dict:
    """
    4-state regime detection using VIX, Nifty trend, and stock-level signals.
    States: BULL_LOW_VOL, BULL_HIGH_VOL, BEAR_HIGH_VOL, SIDEWAYS
    """
    vix_level = (vix or {}).get("vix_level", 15.0)
    nifty_trend = (nifty or {}).get("trend", "flat")
    nifty_bullish = nifty_trend == "bullish"
    nifty_bearish = nifty_trend == "bearish"

    # Stock-level signals
    bull_signals = 0
    bear_signals = 0
    if indicators:
        rsi = indicators.get("RSI", 50)
        price = indicators.get("price", 0)
        ema9 = indicators.get("EMA_9", indicators.get("SMA_20", 0))
        ema21 = indicators.get("EMA_21", indicators.get("SMA_50", 0))
        supertrend_dir = indicators.get("Supertrend_Dir", indicators.get("supertrend_dir", 0))

        if rsi < 40: bull_signals += 1
        elif rsi > 65: bear_signals += 1

        if ema9 > 0 and price > ema9: bull_signals += 1
        elif ema9 > 0: bear_signals += 1

        if ema21 > 0 and price > ema21: bull_signals += 1
        elif ema21 > 0: bear_signals += 1

        if supertrend_dir == 1: bull_signals += 1
        elif supertrend_dir == -1: bear_signals += 1

        macd = indicators.get("MACD", 0)
        macd_signal = indicators.get("MACD_Signal", 0)
        if macd > macd_signal: bull_signals += 1
        else: bear_signals += 1

    # Combine VIX + Nifty + stock signals into 4-state regime
    high_vol = vix_level >= 18
    very_high_vol = vix_level >= 22

    if nifty_bearish and (very_high_vol or bear_signals >= 3):
        regime = "BEAR_HIGH_VOL"
        entry_threshold = 0.1    # DEMO: much easier entry
        min_confidence = 5
    elif nifty_bullish and not high_vol and bull_signals >= 2:
        regime = "BULL_LOW_VOL"
        entry_threshold = 0.05   # DEMO: very easy entry
        min_confidence = 2
    elif nifty_bullish and high_vol:
        regime = "BULL_HIGH_VOL"
        entry_threshold = 0.1
        min_confidence = 5
    else:
        regime = "SIDEWAYS"
        entry_threshold = 0.15
        min_confidence = 5

    return {
        "regime": regime,
        "entry_threshold": entry_threshold,
        "min_confidence": min_confidence,
        "vix_level": vix_level,
        "nifty_trend": nifty_trend,
        "bull_signals": bull_signals,
        "bear_signals": bear_signals,
    }


def evaluate_trade_signal(
    ticker: str,
    current_price: float,
    predicted_prices: list,
    confidence: float,
    indicators: dict | None = None,
    sentiment_score: float | None = None,
) -> dict:
    """Legacy trade signal evaluation (used by manual /trade/execute endpoint)."""
    state = _load_state()

    regime = detect_market_regime(indicators=indicators)
    # Backwards-compatible thresholds derived from new regime
    regime_thresholds = {
        "BULL_LOW_VOL":  {"buy": 5, "sell": 30},   # DEMO: much lower buy threshold
        "BULL_HIGH_VOL": {"buy": 8, "sell": 35},
        "BEAR_HIGH_VOL": {"buy": 10, "sell": 40},
        "SIDEWAYS":      {"buy": 7, "sell": 35},
    }
    thresholds = regime_thresholds.get(regime["regime"], {"buy": 7, "sell": 35})
    buy_threshold = thresholds["buy"]
    sell_threshold = thresholds["sell"]

    scores = compute_composite_score(
        predicted_prices, current_price, confidence,
        indicators, sentiment_score,
        regime=regime["regime"],
    )
    composite = scores["composite_score"]

    pred_day1 = predicted_prices[0]
    pred_day5 = predicted_prices[-1]
    pred_direction = "up" if pred_day5 > current_price else "down"

    signal = {
        "ticker": ticker,
        "current_price": current_price,
        "predicted_day1": round(pred_day1, 2),
        "predicted_day5": round(pred_day5, 2),
        "pred_change_pct": scores["pred_change_pct"],
        "pred_direction": pred_direction,
        "days_above_current": scores["days_above"],
        "confidence": confidence,
        "composite_score": composite,
        "market_regime": regime["regime"],
        "scores": scores,
    }

    if ticker in state["positions"]:
        check = check_position(ticker, current_price)
        if check["action"] == "sell":
            result = execute_sell(ticker, current_price, check["reason"])
            signal["action"] = "SELL"
            signal["trade_result"] = result
        elif composite <= sell_threshold:
            result = execute_sell(ticker, current_price,
                                 f"Bearish signal in {regime['regime']} market ({composite}/100)")
            signal["action"] = "SELL"
            signal["trade_result"] = result
        else:
            signal["action"] = "HOLD"
            signal["position"] = check
    else:
        if composite >= buy_threshold and confidence >= regime.get("min_confidence", 20):
            result = execute_buy(ticker, current_price, predicted_prices, confidence)
            signal["action"] = "BUY"
            signal["trade_result"] = result
        elif (scores["pred_change_pct"] > 2.0 and scores["days_above"] >= 3
              and confidence >= 25):
            result = execute_buy(ticker, current_price, predicted_prices, confidence)
            signal["action"] = "BUY"
            signal["trade_result"] = result
        else:
            signal["action"] = "WAIT"
            signal["reason"] = (
                f"Score {composite}/100 ({regime['regime']} mode, "
                f"need >={buy_threshold})"
            )

    return signal

