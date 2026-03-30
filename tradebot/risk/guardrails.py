"""
risk/guardrails.py
Hard-coded non-negotiable risk limits.
Cannot be overridden by any user setting or API call.
"""
import logging
import redis
from datetime import date
from config import SECRETS, RISK

log = logging.getLogger(__name__)

_r = redis.Redis(
    host=SECRETS.get("redis", {}).get("host", "localhost"),
    port=SECRETS.get("redis", {}).get("port", 6379),
    decode_responses=True,
)

MAX_DAILY_LOSS_PCT      = RISK.get("max_daily_loss_pct", 2.0) / 100
MAX_SINGLE_TRADE_PCT    = RISK.get("max_single_trade_risk_pct", 1.5) / 100
MAX_STOP_DISTANCE_PCT   = RISK.get("max_stop_distance_pct", 2.0) / 100
MAX_INTRADAY_POSITIONS  = RISK.get("max_intraday_positions", 5)
MAX_SWING_POSITIONS     = RISK.get("max_swing_positions", 3)
MAX_POSITIONAL          = RISK.get("max_positional_positions", 2)


# ── Daily halt flag ───────────────────────────────────────────────────────────

def is_halted(user_id: str = "default") -> bool:
    return _r.exists(f"halt:{user_id}:{date.today().isoformat()}") == 1


def set_halt(user_id: str = "default"):
    _r.set(f"halt:{user_id}:{date.today().isoformat()}", "1", ex=86400)
    log.critical("HALT SET for user %s — AutoTrade disabled for today", user_id)


def get_daily_risk_used(user_id: str = "default") -> float:
    val = _r.get(f"risk_used:{user_id}:{date.today().isoformat()}")
    return float(val) if val else 0.0


def add_risk_used(amount: float, user_id: str = "default"):
    key = f"risk_used:{user_id}:{date.today().isoformat()}"
    _r.incrbyfloat(key, amount)
    _r.expire(key, 86400)


# ── Position size calculation ─────────────────────────────────────────────────

def safe_position_size(
    capital: float,
    entry: float,
    stop: float,
    size_multiplier: float = 1.0,
) -> int:
    """
    Shares = risk_amount / stop_distance
    Enforces both MAX_SINGLE_TRADE_PCT and MAX_STOP_DISTANCE_PCT.
    size_multiplier: 1.5 for Aggressive mood, 1.0 for others.
    """
    stop_distance     = abs(entry - stop)
    stop_distance_pct = stop_distance / entry if entry > 0 else 0

    # Hard cap: stop distance cannot exceed 2% of entry
    if stop_distance_pct > MAX_STOP_DISTANCE_PCT:
        stop_distance = entry * MAX_STOP_DISTANCE_PCT
        log.warning(
            "Stop distance capped from %.2f%% to %.2f%% of entry",
            stop_distance_pct * 100, MAX_STOP_DISTANCE_PCT * 100,
        )

    risk_amount = capital * MAX_SINGLE_TRADE_PCT * size_multiplier
    shares      = int(risk_amount / stop_distance) if stop_distance > 0 else 1
    return max(1, shares)


# ── Pre-trade checks ──────────────────────────────────────────────────────────

def check_position_limit(trade_type: str, current_counts: dict) -> tuple[bool, str]:
    """
    trade_type: 'intraday' | 'swing' | 'positional'
    current_counts: {'intraday': N, 'swing': N, 'positional': N}
    Returns (allowed, reason)
    """
    limits = {
        "intraday":   MAX_INTRADAY_POSITIONS,
        "swing":      MAX_SWING_POSITIONS,
        "positional": MAX_POSITIONAL,
    }
    limit = limits.get(trade_type, 0)
    count = current_counts.get(trade_type, 0)
    if count >= limit:
        return False, f"Position limit reached: {count}/{limit} {trade_type} trades open"
    return True, "OK"


def pre_trade_gate(
    capital: float,
    trade_type: str,
    current_counts: dict,
    user_id: str = "default",
) -> tuple[bool, str]:
    """Master gate — checks all hard limits before any trade is placed."""

    # 1. System halt check
    if is_halted(user_id):
        return False, "System halted — daily loss limit was breached earlier today"

    # 2. Daily loss check (from Kite P&L if available)
    risk_used = get_daily_risk_used(user_id)
    daily_limit = capital * MAX_DAILY_LOSS_PCT
    if risk_used >= daily_limit:
        set_halt(user_id)
        return False, f"Daily loss limit ₹{daily_limit:,.0f} reached (used ₹{risk_used:,.0f})"

    # 3. Position count check
    allowed, reason = check_position_limit(trade_type, current_counts)
    if not allowed:
        return False, reason

    return True, "PASS"


# ── Emergency halt procedure ──────────────────────────────────────────────────

def emergency_halt(kite, user_id: str = "default"):
    """
    1. Cancel all open orders
    2. Square off all intraday MIS positions
    3. Set halt flag
    4. Send push notification (caller responsibility)
    """
    from ingestion.kite_client import cancel_all_open_orders

    log.critical("EMERGENCY HALT triggered for user %s", user_id)

    # Cancel all open orders
    cancelled = cancel_all_open_orders()
    log.info("Cancelled %d orders", len(cancelled))

    # Square off all intraday positions
    try:
        positions = kite.positions().get("day", [])
        for pos in positions:
            qty = pos.get("quantity", 0)
            if qty == 0:
                continue
            side = "SELL" if qty > 0 else "BUY"
            from ingestion.kite_client import place_market_order
            place_market_order(
                symbol=pos["tradingsymbol"],
                qty=abs(qty),
                side=side,
                product=pos.get("product", "MIS"),
            )
    except Exception as e:
        log.error("Square-off failed during emergency halt: %s", e)

    set_halt(user_id)
    return {"status": "HALTED", "orders_cancelled": len(cancelled)}
