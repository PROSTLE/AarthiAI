"""
inference.py — Hackathon Submission Entry Point
================================================
Aarthi AI: Multi-Signal Stock Intelligence Engine

Complies with hackathon pre-submission checklist:
  - All env vars: API_BASE_URL, MODEL_NAME, HF_TOKEN (optional: LOCAL_IMAGE_NAME)
  - Defaults ONLY for API_BASE_URL and MODEL_NAME (not HF_TOKEN)
  - All LLM calls use the OpenAI client (from openai import OpenAI)
  - Stdout logs follow the required structured format (START/STEP/END) exactly
  - from_docker_image() support via LOCAL_IMAGE_NAME env var
"""

import os
import sys
import json
import time

# ── Required environment variables (hackathon checklist) ──────────────────────
# Defaults ONLY for API_BASE_URL and MODEL_NAME — NOT for HF_TOKEN
API_BASE_URL = os.getenv("API_BASE_URL", "https://api-inference.huggingface.co/v1/")
MODEL_NAME   = os.getenv("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN     = os.getenv("HF_TOKEN")               # No default — must be set by user
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")   # Optional: used with from_docker_image()

# ── OpenAI client (required by hackathon rules) ───────────────────────────────
from openai import OpenAI

client = OpenAI(
    base_url=API_BASE_URL,
    api_key=HF_TOKEN if HF_TOKEN else "hf-",       # HF models use HF_TOKEN as the key
)


# ── Docker image helper (optional) ───────────────────────────────────────────
def from_docker_image():
    """
    Returns the local Docker image name if LOCAL_IMAGE_NAME env var is set.
    Used for containerised inference deployments.
    """
    image = os.getenv("LOCAL_IMAGE_NAME")
    if not image:
        return None
    return image


# ── Structured log helpers (START / STEP / END format) ───────────────────────
def log_start(task: str):
    print(f"[START] {task}", flush=True)

def log_step(step: str, detail: str = ""):
    msg = f"[STEP] {step}"
    if detail:
        msg += f" | {detail}"
    print(msg, flush=True)

def log_end(task: str, result: str = ""):
    msg = f"[END] {task}"
    if result:
        msg += f" | {result}"
    print(msg, flush=True)


# ── Inference: Stock Analysis via LLM ────────────────────────────────────────
def run_inference(ticker: str, indicators: dict, sentiment_score: float = 0.0) -> dict:
    """
    Run Aarthi AI's LLM-based stock inference for a given ticker.
    Uses the OpenAI client configured via API_BASE_URL / MODEL_NAME / HF_TOKEN.

    Returns a dict with keys: score, direction, reasoning, source.
    """
    task_name = f"stock_inference:{ticker}"
    log_start(task_name)

    # ── Build prompt ─────────────────────────────────────────────────────────
    log_step("building_prompt", f"ticker={ticker}")
    prompt = _build_prompt(ticker, indicators, sentiment_score)

    # ── Call the LLM via OpenAI client ───────────────────────────────────────
    log_step("calling_llm", f"model={MODEL_NAME}, base_url={API_BASE_URL}")
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Aarthi AI, an expert Indian stock market analyst. "
                        "Respond ONLY with valid JSON. No markdown, no extra text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
            temperature=0.2,
        )
        raw_text = response.choices[0].message.content.strip()
        log_step("llm_response_received", f"length={len(raw_text)}")
    except Exception as e:
        log_end(task_name, f"ERROR: {e}")
        return _fallback(str(e))

    # ── Parse response ───────────────────────────────────────────────────────
    log_step("parsing_response")
    try:
        # Strip markdown code fences if present
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        score = max(-1.0, min(1.0, float(parsed.get("score", 0.0))))

        result = {
            "ticker":    ticker,
            "score":     round(score, 3),
            "direction": parsed.get("direction", "neutral"),
            "reasoning": parsed.get("reasoning", ""),
            "source":    f"openai/{MODEL_NAME}",
        }

        log_end(task_name, f"direction={result['direction']}, score={result['score']}")
        return result

    except (json.JSONDecodeError, KeyError, ValueError) as parse_err:
        log_end(task_name, f"PARSE_ERROR: {parse_err}")
        return _fallback(f"parse error: {parse_err}")


# ── Batch Inference ───────────────────────────────────────────────────────────
def run_batch_inference(tickers: list[str]) -> list[dict]:
    """
    Run inference for a list of tickers sequentially.
    Each call follows the START/STEP/END log structure independently.
    """
    log_start("batch_inference")
    log_step("batch_start", f"tickers={tickers}, count={len(tickers)}")

    results = []
    for i, ticker in enumerate(tickers):
        log_step("processing_ticker", f"{i+1}/{len(tickers)} ticker={ticker}")
        # Minimal dummy indicators for standalone batch run demo
        indicators = {
            "RSI": 50.0,
            "MACD": 0.0,
            "MACD_Signal": 0.0,
            "SMA_20": 0.0,
            "SMA_50": 0.0,
            "BB_Width": 0.02,
            "ATR": 1.0,
        }
        result = run_inference(ticker, indicators, sentiment_score=0.0)
        results.append(result)

    log_end("batch_inference", f"completed={len(results)}")
    return results


# ── Private helpers ───────────────────────────────────────────────────────────
def _build_prompt(ticker: str, indicators: dict, sentiment_score: float) -> str:
    return f"""Analyze this Indian stock and provide a prediction bias.

STOCK: {ticker}

TECHNICAL INDICATORS:
- RSI: {indicators.get('RSI', 'N/A')}  (>70 overbought, <30 oversold)
- MACD: {indicators.get('MACD', 'N/A')} (Signal: {indicators.get('MACD_Signal', 'N/A')})
- SMA_20: {indicators.get('SMA_20', 'N/A')} | SMA_50: {indicators.get('SMA_50', 'N/A')}
- BB_Width: {indicators.get('BB_Width', 'N/A')} | ATR: {indicators.get('ATR', 'N/A')}

SENTIMENT SCORE: {sentiment_score:+.3f}  (-1=very negative, 0=neutral, +1=very positive)

Respond ONLY with this exact JSON format, no other text:
{{"score": <float between -1.0 and 1.0>, "direction": "<bullish/bearish/neutral>", "reasoning": "<one concise sentence>"}}

Score guide: -1.0 = very bearish, 0 = neutral, +1.0 = very bullish"""


def _fallback(reason: str = "") -> dict:
    return {
        "score":     0.0,
        "direction": "neutral",
        "reasoning": f"LLM unavailable — fallback to neutral. Reason: {reason}",
        "source":    "fallback",
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    """
    Standalone demo: infers on a default list of NSE tickers.
    Usage:
        python inference.py
        python inference.py RELIANCE.NS TCS.NS INFY.NS
    """
    log_start("aarthi_ai_inference_demo")
    log_step("env_check", f"API_BASE_URL={API_BASE_URL}, MODEL_NAME={MODEL_NAME}, HF_TOKEN={'set' if HF_TOKEN else 'NOT SET'}")

    # Optional docker image info
    docker_image = from_docker_image()
    if docker_image:
        log_step("docker_image", f"LOCAL_IMAGE_NAME={docker_image}")

    # Tickers from CLI args or default set
    tickers = sys.argv[1:] if len(sys.argv) > 1 else [
        "RELIANCE.NS",
        "TCS.NS",
        "INFY.NS",
    ]

    results = run_batch_inference(tickers)

    log_step("printing_results")
    for r in results:
        print(json.dumps(r, indent=2))

    log_end("aarthi_ai_inference_demo", f"total_tickers_processed={len(results)}")
