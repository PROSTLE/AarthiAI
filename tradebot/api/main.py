"""
api/main.py
FastAPI backend — serves signals, handles mood, WebSocket live push.
"""
import logging
import asyncio
import json
from datetime import datetime, date
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis

from config import SECRETS
from behavioral.mood import Mood, set_mood, get_trade_mode
from risk.guardrails import is_halted, pre_trade_gate

log = logging.getLogger(__name__)

app = FastAPI(
    title="AarthiAI TradeBot API",
    version="1.0.0",
    description="Real-time trade signals and AutoTrade control for NSE/BSE",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_r = redis.Redis(
    host=SECRETS.get("redis", {}).get("host", "localhost"),
    port=SECRETS.get("redis", {}).get("port", 6379),
    decode_responses=True,
)

# WebSocket connection registry
_ws_clients: dict[str, list[WebSocket]] = {}


# ── Pydantic models ───────────────────────────────────────────────────────────

class MoodRequest(BaseModel):
    user_id: str
    mood: Mood

class TradeRequest(BaseModel):
    user_id:    str
    ticker:     str
    signal:     str        # "LONG" or "SHORT"
    entry:      float
    stop:       float
    target:     float
    trade_type: str = "intraday"

class ScanRequest(BaseModel):
    user_id: str = "default"
    language: str = "en"


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


# ── Mood endpoints ────────────────────────────────────────────────────────────

@app.post("/api/mood")
def capture_mood(req: MoodRequest):
    """Set today's mood from the morning UI tap."""
    mode = set_mood(req.user_id, req.mood)
    return {
        "user_id":     req.user_id,
        "mood":        req.mood,
        "trade_mode":  mode.name,
        "auto_entry":  mode.auto_entry,
        "auto_exit":   mode.auto_exit,
        "confidence_threshold": mode.confidence_threshold,
    }

@app.get("/api/mood/{user_id}")
def get_mood_status(user_id: str):
    from behavioral.mood import get_mood
    mood = get_mood(user_id)
    return {"user_id": user_id, "mood": mood.value, "date": str(date.today())}


# ── Signal endpoints ──────────────────────────────────────────────────────────

@app.get("/api/signals/latest")
def get_latest_signals(user_id: str = "default"):
    """Returns cached signals from today's 9:15 AM scan."""
    key  = f"signals:{date.today().isoformat()}"
    data = _r.get(key)
    if not data:
        return {"signals": None, "message": "No scan has run today. Check at 9:15 AM IST."}
    return json.loads(data)

@app.get("/api/brief")
def get_daily_brief(user_id: str = "default", language: str = "en"):
    """Returns today's Daily Signal Brief text."""
    key  = f"brief:{user_id}:{date.today().isoformat()}"
    data = _r.get(key)
    if not data:
        return {"brief": None, "message": "Brief not yet generated."}
    return {"brief": data, "language": language}

@app.post("/api/scan")
async def trigger_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    """Manually trigger a pre-market scan (e.g. for testing)."""
    background_tasks.add_task(_run_scan_background, req.user_id, req.language)
    return {"status": "scan_started", "user_id": req.user_id}

async def _run_scan_background(user_id: str, language: str):
    try:
        from ingestion.nse_data import (
            get_fii_dii, get_options_pcr, get_global_cues,
            get_sector_momentum, get_news_headlines
        )
        from signals.signal_engine import run_premarket_scan
        from signals.brief_generator import generate_brief, generate_brief_json
        from behavioral.mood import get_trade_mode

        context = {
            "fii":              get_fii_dii(),
            "nifty_pcr":        get_options_pcr("NIFTY"),
            "global_cues":      get_global_cues(),
            "sector_momentum":  get_sector_momentum(),
            "headlines":        get_news_headlines(),
        }
        signals    = run_premarket_scan(context)
        mode       = get_trade_mode(user_id, 100_000)  # placeholder capital
        brief_text = generate_brief(signals, mode, language)
        brief_json = generate_brief_json(signals, mode)

        # Cache results
        today = str(date.today())
        _r.set(f"signals:{today}",           json.dumps(brief_json),  ex=86400)
        _r.set(f"brief:{user_id}:{today}",   brief_text,              ex=86400)

        # Push to WebSocket clients
        await _broadcast(user_id, brief_json)

        # Firebase push notification
        _push_notification(user_id, brief_json)

    except Exception as e:
        log.error("Background scan failed: %s", e)


# ── Trade endpoints ───────────────────────────────────────────────────────────

@app.post("/api/trade/execute")
def execute_trade_endpoint(req: TradeRequest):
    """
    Manual or semi-auto trade execution.
    Always goes through full guardrails.
    """
    try:
        capital = _get_capital(req.user_id)
    except Exception:
        capital = 100_000.0   # fallback for testing

    mode = get_trade_mode(req.user_id, capital)

    if mode.paused:
        raise HTTPException(status_code=403, detail="AutoTrade paused — mood is OUT")

    from execution.order_manager import execute_trade
    result = execute_trade(
        ticker=req.ticker,
        signal=req.signal,
        entry_price=req.entry,
        stop_price=req.stop,
        target_price=req.target,
        capital=capital,
        trade_type=req.trade_type,
        size_multiplier=mode.position_size_multiplier,
        user_id=req.user_id,
    )
    return result

@app.get("/api/trade/positions/{user_id}")
def get_open_positions(user_id: str):
    """Returns today's open trades from Redis."""
    keys   = _r.keys(f"trade:{user_id}:*")
    trades = [json.loads(_r.get(k)) for k in keys if _r.get(k)]
    return {"positions": trades, "count": len(trades)}


# ── Risk status ───────────────────────────────────────────────────────────────

@app.get("/api/risk/status/{user_id}")
def get_risk_status(user_id: str):
    from risk.guardrails import get_daily_risk_used
    try:
        capital = _get_capital(user_id)
    except Exception:
        capital = 100_000.0

    from config import RISK
    daily_limit = capital * RISK.get("max_daily_loss_pct", 0.02) / 100
    risk_used   = get_daily_risk_used(user_id)
    return {
        "halted":        is_halted(user_id),
        "capital":       capital,
        "daily_limit":   round(daily_limit, 2),
        "risk_used":     round(risk_used, 2),
        "risk_remaining": round(max(0, daily_limit - risk_used), 2),
        "date":           str(date.today()),
    }


# ── Behavioral ────────────────────────────────────────────────────────────────

@app.get("/api/user/{user_id}/archetype")
def get_user_archetype(user_id: str):
    try:
        from behavioral.profiler import classify_user
        import numpy as np
        # In production: load the user's actual interaction vector from DB
        dummy_vector = np.zeros(100)
        archetype = classify_user(dummy_vector)
        return {"user_id": user_id, "archetype": archetype}
    except Exception as e:
        return {"user_id": user_id, "archetype": "unknown", "error": str(e)}


# ── WebSocket live signal push ────────────────────────────────────────────────

@app.websocket("/ws/signals/{user_id}")
async def ws_signals(websocket: WebSocket, user_id: str):
    await websocket.accept()
    _ws_clients.setdefault(user_id, []).append(websocket)
    log.info("WebSocket client connected: %s", user_id)
    try:
        while True:
            # Keep alive — real data pushed via _broadcast()
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "ts": datetime.now().isoformat()})
    except WebSocketDisconnect:
        _ws_clients.get(user_id, []).remove(websocket)
        log.info("WebSocket client disconnected: %s", user_id)


async def _broadcast(user_id: str, data: dict):
    dead = []
    for ws in _ws_clients.get(user_id, []):
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for d in dead:
        _ws_clients.get(user_id, []).remove(d)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_capital(user_id: str) -> float:
    from ingestion.kite_client import get_available_capital
    return get_available_capital()


def _push_notification(user_id: str, brief_json: dict):
    try:
        import firebase_admin
        from firebase_admin import messaging, credentials
        if not firebase_admin._apps:
            cred = credentials.Certificate(SECRETS.get("firebase", {}).get("credentials_path", ""))
            firebase_admin.initialize_app(cred)

        top3 = brief_json.get("top_signals", [])
        body = " | ".join(
            f"{s['ticker']} {s['signal']} ({s['confidence']:.0f}%)" for s in top3
        ) or "No signals today"

        msg = messaging.Message(
            notification=messaging.Notification(
                title="AarthiAI — 9:15 AM Signal Brief",
                body=body,
            ),
            topic=f"user_{user_id}",
        )
        messaging.send(msg)
    except Exception as e:
        log.warning("Firebase push failed: %s", e)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8001, reload=True)
