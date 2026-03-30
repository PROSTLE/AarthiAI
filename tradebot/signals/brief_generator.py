"""
signals/brief_generator.py
Daily Signal Brief — structured output at 9:15 AM.
Bilingual support via deep-translator.
"""
import logging
from datetime import datetime

try:
    import pendulum
    _now = lambda: pendulum.now("Asia/Kolkata")
except ImportError:
    _now = datetime.now

log = logging.getLogger(__name__)

SUPPORTED_LANGS = {"hi": "Hindi", "ta": "Tamil", "te": "Telugu", "mr": "Marathi"}


def _fmt_price(p: float) -> str:
    return f"₹{p:,.2f}"


def generate_brief(
    signals: dict,
    trade_mode,
    language: str = "en",
) -> str:
    """
    signals dict from signal_engine.run_premarket_scan()
    trade_mode: behavioral.mood.TradeMode instance
    """
    now_str  = _now().strftime("%a, %d %b %Y %H:%M") if not hasattr(_now(), "format") else _now().format("ddd, DD MMM YYYY HH:mm")
    lines    = []
    ctx      = signals.get("market_context", {})
    fii      = ctx.get("fii", {})
    gcues    = ctx.get("global_cues", {})
    pcr      = ctx.get("nifty_pcr", 1.0)

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        "═" * 56,
        "  AARTHAI TRADEBOT — DAILY SIGNAL BRIEF",
        f"  {now_str} IST",
        "═" * 56,
        "",
    ]

    # ── Market Context ────────────────────────────────────────────────────────
    dow_chg = gcues.get("dow_futures", {}).get("change_pct", 0)
    nas_chg = gcues.get("nasdaq_futures", {}).get("change_pct", 0)
    sgx_chg = gcues.get("sgx_nifty_proxy", {}).get("change_pct", 0)
    cru_chg = gcues.get("crude_oil", {}).get("change_pct", 0)
    usd_val = gcues.get("usd_inr", {}).get("price", 0)

    pcr_label = "Bullish" if pcr >= 1.2 else "Bearish" if pcr <= 0.8 else "Neutral"
    lines += [
        "📡  MARKET CONTEXT",
        f"  Global  : Dow {dow_chg:+.2f}% | Nasdaq {nas_chg:+.2f}% | SGX Nifty proxy {sgx_chg:+.2f}%",
        f"            Crude {cru_chg:+.2f}% | USD/INR {usd_val:.2f}",
        f"  FII/DII : FII Net {fii.get('fii_net', 0):+,.0f} Cr | DII Net {fii.get('dii_net', 0):+,.0f} Cr",
        f"  PCR     : {pcr:.3f} — {pcr_label}",
        "",
    ]

    # ── Sector Heat ───────────────────────────────────────────────────────────
    lines.append("🔥  TOP SECTOR HEAT SCORES")
    for s in (signals.get("sector_heats") or [])[:5]:
        bar = "█" * int(s["heat"] / 10)
        lines.append(f"  {s['sector']:<22} {bar:<10} {s['heat']:.1f}/100")
    lines.append("")

    # ── Intraday Picks ────────────────────────────────────────────────────────
    intraday = signals.get("intraday_picks", [])
    lines.append(f"⚡  INTRADAY PICKS  ({len(intraday)} signal{'s' if len(intraday) != 1 else ''})")
    if not intraday:
        lines.append("  No valid intraday setups found today.")
    for pick in intraday:
        rr   = pick.get("rr_ratio", 0)
        vsr  = pick.get("vsr", 0)
        conf = pick.get("confidence", 0)
        flag = "  ⚠ VSR EXTREME — reduce size" if pick.get("vsr_extreme_flag") else ""
        lines += [
            "",
            f"  ▶ {pick['ticker']}  [{pick['signal']}]  Confidence: {conf:.1f}/100",
            f"    Entry : {_fmt_price(pick['entry'])}   Stop : {_fmt_price(pick['stop'])}   Target : {_fmt_price(pick['target'])}",
            f"    RSI   : {pick['rsi']:.1f}   VSR : {vsr:.2f}x   RR : 1:{rr:.2f}   ATR : {_fmt_price(pick['atr'])}",
            f"    Why   : {pick.get('shap_reason', '—')}{flag}",
        ]
    lines.append("")

    # ── Swing Picks ───────────────────────────────────────────────────────────
    swing = signals.get("swing_picks", [])
    lines.append(f"📈  SWING PICKS  ({len(swing)} signal{'s' if len(swing) != 1 else ''})")
    if not swing:
        lines.append("  No swing setups above threshold today.")
    for pick in swing:
        lines += [
            "",
            f"  ▶ {pick['ticker']}",
            f"    EMA Structure : {pick.get('ema_structure', '—')}",
            f"    RS vs Sector  : {pick.get('rs', 0):+.2f}%",
            f"    10-Day Forecast: {pick.get('forecast_10d', 0):+.2f}%  Confidence: {pick.get('confidence', 0):.1f}",
            f"    Why : {pick.get('shap_reason', '—')}",
        ]
    lines.append("")

    # ── Positional ────────────────────────────────────────────────────────────
    pos = signals.get("positional_pick")
    lines.append("🏛  POSITIONAL OPPORTUNITY")
    if pos:
        lines += [
            f"  ▶ {pos['ticker']}",
            f"    F-Score : {pos.get('f_score', '—')}/9    Z-Score : {pos.get('z_score', 0):.2f}    ROE : {pos.get('roe', 0):.1f}%",
            f"    Sector  : {pos.get('sector', '—')}",
            f"    Why     : {pos.get('shap_reason', '—')}",
        ]
    else:
        lines.append("  No positional stock passed all fundamental gates today.")
    lines.append("")

    # ── AutoTrade Status ──────────────────────────────────────────────────────
    lines += [
        "⚙  AUTOTRADE STATUS",
        f"  Mode            : {trade_mode.name}",
        f"  Confidence Gate : {trade_mode.confidence_threshold}",
        f"  Size Multiplier : {trade_mode.position_size_multiplier}x",
        f"  Max Trades      : {trade_mode.max_trades}",
        f"  Risk Budget Left: {_fmt_price(trade_mode.remaining_budget)}",
        f"  Auto Entry      : {'YES' if trade_mode.auto_entry else 'NO — awaiting your approval'}",
        f"  Auto Exit       : {'YES' if trade_mode.auto_exit else 'NO — manual exit required'}",
        "",
        "═" * 56,
        "  Powered by AarthiAI TradeBot — for informational use.",
        "  Past signals do not guarantee future performance.",
        "═" * 56,
    ]

    brief = "\n".join(lines)

    # ── Translation ───────────────────────────────────────────────────────────
    if language != "en" and language in SUPPORTED_LANGS:
        try:
            from deep_translator import GoogleTranslator
            brief = GoogleTranslator(source="en", target=language).translate(brief)
        except Exception as e:
            log.warning("Translation to %s failed: %s", language, e)

    return brief


def generate_brief_json(signals: dict, trade_mode) -> dict:
    """
    Machine-readable version for the React Native app push payload.
    """
    intraday  = signals.get("intraday_picks", [])
    top3      = intraday[:3]
    pcr       = signals.get("market_context", {}).get("nifty_pcr", 1.0)

    return {
        "generated_at":  datetime.now().isoformat(),
        "autotrade_mode": trade_mode.name,
        "top_signals": [
            {
                "ticker":     p["ticker"],
                "signal":     p["signal"],
                "entry":      p["entry"],
                "stop":       p["stop"],
                "target":     p["target"],
                "confidence": p["confidence"],
                "reason":     p["shap_reason"],
            }
            for p in top3
        ],
        "market_sentiment": "bullish" if pcr >= 1.2 else "bearish" if pcr <= 0.8 else "neutral",
        "sector_heats": signals.get("sector_heats", [])[:3],
        "risk_budget":  trade_mode.remaining_budget,
    }
