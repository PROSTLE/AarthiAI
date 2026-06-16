---
title: AarthiAI
emoji: 🦀
colorFrom: red
colorTo: green
sdk: docker
pinned: false
---

# 📈 Aarthi AI — Empathetic Financial Planning + Stock Forecasting

> Built at **Women Techies**. A financial-intelligence app that pairs a **PyTorch BiLSTM price forecaster** and a **FinBERT + VADER sentiment engine** with an LLM "reasoning voice" — so the numbers come with context a real person can act on.

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?style=flat&logo=pytorch&logoColor=white)
![HuggingFace](https://img.shields.io/badge/FinBERT-FFD21E?style=flat&logo=huggingface&logoColor=black)
![Gemini](https://img.shields.io/badge/Gemini-8E75B2?style=flat&logo=googlegemini&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=flat&logo=python&logoColor=white)

---

## The idea

Most robo-advisors ask your risk tolerance on a 1–10 scale and dump you into an index fund. Aarthi AI's premise is that good financial guidance needs **context** — your emotional state, life stage, cash flow, and dependents — and then explains its reasoning in plain language instead of flashing red/green numbers. The forecasting and sentiment models supply the hard signals; an LLM turns them into something human-readable.

## Deep tech (what's actually under the hood)

### 1. Price forecaster — Attention BiLSTM (PyTorch)
`backend/model.py` defines `StockLSTM`, a **bidirectional 3-layer LSTM (128 hidden units) with an attention head**, trained per-ticker on demand:

- **Input:** a 60-day rolling window (`LOOK_BACK = 60`) of ~10 price/technical features, `MinMaxScaler`-normalised on the train split only (no leakage).
- **Output:** the next **5 closing prices** (`PREDICT_DAYS = 5`).
- **Training:** Adam (`lr=1e-3`, `weight_decay=1e-5`), `MSELoss`, `ReduceLROnPlateau` scheduler, and **early stopping** on validation loss (≤35 epochs). Fully seeded for reproducibility.
- **Why BiLSTM + attention:** markets have memory (support/resistance); the recurrent state captures sequence structure while attention weights the most predictive days in the window.

### 2. Sentiment engine — FinBERT + VADER ensemble
`backend/sentiment.py` blends two complementary models so headlines are read in financial context:

```
combined = 0.4 · VADER  +  0.6 · FinBERT(ProsusAI/finbert)
```

- **FinBERT** (a BERT model pre-trained on financial text) handles domain language VADER misreads.
- **VADER** adds fast lexical polarity, with a **custom finance lexicon** patched in (e.g. "beat", "downgrade", "guidance").
- A strongly negative news signal can override a bullish technical forecast — a deliberate guardrail.

### 3. Technical scoring — horizon-aligned, not textbook
`backend/technical_signals.py` is tuned to the **5-day** prediction horizon rather than copy-pasting defaults:
- **RSI** blends `RSI(5)·0.70 + RSI(14)·0.30` so momentum matches the forecast window.
- **MACD** scores histogram **acceleration** (slope of the last 3 bars), not static level.
- **ATR** is treated as a volatility/regime input (weight reduced), not a direction signal.
This deterministic engine acts as a sanity rail on the ML outputs.

### 4. LLM reasoning layer
Google **Gemini** (`google-generativeai`) synthesises the technical indicators, sentiment, and forecast into plain-English explanations and behavioural nudges — the "why" behind each recommendation.

### 5. Paper-trading + agent interface
The FastAPI app also exposes a **paper-trading portfolio** (`/api/trade/*` — execute, toggle, reset, portfolio) and an **OpenEnv-style RL interface** (`/reset`, `/step`, `/state`, see `openenv.yaml`) so the forecaster can be driven as an environment.

## API surface (FastAPI)

| Endpoint | Purpose |
|---|---|
| `GET /api/predict/{ticker}` | 5-day BiLSTM price forecast + confidence |
| `GET /api/sentiment/{ticker}` | FinBERT+VADER news sentiment breakdown |
| `GET /api/summary/{ticker}` | LLM-narrated analysis |
| `GET /api/chart/{ticker}` | OHLCV history (`yfinance`) |
| `GET /api/high-potential` | Ranked screen across watched tickers |
| `GET /api/market-indices` | Live index snapshot |
| `POST /api/trade/execute/{ticker}` | Paper-trade execution |
| `POST /step` · `/reset` · `/state` | OpenEnv RL environment loop |

## Tech Stack

**ML / NLP** — PyTorch (BiLSTM+attention), Transformers (`ProsusAI/finbert`), NLTK VADER, scikit-learn, XGBoost
**Data / signals** — `yfinance`, `ta` (technical indicators), pandas/NumPy
**Backend** — FastAPI, Pydantic, `google-generativeai` (Gemini), OpenAI SDK
**Frontend** — HTML/CSS/JS dashboards (market, mutual-funds explorer, SIP calculator, company deep-dive)
**Deploy** — Docker (Hugging Face Spaces, `sdk: docker`)

## Quick Start

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt                   # torch is CPU-only via Dockerfile in prod
uvicorn app:app --reload --port 8000              # http://localhost:8000
```

**Frontend**
```bash
cd frontend
npx http-server . -p 3000                          # http://localhost:3000
```

> First prediction per ticker downloads ~2 years of history and trains the LSTM on the fly, so it takes a few seconds; subsequent calls are faster.

## Project layout

```
AarthiAI/
├── backend/
│   ├── app.py                 # FastAPI app — predict / sentiment / trade / OpenEnv routes
│   ├── model.py               # StockLSTM (BiLSTM + attention) train_and_predict
│   ├── sentiment.py           # FinBERT + VADER weighted ensemble
│   ├── technical_signals.py   # horizon-aligned RSI / MACD / ATR scoring
│   ├── stock_data.py          # yfinance + ta feature pipeline
│   ├── intraday_model.py / long_term_analysis.py / fund_intelligence.py
│   └── llm_analysis.py        # Gemini reasoning layer
├── frontend/                  # market dashboard, funds explorer, SIP calculator
├── Dockerfile                 # HF Spaces (CPU torch)
└── openenv.yaml               # RL environment manifest
```

## ⚠️ Disclaimer

Aarthi AI is a **hackathon prototype for education and demonstration only** — not a registered financial advisor. Forecasts and sentiment scores are not financial advice; capital can be lost. Consult a certified advisor before making investment decisions.

## License

MIT — fork and build on it.
