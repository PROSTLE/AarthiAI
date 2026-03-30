"""
features/sector_heat.py
Sector Heat Score computation — 5-factor weighted formula.
"""
import numpy as np
from scipy import stats
from config import SECTOR


W = SECTOR.get("weights", {
    "news_sentiment": 0.25,
    "fii_flow": 0.20,
    "price_momentum": 0.20,
    "global_correlation": 0.20,
    "options_pcr": 0.15,
})
PCR_BULL = SECTOR.get("pcr_bullish_above", 1.2)
PCR_BEAR = SECTOR.get("pcr_bearish_below", 0.8)


def _norm_range(v: float, lo: float = -3.0, hi: float = 3.0) -> float:
    """Clamp a z-score range to [0, 1]."""
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _pcr_to_signal(pcr: float) -> float:
    """Maps raw PCR → 0 (bearish) to 1 (bullish)."""
    if pcr >= PCR_BULL:
        return 1.0
    if pcr <= PCR_BEAR:
        return 0.0
    return (pcr - PCR_BEAR) / (PCR_BULL - PCR_BEAR)


def compute_sector_heat(
    news_sentiment: float,       # -1 to +1 (from FinBERT aggregation)
    fii_flow_crore: float,       # raw FII net flow in Crore
    sector_return_5d: float,     # 5-day % return of sector index
    global_change_pct: float,    # weighted global futures change %
    pcr: float,                  # Nifty PCR from options chain
    fii_history: list[float] | None = None,   # last 20 days FII for z-scoring
    momentum_history: list[float] | None = None,  # last 20 sectors' 5d returns
) -> float:
    """
    Returns Sector Heat Score 0–100.
    Heat = 0.25*news + 0.20*fii_norm + 0.20*momentum_z + 0.20*global + 0.15*pcr
    """
    # News sentiment: -1..+1 → 0..1
    news_01 = (news_sentiment + 1) / 2

    # FII flow: z-score within historical distribution
    if fii_history and len(fii_history) >= 5:
        fii_z    = (fii_flow_crore - np.mean(fii_history)) / (np.std(fii_history) + 1e-9)
        fii_01   = _norm_range(fii_z)
    else:
        fii_01 = 0.5 + (fii_flow_crore / 10_000)   # naive: ±10,000 Cr maps to ≈0..1
        fii_01 = max(0.0, min(1.0, fii_01))

    # Sector momentum: z-score
    if momentum_history and len(momentum_history) >= 5:
        mom_z = (sector_return_5d - np.mean(momentum_history)) / (np.std(momentum_history) + 1e-9)
        mom_01 = _norm_range(mom_z)
    else:
        mom_01 = max(0.0, min(1.0, (sector_return_5d + 10) / 20))  # ±10% maps 0..1

    # Global cues: % change → normalise around ±2%
    global_01 = max(0.0, min(1.0, (global_change_pct + 2) / 4))

    # PCR signal
    pcr_01 = _pcr_to_signal(pcr)

    raw = (
        W["news_sentiment"]   * news_01   +
        W["fii_flow"]         * fii_01    +
        W["price_momentum"]   * mom_01    +
        W["global_correlation"] * global_01 +
        W["options_pcr"]      * pcr_01
    )
    return round(raw * 100, 2)


def rank_sectors(sector_heat_map: dict[str, float]) -> list[dict]:
    """Returns sectors sorted by heat score descending."""
    return sorted(
        [{"sector": k, "heat": v} for k, v in sector_heat_map.items()],
        key=lambda x: x["heat"],
        reverse=True,
    )


def compute_confidence_score(
    ml_prob: float,
    tech_score: float,
    sector_heat: float,
    fundamental_score: float,
    sentiment_score: float,
) -> float:
    """
    Composite Confidence Score 0–100.
    AutoTrade Semi-Auto fires > 75, Full AutoTrade fires > 82.
    """
    from config import CONFIDENCE
    W = CONFIDENCE.get("weights", {
        "ml_model": 0.30, "technical": 0.25, "sector_heat": 0.20,
        "fundamental": 0.15, "sentiment": 0.10,
    })

    raw = (
        W["ml_model"]    * max(0.0, min(1.0, ml_prob))             +
        W["technical"]   * max(0.0, min(1.0, tech_score))          +
        W["sector_heat"] * max(0.0, min(1.0, sector_heat / 100))   +
        W["fundamental"] * max(0.0, min(1.0, fundamental_score))   +
        W["sentiment"]   * max(0.0, min(1.0, sentiment_score))
    )
    return round(raw * 100, 2)
