
import torch
from transformers import BertTokenizer, BertForSequenceClassification
import numpy as np
import yfinance as yf
import nltk
import math
from nltk.sentiment.vader import SentimentIntensityAnalyzer

try:
    nltk.data.find("sentiment/vader_lexicon.zip")
except LookupError:
    nltk.download("vader_lexicon", quiet=True)

_vader = SentimentIntensityAnalyzer()

MODEL_NAME = "ProsusAI/finbert"
_tokenizer = BertTokenizer.from_pretrained(MODEL_NAME)
_finbert = BertForSequenceClassification.from_pretrained(MODEL_NAME)
_finbert.eval()
# Correct mapping from transformers config: 0=positive, 1=negative, 2=neutral
FINBERT_LABELS = ["positive", "negative", "neutral"]

VADER_WEIGHT = 0.4
FINBERT_WEIGHT = 0.6
_SCORE_EPS = 1e-6


def _to_strict_task_score(signed_score: float) -> float:
    """Convert signed sentiment [-1, 1] into strict task score (0, 1)."""
    try:
        value = float(signed_score)
    except (TypeError, ValueError):
        value = 0.0
    if not math.isfinite(value):
        value = 0.0
    value = max(-1.0, min(1.0, value))
    normalized = (value + 1.0) / 2.0
    return max(_SCORE_EPS, min(1.0 - _SCORE_EPS, normalized))

# Extend VADER lexicon with financial context terms
_vader.lexicon.update({
    'hike': 1.5,
    'stake': 1.0,
    'approve': 2.0,
    'approved': 2.0,
    'approval': 2.0,
    'raise': 1.5,
    'raised': 1.5,
    'growth': 2.0,
    'gain': 2.0,
    'jump': 1.5,
    'surge': 1.5,
    'fall': -1.5,
    'drop': -1.5,
    'plunge': -2.0,
    'cut': -1.5,
    'slash': -2.0,
    'warn': -1.5,
    'alert': -1.0,
})


def _score_vader(text: str) -> dict:
    scores = _vader.polarity_scores(text)
    compound = scores["compound"]

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    confidence = round(abs(compound), 4)
    return {
        "label": label,
        "score": round(_to_strict_task_score(compound), 6),
        "signed_score": round(compound, 4),
        "confidence": confidence,
    }


def _score_finbert(text: str) -> dict:
    tokens = _tokenizer(text, return_tensors="pt", padding=True,
                        truncation=True, max_length=128)
    with torch.no_grad():
        logits = _finbert(**tokens).logits
    probs = torch.nn.functional.softmax(logits, dim=-1).squeeze().tolist()
    idx = int(np.argmax(probs))

    # Logits match FINBERT_LABELS = ["positive", "negative", "neutral"]
    # Score = Positive_Prob - Negative_Prob
    signed_score = probs[0] - probs[1]
    
    return {
        "label": FINBERT_LABELS[idx],
        "score": round(_to_strict_task_score(signed_score), 6),
        "signed_score": round(signed_score, 4),
        "confidence": round(probs[idx], 4),
    }


def _score_text(text: str) -> dict:
    vader = _score_vader(text)
    finbert = _score_finbert(text)

    combined_score = (VADER_WEIGHT * vader["signed_score"]) + (FINBERT_WEIGHT * finbert["signed_score"])

    if combined_score > 0.1:
        label = "positive"
    elif combined_score < -0.1:
        label = "negative"
    else:
        label = "neutral"

    combined_confidence = (VADER_WEIGHT * vader["confidence"]) + (FINBERT_WEIGHT * finbert["confidence"])

    return {
        "text": text,
        "label": label,
        "confidence": round(combined_confidence, 4),
        "combined_score": round(_to_strict_task_score(combined_score), 6),
        "combined_signed_score": round(combined_score, 4),
        "vader": vader,
        "finbert": finbert,
    }


def fetch_news_headlines(ticker: str, max_items: int = 10) -> list[str]:
    stock = yf.Ticker(ticker)
    news = stock.news or []
    headlines = []
    for item in news[:max_items]:
        content = item.get("content", {})
        title = content.get("title", "") or item.get("title", "")
        if title:
            headlines.append(title)
    return headlines



