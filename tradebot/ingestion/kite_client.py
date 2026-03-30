"""
ingestion/kite_client.py
Zerodha KiteConnect wrapper — live ticks → Redis stream, order placement.
"""
import logging
import redis
import json
import time
from kiteconnect import KiteConnect, KiteTicker
from config import SECRETS, MARKET

log = logging.getLogger(__name__)

_secrets = SECRETS.get("kite", {})
API_KEY      = _secrets.get("api_key", "")
ACCESS_TOKEN = _secrets.get("access_token", "")

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(ACCESS_TOKEN)

_redis = redis.Redis(
    host=SECRETS.get("redis", {}).get("host", "localhost"),
    port=SECRETS.get("redis", {}).get("port", 6379),
    decode_responses=True,
)


# ── Tick streaming ────────────────────────────────────────────────────────────

def build_ticker(instrument_tokens: list[int]) -> KiteTicker:
    ticker = KiteTicker(API_KEY, ACCESS_TOKEN)

    def on_connect(ws, response):
        log.info("KiteTicker connected — subscribing %d instruments", len(instrument_tokens))
        ws.subscribe(instrument_tokens)
        ws.set_mode(ws.MODE_FULL, instrument_tokens)

    def on_ticks(ws, ticks):
        pipe = _redis.pipeline()
        for tick in ticks:
            key = f"ticks:{tick['instrument_token']}"
            pipe.xadd(key, {
                "ltp":       str(tick.get("last_price", 0)),
                "volume":    str(tick.get("volume_traded", 0)),
                "oi":        str(tick.get("oi", 0)),
                "bid":       str(tick.get("depth", {}).get("buy", [{}])[0].get("price", 0)),
                "ask":       str(tick.get("depth", {}).get("sell", [{}])[0].get("price", 0)),
                "timestamp": str(tick.get("timestamp", "")),
            }, maxlen=10_000)
        pipe.execute()

    def on_error(ws, code, reason):
        log.error("KiteTicker error %s: %s", code, reason)

    def on_close(ws, code, reason):
        log.warning("KiteTicker closed %s: %s", code, reason)

    ticker.on_connect = on_connect
    ticker.on_ticks   = on_ticks
    ticker.on_error   = on_error
    ticker.on_close   = on_close
    return ticker


def get_latest_tick(instrument_token: int) -> dict | None:
    """Pull the most recent tick from Redis stream."""
    key = f"ticks:{instrument_token}"
    msgs = _redis.xrevrange(key, count=1)
    if not msgs:
        return None
    _, fields = msgs[0]
    return {k: float(v) if k != "timestamp" else v for k, v in fields.items()}


# ── Instrument lookup ─────────────────────────────────────────────────────────

def get_instrument_token(symbol: str, exchange: str = "NSE") -> int | None:
    instruments = kite.instruments(exchange)
    for inst in instruments:
        if inst["tradingsymbol"] == symbol:
            return inst["instrument_token"]
    return None


def get_nse_instruments() -> list[dict]:
    return kite.instruments("NSE")


# ── Order utils ───────────────────────────────────────────────────────────────

def place_market_order(
    symbol: str,
    qty: int,
    side: str,                       # "BUY" or "SELL"
    product: str = "MIS",
) -> str:
    tx = kite.TRANSACTION_TYPE_BUY if side == "BUY" else kite.TRANSACTION_TYPE_SELL
    order_id = kite.place_order(
        tradingsymbol=symbol,
        exchange=kite.EXCHANGE_NSE,
        transaction_type=tx,
        quantity=qty,
        product=product,
        order_type=kite.ORDER_TYPE_MARKET,
        variety=kite.VARIETY_REGULAR,
    )
    log.info("Market order placed: %s %s x%d → order_id=%s", side, symbol, qty, order_id)
    return order_id


def place_limit_order(symbol: str, qty: int, side: str, price: float, product: str = "MIS") -> str:
    tx = kite.TRANSACTION_TYPE_BUY if side == "BUY" else kite.TRANSACTION_TYPE_SELL
    order_id = kite.place_order(
        tradingsymbol=symbol,
        exchange=kite.EXCHANGE_NSE,
        transaction_type=tx,
        quantity=qty,
        price=price,
        product=product,
        order_type=kite.ORDER_TYPE_LIMIT,
        variety=kite.VARIETY_REGULAR,
    )
    log.info("Limit order placed: %s %s x%d @ %.2f → order_id=%s", side, symbol, qty, price, order_id)
    return order_id


def place_gtt_oco(
    symbol: str,
    qty: int,
    side: str,           # "SELL" to exit a long
    stop: float,
    target: float,
    last_price: float,
    product: str = "MIS",
) -> int:
    """
    OCO GTT — one for stop-loss, one for target.
    Returns gtt_id. Must be called within 2 seconds of entry.
    """
    tx = kite.TRANSACTION_TYPE_SELL if side == "SELL" else kite.TRANSACTION_TYPE_BUY
    gtt_id = kite.place_gtt(
        trigger_type=kite.GTT_TYPE_OCO,
        tradingsymbol=symbol,
        exchange="NSE",
        trigger_values=[round(stop, 2), round(target, 2)],
        last_price=last_price,
        orders=[
            {"transaction_type": tx, "quantity": qty,
             "order_type": kite.ORDER_TYPE_LIMIT, "product": product, "price": round(stop, 2)},
            {"transaction_type": tx, "quantity": qty,
             "order_type": kite.ORDER_TYPE_LIMIT, "product": product, "price": round(target, 2)},
        ],
    )
    log.info("GTT OCO placed: %s stop=%.2f target=%.2f gtt_id=%s", symbol, stop, target, gtt_id)
    return gtt_id


def cancel_all_open_orders() -> list[str]:
    cancelled = []
    for order in kite.orders():
        if order["status"] in ("OPEN", "TRIGGER PENDING", "PENDING"):
            try:
                kite.cancel_order(order["variety"], order["order_id"])
                cancelled.append(order["order_id"])
            except Exception as e:
                log.error("Failed to cancel order %s: %s", order["order_id"], e)
    log.warning("Cancelled %d open orders", len(cancelled))
    return cancelled


def get_day_pnl() -> float:
    positions = kite.positions().get("day", [])
    return sum(p.get("unrealised", 0) + p.get("realised", 0) for p in positions)


def get_available_capital() -> float:
    margins = kite.margins()
    return float(margins.get("equity", {}).get("available", {}).get("cash", 0))
