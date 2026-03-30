"""
behavioral/mood.py
Daily mood capture → TradeMode mapping.
Storage: mood persisted in Redis keyed by user_id + date.
"""
from dataclasses import dataclass, field
from enum import Enum
import redis
import json
from datetime import date
from config import SECRETS, CONFIDENCE

_r = redis.Redis(
    host=SECRETS.get("redis", {}).get("host", "localhost"),
    port=SECRETS.get("redis", {}).get("port", 6379),
    decode_responses=True,
)


class Mood(str, Enum):
    FOCUSED    = "focused"
    BUSY       = "busy"
    TIRED      = "tired"
    OUT        = "out"
    AGGRESSIVE = "aggressive"


@dataclass
class TradeMode:
    name:                    str
    auto_entry:              bool
    auto_exit:               bool
    confidence_threshold:    float
    position_size_multiplier: float
    max_trades:              int
    paused:                  bool = False
    remaining_budget:        float = 0.0   # filled at runtime


MOOD_CONFIG: dict[Mood, TradeMode] = {
    Mood.FOCUSED: TradeMode(
        name="Supervised",
        auto_entry=False, auto_exit=False,
        confidence_threshold=CONFIDENCE.get("semiauto_threshold", 75),
        position_size_multiplier=1.0, max_trades=5,
    ),
    Mood.BUSY: TradeMode(
        name="Semi-Auto",
        auto_entry=True, auto_exit=False,
        confidence_threshold=CONFIDENCE.get("semiauto_threshold", 75),
        position_size_multiplier=1.0, max_trades=5,
    ),
    Mood.TIRED: TradeMode(
        name="Full AutoTrade",
        auto_entry=True, auto_exit=True,
        confidence_threshold=CONFIDENCE.get("fullauto_threshold", 82),
        position_size_multiplier=1.0, max_trades=3,
    ),
    Mood.OUT: TradeMode(
        name="Paused — Portfolio Monitor",
        auto_entry=False, auto_exit=False,
        confidence_threshold=999, position_size_multiplier=0,
        max_trades=0, paused=True,
    ),
    Mood.AGGRESSIVE: TradeMode(
        name="Semi-Auto Aggressive",
        auto_entry=True, auto_exit=False,
        confidence_threshold=CONFIDENCE.get("aggressive_threshold", 68),
        position_size_multiplier=1.5, max_trades=5,
    ),
}


def set_mood(user_id: str, mood: Mood) -> TradeMode:
    key   = f"mood:{user_id}:{date.today().isoformat()}"
    _r.set(key, mood.value, ex=86400)
    return MOOD_CONFIG[mood]


def get_mood(user_id: str) -> Mood:
    key = f"mood:{user_id}:{date.today().isoformat()}"
    val = _r.get(key)
    if val and val in Mood._value2member_map_:
        return Mood(val)
    return Mood.FOCUSED   # safe default


def get_trade_mode(user_id: str, capital: float) -> TradeMode:
    mood = get_mood(user_id)
    mode = MOOD_CONFIG[mood]
    # Attach remaining budget
    from risk.guardrails import get_daily_risk_used
    used = get_daily_risk_used(user_id)
    from config import RISK
    daily_limit = capital * RISK.get("max_daily_loss_pct", 0.02)
    mode.remaining_budget = max(0.0, daily_limit - used)
    return mode