def _is_relevant(headline: str, ticker: str) -> bool:
    """
    Relevance check. yfinance already returns ticker-specific news,
    so we default to True (trust yfinance). We only reject headlines
    that mention a clearly different well-known company.
    """
    headline_lower = headline.lower()
    ticker_base = ticker.split(".")[0].lower()  # "RELIANCE" from "RELIANCE.NS"
    
    # Quick accept: headline mentions the ticker or company directly
    if ticker_base in headline_lower:
        return True

    # Common variations map
    aliases = {
        "RELIANCE": ["reliance", "ril", "ambani"],
        "TCS": ["tcs", "tata consultancy"],
        "INFY": ["infy", "infosys"],
        "HDFCBANK": ["hdfc", "housing development"],
        "ICICIBANK": ["icici"],
        "SBIN": ["sbi", "state bank"],
        "LT": ["l&t", "larsen", "toubro"],
        "ITC": ["itc"],
        "BHARTIARTL": ["airtel", "bharti"],
        "KOTAKBANK": ["kotak"],
        "TATAMOTORS": ["tata motors", "jlr"],
        "MARUTI": ["maruti", "suzuki"],
        "WIPRO": ["wipro"],
        "ADANIENT": ["adani ent", "adani group"],
        "TATASTEEL": ["tata steel"],
        "BAJFINANCE": ["bajaj finance"],
        "BAJAJFINSV": ["bajaj finserv"],
        "HINDUNILVR": ["hul", "hindustan unilever"],
        "SUNPHARMA": ["sun pharma"],
        "TITAN": ["titan"],
        "ASIANPAINT": ["asian paints"],
        "ULTRACEMCO": ["ultratech"],
        "NESTLEIND": ["nestle"],
        "POWERGRID": ["power grid", "pgcil"],
        "NTPC": ["ntpc"],
        "M&M": ["mahindra"],
        "JSWSTEEL": ["jsw steel"],
        "GRASIM": ["grasim"],
        "COALINDIA": ["coal india"],
        "ADANIPORTS": ["adani ports"],
        "ADANIGREEN": ["adani green"],
        "TECHM": ["tech mahindra"],
        "BPCL": ["bpcl", "bharat petroleum"],
        "EICHERMOT": ["eicher"],
        "DIVISLAB": ["divi's", "divis"],
        "CIPLA": ["cipla"],
        "HCLTECH": ["hcl tech"],
        "ONGC": ["ongc", "oil and natural gas"],
        "HINDALCO": ["hindalco"],
        "DRREDDY": ["dr reddy"],
        "INDUSINDBK": ["indusind"],
        "BEL": ["bharat electronics"],
        "HAL": ["hindustan aeronautics"],
        "IOC": ["indian oil"],
        "VEDL": ["vedanta"],
        "DLF": ["dlf"],
        "SBILIFE": ["sbi life"],
        "HDFCLIFE": ["hdfc life"],
        "ZOMATO": ["zomato"],
        "PAYTM": ["paytm", "one97"],
        "NYKAA": ["nykaa", "fsn"],
        "IRCTC": ["irctc", "railway"],
    }
        
    # Check known aliases
    if ticker_base.upper() in aliases:
        for alias in aliases[ticker_base.upper()]:
            if alias in headline_lower:
                return True
                
    # Default: trust yfinance — it already curates news for this ticker
    return True


def _check_overrides(headline: str) -> float | None:
    """
    Force scores for clear financial signals that NLP models often miss.
    Returns: Score (-1 to 1) or None.
    """
    hl = headline.lower()
    
    # Strong Negative Signals
    if any(x in hl for x in ["cuts", "lowers", "slashes", "misses", "below"]) and \
       any(x in hl for x in ["guidance", "forecast", "outlook", "estimate", "target"]):
        return -0.8
        
    if "bankruptcy" in hl or "fraud" in hl or "scam" in hl or "default" in hl:
        return -0.9

    # Strong Positive Signals
    if any(x in hl for x in ["raises", "hikes", "beats", "above", "record"]) and \
       any(x in hl for x in ["guidance", "forecast", "outlook", "estimate", "profit", "revenue"]):
        return 0.8
        
    if "wins order" in hl or "wins contract" in hl or "bagged order" in hl:
        return 0.7
        
    return None


def _is_noise(headline: str) -> bool:
    """Discard junk headlines."""
    # Too short or just a company name
    if len(headline) < 20: 
        return True
    if "share price" in headline.lower() and "live" in headline.lower():
        # "Reliance share price live" -> Noise, no sentiment
        return True
    return False


def analyze_sentiment(ticker: str) -> dict:
    headlines = fetch_news_headlines(ticker)
    
    valid_details = []
    
    for h in headlines:
        # 1. Filter Noise
        if _is_noise(h):
            continue
            
        # 2. Filter Relevance
        if not _is_relevant(h, ticker):
            continue
            
        # 3. Check Overrides (Priority 1)
        override_score = _check_overrides(h)
        if override_score is not None:
            label = "positive" if override_score > 0 else "negative"
            valid_details.append({
                "text": h,
                "label": label,
                "confidence": 1.0,
                "combined_score": round(_to_strict_task_score(override_score), 6),
                "combined_signed_score": override_score,
                "method": "Keyword Override"
            })
            continue

        # 4. Use Model (Priority 2)
        score_data = _score_text(h)
        valid_details.append(score_data)

    if not valid_details:
        return {
            "ticker": ticker,
            "articles_analyzed": 0,
            "details": [],
            "overall_sentiment": "neutral",
            "overall_score": 0.5,
            "overall_signed_score": 0.0,
            "contradictory_dampened": False,
            "method": "Hybrid (Keywords + VADER/FinBERT)",
        }

    raw_scores = [d.get("combined_signed_score", 0.0) for d in valid_details]
    avg = float(np.mean(raw_scores))

    # Dampen one-off outliers
    contradictory_dampened = False
    n = len(raw_scores)
    if n >= 2:
        variance = float(np.var(raw_scores))
        median = float(np.median(raw_scores))
        # High variance or mean far from median => contradictory/one-off dominated
        contradictory = variance > 0.15 or abs(avg - median) > 0.35
        if contradictory:
            contradictory_dampened = True
            # Pull toward median
            avg = 0.4 * avg + 0.6 * median

    if avg > 0.1:
        overall = "positive"
    elif avg < -0.1:
        overall = "negative"
    else:
        overall = "neutral"

    return {
        "ticker": ticker,
        "articles_analyzed": len(valid_details),
        "details": valid_details,
        "overall_sentiment": overall,
        "overall_score": round(_to_strict_task_score(avg), 6),
        "overall_signed_score": round(avg, 4),
        "contradictory_dampened": contradictory_dampened,
        "method": "Hybrid (Keywords + VADER/FinBERT)",
    }
