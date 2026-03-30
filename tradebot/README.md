# AarthiAI TradeBot

Production-ready autonomous trading system for **NSE/BSE** Indian equity markets.

---

## Architecture

```
tradebot/
├── config/             # thresholds.yaml, secrets.yaml
├── ingestion/          # KiteConnect ticks, NSE data, yfinance
├── features/           # Technical indicators, sector heat scoring
├── models/             # LightGBM (intraday), XGBoost (swing), fundamentals
├── sentiment/          # FinBERT news scoring with decay weights
├── behavioral/         # Mood engine, SVD+KMeans user profiling
├── risk/               # Hard guardrails, GTT enforcement
├── execution/          # Order manager, 5-min P&L monitor
├── signals/            # Signal engine, Daily Signal Brief
├── orchestration/      # Airflow DAGs (9:00 AM, 9:15 AM, 4:00 PM IST)
├── monitoring/         # Evidently drift detection, MLflow logging
├── api/                # FastAPI + WebSocket + Firebase push
└── run.py              # Entry point
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure secrets
```bash
cp config/secrets.template.yaml config/secrets.yaml
# Fill in your Kite API key, access token, Redis/Postgres creds
```

### 3. Start services
```bash
# Redis (required)
redis-server

# MLflow (optional but recommended)
mlflow server --host 0.0.0.0 --port 5000

# Postgres (for Airflow)
# docker run -e POSTGRES_PASSWORD=pass -p 5432:5432 postgres:15
```

### 4. Run the API
```bash
cd tradebot
python run.py api
# → http://localhost:8001
# → Docs at http://localhost:8001/docs
```

### 5. Manual scan (test without Airflow)
```bash
python run.py scan
```

### 6. Train models (first time)
```bash
python run.py train
```

---

## Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/mood` | Set today's trading mood |
| GET | `/api/signals/latest` | Get latest signal brief |
| GET | `/api/brief?language=hi` | Daily brief (bilingual) |
| POST | `/api/scan` | Trigger manual scan |
| POST | `/api/trade/execute` | Place a trade |
| GET | `/api/risk/status/{user_id}` | Risk budget remaining |
| WS | `/ws/signals/{user_id}` | Live signal push |

---

## Mood → AutoTrade Modes

| Morning Mood | Mode | Auto Entry | Auto Exit | Confidence Gate |
|---|---|---|---|---|
| Focused & active | Supervised | ❌ | ❌ | 75 |
| Busy but watching | Semi-Auto | ✅ | ❌ | 75 |
| Tired — trade for me | Full AutoTrade | ✅ | ✅ | 82 |
| Out today | Paused | ❌ | ❌ | — |
| Aggressive | Semi-Auto+ | ✅ | ❌ | 68, 1.5× size |

---

## Risk Guardrails (Non-negotiable)

- Max daily loss: **2% of capital** → auto halt + square-off
- Max single trade risk: **1.5% of capital**
- Max stop distance: **2% of entry** (wider stops shrink position size)
- Max concurrent: **5 intraday / 3 swing / 2 positional**
- GTT OCO placed within **2 seconds** of every entry
- Force square-off at **15:15 IST** for all MIS positions

---

## Airflow Schedule

| DAG | Trigger | Task |
|-----|---------|------|
| `premarket_pipeline` | 9:00 AM IST Mon–Fri | Global cues, FII/DII, PCR, sector momentum, news |
| `market_open_scanner` | 9:15 AM IST Mon–Fri | Signal generation + AutoTrade execution |
| `eod_model_updater` | 4:00 PM IST Mon–Fri | Outcome logging, drift detection, retrain |

---

## Important NSE Warnings

- **Kite WebSocket**: max 3,000 instrument tokens per connection
- **F&O Ban**: check `nsepython.nse_fo_ban()` daily — filtered automatically
- **GTT**: does NOT auto-square MIS at 3:20 PM — force square-off via `schedule` at 15:15
- **yfinance NSE**: always `.NS` suffix; 15-min delay — never use for live signals
- **ORB Window**: 9:15–9:29 AM (first 3 five-minute candles)
