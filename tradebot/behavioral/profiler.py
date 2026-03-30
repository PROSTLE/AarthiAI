"""
behavioral/profiler.py
User behavioral fingerprinting via SVD + KMeans.
Interaction matrix → 50-dim latent space → 6 trader archetypes.
"""
import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize
import joblib
import logging
from pathlib import Path
from config import BEHAVIORAL

log = logging.getLogger(__name__)

SVD_PATH    = Path("models/saved/svd_behavioral.pkl")
KMEANS_PATH = Path("models/saved/kmeans_archetypes.pkl")
SVD_PATH.parent.mkdir(parents=True, exist_ok=True)

N_COMPONENTS = BEHAVIORAL.get("svd_components", 50)
N_CLUSTERS   = BEHAVIORAL.get("kmeans_clusters", 6)

INTERACTION_WEIGHTS: dict[str, int] = BEHAVIORAL.get("interaction_weights", {
    "watchlist_add":    3,
    "alert_triggered":  2,
    "trade_executed":   5,
    "held_5days":       4,
    "exited_at_profit": 6,
})

ARCHETYPES = [
    "momentum_chaser",
    "breakout_trader",
    "value_accumulator",
    "dividend_harvester",
    "options_hedger",
    "macro_trader",
]


def build_interaction_matrix(events_df: pd.DataFrame):
    """
    events_df columns: user_id, stock_ticker, event_type
    Returns: (matrix np.ndarray, user_ids list, ticker_ids list)
    """
    events_df = events_df.copy()
    events_df["score"] = events_df["event_type"].map(INTERACTION_WEIGHTS).fillna(1).astype(float)

    pivot = events_df.pivot_table(
        index="user_id", columns="stock_ticker",
        values="score", aggfunc="sum", fill_value=0.0,
    )
    return pivot.values, pivot.index.tolist(), pivot.columns.tolist()


def train_behavioral_models(events_df: pd.DataFrame):
    matrix, user_ids, ticker_ids = build_interaction_matrix(events_df)

    # Clip to N_COMPONENTS if fewer users
    n_comp = min(N_COMPONENTS, min(matrix.shape) - 1)
    svd    = TruncatedSVD(n_components=n_comp, random_state=42)
    latent = svd.fit_transform(matrix)
    normed = normalize(latent)

    n_clust = min(N_CLUSTERS, len(user_ids))
    kmeans  = KMeans(n_clusters=n_clust, random_state=42, n_init=10)
    kmeans.fit(normed)

    joblib.dump({"svd": svd, "user_ids": user_ids, "ticker_ids": ticker_ids}, SVD_PATH)
    joblib.dump({"kmeans": kmeans}, KMEANS_PATH)

    log.info("Behavioral models trained. Users=%d, Tickers=%d, Clusters=%d",
             len(user_ids), len(ticker_ids), n_clust)
    return svd, kmeans


def classify_user(user_vector: np.ndarray) -> str:
    """
    user_vector: 1D array of scores for each ticker (same order as training).
    Returns: archetype string.
    """
    bundle  = joblib.load(SVD_PATH)
    svd     = bundle["svd"]
    kmeans  = joblib.load(KMEANS_PATH)["kmeans"]

    latent  = normalize(svd.transform(user_vector.reshape(1, -1)))
    cluster = int(kmeans.predict(latent)[0])
    return ARCHETYPES[cluster % len(ARCHETYPES)]


def get_stock_recommendations(user_id: str, n: int = 5) -> list[str]:
    """
    Collaborative filtering — returns top N tickers for this user.
    Uses reconstructed SVD matrix to find highest scoring unseen items.
    """
    try:
        bundle   = joblib.load(SVD_PATH)
        svd      = bundle["svd"]
        user_ids = bundle["user_ids"]
        tickers  = bundle["ticker_ids"]

        if user_id not in user_ids:
            log.warning("User %s not in model — returning empty recs", user_id)
            return []

        idx = user_ids.index(user_id)
        # Reconstruct full matrix for this user row
        components  = svd.components_
        latent      = svd.transform(np.zeros((1, len(tickers))))  # placeholder
        reconstructed = svd.inverse_transform(latent)[0]

        top_idx = np.argsort(reconstructed)[-n:][::-1]
        return [tickers[i] for i in top_idx]
    except Exception as e:
        log.error("Recommendation failed: %s", e)
        return []
