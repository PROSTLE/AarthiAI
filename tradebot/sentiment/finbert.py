"""
sentiment/finbert.py
FinBERT sentiment scoring with exponential recency decay.
Model: ProsusAI/finbert → POSITIVE/NEGATIVE/NEUTRAL + confidence.
"""
import logging
import numpy as np
from datetime import datetime
from functools import lru_cache
from config import SENTIMENT

log = logging.getLogger(__name__)
HALF_LIFE_H = SENTIMENT.get("finbert_half_life_hours", 4.0)

_LABEL_MAP = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}


@lru_cache(maxsize=1)
def _get_pipeline():
    """Load FinBERT once and cache — first call takes ~30s."""
    from transformers import pipeline as hf_pipeline
    log.info("Loading ProsusAI/finbert — first call...")
    return hf_pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        tokenizer="ProsusAI/finbert",
        device=-1,          # cpu; set to 0 for cuda
        truncation=True,
        max_length=512,
    )


def score_headline(text: str) -> tuple[float, float]:
    """
    Returns (directional_score, confidence).
    directional_score: +1 (positive), -1 (negative), 0 (neutral) × confidence
    """
    try:
        pipe   = _get_pipeline()
        result = pipe(text[:512])[0]
        label  = result["label"].lower()
        conf   = float(result["score"])
        return _LABEL_MAP.get(label, 0.0) * conf, conf
    except Exception as e:
        log.warning("FinBERT score failed: %s", e)
        return 0.0, 0.0


def _parse_dt(published: str) -> datetime:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(published[:30], fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return datetime.utcnow()


def aggregate_ticker_sentiment(
    headlines: list[dict],
    ticker: str,
    half_life_hours: float = HALF_LIFE_H,
) -> float:
    """
    Weighted average sentiment for a ticker.
    Weight = exp(-λ * age_hours), λ = ln(2) / half_life.
    Returns score in [-1, +1].
    """
    lam = np.log(2) / half_life_hours
    now = datetime.utcnow()

    scores, weights = [], []
    clean_ticker = ticker.replace(".NS", "").replace(".BO", "").lower()

    for h in headlines:
        title = h.get("title", "")
        if clean_ticker not in title.lower() and clean_ticker not in h.get("summary", "").lower():
            continue
        score, conf = score_headline(title)
        if conf == 0.0:
            continue
        age_h  = max(0.0, (now - _parse_dt(h.get("published", ""))).total_seconds() / 3600)
        weight = np.exp(-lam * age_h)
        scores.append(score)
        weights.append(weight)

    if not scores:
        return 0.0
    return float(np.average(scores, weights=weights))


def batch_score_market(headlines: list[dict], tickers: list[str]) -> dict[str, float]:
    """Scores all tickers against the headline pool. Returns {ticker: score}."""
    return {t: aggregate_ticker_sentiment(headlines, t) for t in tickers}
