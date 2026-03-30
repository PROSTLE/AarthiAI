"""
execution/order_manager.py
Full trade lifecycle: entry → GTT stop/target → monitoring → force exit.
Uses Kite client + risk guardrails together.
"""
import logging
import time
import schedule
import redis
import json
from datetime import datetime, date
from config import SECRETS, MARKET, RISK

log = logging.getLogger(__name__)

_r = redis.Redis(
    host=SECRETS.get("redis", {}).get("host", "localhost"),
    port=SECRETS.get("redis", {}).get("port", 6379),
    decode_responses=True,
)

SQUARE_OFF_TIME = MARKET.get("intraday_square_off", "15:15")


# ── Core trade entry ──────────────────────────────────────────────────────────

def execute_trade(
    ticker: str,
    signal: str,               # "LONG" or "SHORT"
    entry_price: float,
    stop_price: float,
    target_price: float,
    capital: float,
    trade_type: str = "intraday",
    size_multiplier: float = 1.0,
    user_id: str = "default",
    current_counts: dict | None = None,
) -> dict:
    """
    End-to-end trade execution with all guardrails applied.
    Returns trade record dict or {"status": "BLOCKED", "reason": ...}
    """
    from risk.guardrails import pre_trade_gate, safe_position_size, add_risk_used
    from ingestion.kite_client import (
        place_market_order, place_gtt_oco, kite
    )

    # 1. Pre-trade gate
    gate_pass, gate_reason = pre_trade_gate(
        capital, trade_type, current_counts or {}, user_id
    )
    if not gate_pass:
        log.warning("Trade BLOCKED [%s]: %s", ticker, gate_reason)
        return {"status": "BLOCKED", "reason": gate_reason, "ticker": ticker}

    # 2. Position sizing
    product = "MIS" if trade_type == "intraday" else "CNC"
    qty     = safe_position_size(capital, entry_price, stop_price, size_multiplier)
    side    = "BUY" if signal == "LONG" else "SELL"

    # 3. Place entry order
    try:
        order_id = place_market_order(ticker.replace(".NS", ""), qty, side, product)
    except Exception as e:
        log.error("Entry order failed for %s: %s", ticker, e)
        return {"status": "FAILED", "reason": str(e), "ticker": ticker}

    # 4. Wait briefly for fill confirmation
    time.sleep(0.4)

    # 5. Place GTT OCO stop-loss + target (must happen within 2 seconds of entry)
    gtt_exit_side = "SELL" if signal == "LONG" else "BUY"
    try:
        gtt_id = place_gtt_oco(
            symbol=ticker.replace(".NS", ""),
            qty=qty,
            side=gtt_exit_side,
            stop=stop_price,
            target=target_price,
            last_price=entry_price,
            product=product,
        )
    except Exception as e:
        log.error("GTT placement failed for %s — NAKED POSITION RISK: %s", ticker, e)
        gtt_id = None

    # 6. Record risk used
    risk_per_trade = abs(entry_price - stop_price) * qty
    add_risk_used(risk_per_trade, user_id)

    # 7. Persist trade record in Redis (TTL 24h)
    trade_record = {
        "ticker":       ticker,
        "signal":       signal,
        "entry_price":  entry_price,
        "stop_price":   stop_price,
        "target_price": target_price,
        "qty":          qty,
        "order_id":     order_id,
        "gtt_id":       str(gtt_id) if gtt_id else "",
        "trade_type":   trade_type,
        "product":      product,
        "user_id":      user_id,
        "timestamp":    datetime.utcnow().isoformat(),
        "status":       "OPEN",
    }
    key = f"trade:{user_id}:{order_id}"
    _r.set(key, json.dumps(trade_record), ex=86400)

    log.info(
        "TRADE EXECUTED: %s %s x%d @ %.2f | SL=%.2f | TGT=%.2f | GTT=%s",
        signal, ticker, qty, entry_price, stop_price, target_price, gtt_id
    )
    return {"status": "OK", **trade_record}


# ── Intraday position monitor ─────────────────────────────────────────────────

def monitor_intraday_positions(user_id: str = "default"):
    """
    Runs every 5 minutes via schedule library.
    Checks P&L, checks daily loss limit, force-squares at SQUARE_OFF_TIME.
    """
    now_str = datetime.now().strftime("%H:%M")

    # Force square-off at 15:15
    if now_str >= SQUARE_OFF_TIME:
        log.info("Square-off time reached (%s) — closing all intraday positions", SQUARE_OFF_TIME)
        _square_off_all_intraday(user_id)
        return

    # Check daily loss limit
    from ingestion.kite_client import get_day_pnl, get_available_capital, kite
    from risk.guardrails import is_halted, emergency_halt

    if is_halted(user_id):
        return

    try:
        capital = get_available_capital()
        pnl     = get_day_pnl()

        from config import RISK
        limit   = capital * RISK.get("max_daily_loss_pct", 0.02) / 100 * -1
        if pnl <= limit:
            log.critical("Daily loss limit breached! P&L=%.2f, Limit=%.2f", pnl, limit)
            emergency_halt(kite, user_id)
            _send_emergency_notification(user_id, pnl, limit)
    except Exception as e:
        log.error("Monitor cycle error: %s", e)


def _square_off_all_intraday(user_id: str):
    """Force exit all MIS (intraday) positions at market price."""
    try:
        from ingestion.kite_client import kite, place_market_order, cancel_all_open_orders
        cancel_all_open_orders()
        positions = kite.positions().get("day", [])
        for pos in positions:
            qty = pos.get("quantity", 0)
            if qty == 0 or pos.get("product") != "MIS":
                continue
            side = "SELL" if qty > 0 else "BUY"
            place_market_order(pos["tradingsymbol"], abs(qty), side, "MIS")
            log.info("Force-squared %s x%d", pos["tradingsymbol"], abs(qty))
    except Exception as e:
        log.error("Square-off failed: %s", e)


def _send_emergency_notification(user_id: str, pnl: float, limit: float):
    """Push notification via Firebase."""
    try:
        import firebase_admin
        from firebase_admin import messaging
        msg = messaging.Message(
            notification=messaging.Notification(
                title="⚠️ AarthiAI — Emergency Halt",
                body=f"Daily loss limit breached! P&L: ₹{pnl:,.2f} (Limit: ₹{limit:,.2f}). All positions squared off.",
            ),
            topic=f"user_{user_id}",
        )
        messaging.send(msg)
    except Exception as e:
        log.error("Emergency notification failed: %s", e)


def start_intraday_monitor(user_id: str = "default"):
    """Start the 5-minute heartbeat monitor (run in a thread)."""
    schedule.every(5).minutes.do(monitor_intraday_positions, user_id=user_id)
    log.info("Intraday position monitor started (every 5 min)")
    import threading

    def _run():
        import time
        while True:
            schedule.run_pending()
            time.sleep(30)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
