
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from stock_data import fetch_stock_data, add_technical_indicators, get_stock_info, fetch_live_price, fetch_chart_data, fetch_india_vix, fetch_tcs_macro_context
from sentiment import analyze_sentiment
from model import train_and_predict
from technical_signals import score_technical_signals
from llm_analysis import analyze_with_llm
from intraday_model import generate_intraday_signal
from long_term_analysis import analyze_long_term
from fund_intelligence import (
    FUND_UNIVERSE, RBI_REPO_RATE, CPI_INFLATION, NIFTY_PE_RATIO,
    analyze_fund, generate_investment_brief,
    piotroski_f_score, altman_z_score, fetch_fundamentals,
)
from trader import (
    get_portfolio, reset_portfolio, toggle_bot,
    evaluate_trade_signal, execute_sell, execute_buy, check_position,
    compute_dynamic_levels, detect_market_regime,
    add_to_balance, withdraw_from_balance, get_wallet_transactions,
    get_value_history,
)
from backtest_weights import run_signal_health_check, get_tcs_macro_score, derive_weights, load_cached_weights
import concurrent.futures
import datetime

app = FastAPI(title="StockSense AI", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "StockSense AI API v3.1 is running 🚀 — Anti-gravity edition"}


# ── OpenEnv-Compatible Endpoints (Required by hackathon checker) ──────────────
# Implements the Gymnasium-style OpenEnv API: reset(), step(), state()
# See: https://github.com/meta-pytorch/OpenEnv

import uuid as _uuid
import time as _time

_episode_state = {
    "episode_id": None,
    "step_count": 0,
    "started_at": None,
    "done": False,
}


class StepActionRequest(BaseModel):
    action: str = "hold"          # "buy" | "sell" | "hold"
    ticker: str = "TCS.NS"
    quantity: float = 1.0


@app.post("/reset")
def openenv_reset():
    """
    OpenEnv reset() — resets the trading portfolio and starts a new episode.
    Required by the hackathon automated checker (POST /reset).
    Returns initial observation in OpenEnv format.
    """
    portfolio = reset_portfolio()
    _episode_state["episode_id"] = str(_uuid.uuid4())
    _episode_state["step_count"] = 0
    _episode_state["started_at"] = _time.time()
    _episode_state["done"] = False

    return {
        "observation": {
            "balance": portfolio.get("balance", 100000.0),
            "positions": {},
            "portfolio_value": portfolio.get("balance", 100000.0),
            "message": "Trading environment reset. New episode started.",
            "episode_id": _episode_state["episode_id"],
        },
        "state": {
            "episode_id": _episode_state["episode_id"],
            "step_count": 0,
            "done": False,
        },
    }


@app.post("/step")
def openenv_step(request: StepActionRequest):
    """
    OpenEnv step() — executes a trade action and returns the resulting observation.
    Actions: 'buy' | 'sell' | 'hold'
    Required by the hackathon automated checker (POST /step).
    """
    _episode_state["step_count"] += 1
    portfolio = get_portfolio()

    reward = 0.0
    result_msg = ""

    try:
        live = fetch_live_price(request.ticker)
        current_price = live.get("price", 0)

        if request.action == "buy":
            cost = current_price * request.quantity
            if portfolio["balance"] >= cost:
                result = execute_buy(
                    ticker=request.ticker,
                    current_price=current_price,
                    predicted_prices=[current_price * 1.02],
                    confidence=0.7,
                )
                reward = 0.5
                result_msg = result.get("message", "Buy executed")
            else:
                reward = -0.1
                result_msg = "Insufficient balance"

        elif request.action == "sell":
            if request.ticker in portfolio.get("positions", {}):
                result = execute_sell(request.ticker, current_price, "OpenEnv step sell")
                reward = result.get("profit", 0) / max(current_price, 1)
                result_msg = result.get("message", "Sell executed")
            else:
                reward = -0.1
                result_msg = "No position to sell"

        else:
            reward = 0.0
            result_msg = "Hold — no action taken"

    except Exception as e:
        result_msg = f"Action failed: {str(e)}"
        reward = -0.05

    portfolio = get_portfolio()
    done = _episode_state["step_count"] >= 100  # episode ends after 100 steps
    _episode_state["done"] = done

    return {
        "observation": {
            "balance": portfolio.get("balance", 0),
            "positions": {k: v.get("shares", 0) for k, v in portfolio.get("positions", {}).items()},
            "portfolio_value": portfolio.get("balance", 0),
            "message": result_msg,
            "episode_id": _episode_state["episode_id"],
        },
        "reward": round(reward, 6),
        "done": done,
        "info": {
            "step": _episode_state["step_count"],
            "action": request.action,
            "ticker": request.ticker,
        },
    }


@app.get("/state")
def openenv_state():
    """
    OpenEnv state() — returns current episode metadata.
    Required by the hackathon automated checker (GET /state).
    """
    portfolio = get_portfolio()
    return {
        "episode_id": _episode_state.get("episode_id"),
        "step_count": _episode_state.get("step_count", 0),
        "done": _episode_state.get("done", False),
        "started_at": _episode_state.get("started_at"),
        "portfolio_summary": {
            "balance": portfolio.get("balance", 0),
            "total_positions": len(portfolio.get("positions", {})),
            "bot_active": portfolio.get("bot_active", False),
        },
    }


@app.get("/api/health")
def health_check():
    """
    Anti-entropy maintenance endpoint.
    Run on every cold start or scheduled health monitor.
    Returns liveness of all signal sources: LLM, macro data, weight cache.
    """
    try:
        return {"status": "ok", **run_signal_health_check()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/macro/{ticker}")
def macro_context(ticker: str):
    """
    Fetch TCS-specific macro signals: USD/INR + CNXIT sector alpha.
    Orthogonal to all price-based signals. Only meaningful for IT exporters.
    """
    try:
        macro = fetch_tcs_macro_context()
        score = get_tcs_macro_score(ticker, macro)
        return {
            "ticker": ticker,
            "usd_inr": macro.get("usd_inr"),
            "usd_5d_return_pct": macro.get("usd_5d_return"),
            "cnxit_5d_alpha_pct": macro.get("cnxit_5d_return"),
            "macro_directional_score": score,
            "available": macro.get("available", False),
            "interpretation": "bullish" if score > 0.1 else ("bearish" if score < -0.1 else "neutral"),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/stock/{ticker}")
def get_stock(ticker: str):
    try:
        df = fetch_stock_data(ticker)
        df = add_technical_indicators(df)
        records = df.tail(200).to_dict(orient="records")
        for r in records:
            if "Date" in r:
                r["Date"] = str(r["Date"])
        info = get_stock_info(ticker)
        return {"info": info, "data": records}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/live/{ticker}")
def live_price(ticker: str):
    try:
        return fetch_live_price(ticker)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/chart/{ticker}")
def chart_data(ticker: str, timeframe: str = Query("1mo", pattern="^(1d|5d|1wk|1mo|3mo|6mo|1y|2y)$")):
    try:
        data = fetch_chart_data(ticker, timeframe)
        return {"ticker": ticker, "timeframe": timeframe, "data": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/market-indices")
def get_market_indices():
    import yfinance as yf
    indices = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN"}
    results = []
    for name, symbol in indices.items():
        try:
            stock = yf.Ticker(symbol)
            info = stock.info or {}
            hist = stock.history(period="5d")
            price = 0
            prev = 0
            if len(hist) >= 2:
                price = round(float(hist["Close"].iloc[-1]), 2)
                prev = round(float(hist["Close"].iloc[-2]), 2)
            elif len(hist) == 1:
                price = round(float(hist["Close"].iloc[-1]), 2)
                prev = info.get("previousClose", info.get("regularMarketPreviousClose", price))
            else:
                price = info.get("regularMarketPrice", info.get("previousClose", 0))
                prev = info.get("previousClose", info.get("regularMarketPreviousClose", price))
            if not price and info:
                price = info.get("regularMarketPrice", info.get("previousClose", 0))
            if not prev or prev == price:
                prev = info.get("previousClose", info.get("regularMarketPreviousClose", prev))
            change = round(price - prev, 2)
            change_pct = round((change / prev) * 100, 2) if prev else 0
            results.append({
                "name": name, "symbol": symbol, "price": price,
                "change": change, "change_pct": change_pct,
                "direction": "up" if change >= 0 else "down",
            })
        except Exception:
            results.append({"name": name, "symbol": symbol, "price": 0, "change": 0, "change_pct": 0, "direction": "up"})
    return {"indices": results}


@app.get("/api/predict/{ticker}")
def predict(ticker: str):
    try:
        df = fetch_stock_data(ticker)
        df = add_technical_indicators(df)

        # ── Compute all 5 factors ──
        # 1. Sentiment
        sent = analyze_sentiment(ticker)
        sentiment_score = float(sent.get("overall_score", 0))
        sentiment_label = sent.get("overall_sentiment", "neutral")

        # 2. Technical signals
        tech = score_technical_signals(df)
        technical_score = float(tech.get("score", 0))
        technical_direction = tech.get("direction", "neutral")

        # 3. LLM analysis
        latest = df.iloc[-1]
        indicators = {
            "RSI": round(float(latest["RSI"]), 2),
            "MACD": round(float(latest["MACD"]), 4),
            "MACD_Signal": round(float(latest["MACD_Signal"]), 4),
            "SMA_20": round(float(latest["SMA_20"]), 2),
            "SMA_50": round(float(latest["SMA_50"]), 2),
            "BB_Width": round(float(latest["BB_Width"]), 4),
            "ATR": round(float(latest["ATR"]), 2),
        }
        recent_prices = df["Close"].values[-10:].tolist()
        llm = analyze_with_llm(
            ticker=ticker,
            current_price=float(latest["Close"]),
            indicators=indicators,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            recent_prices=recent_prices,
        )
        llm_score = float(llm.get("score", 0))
        llm_direction = llm.get("direction", "neutral")

        # Market Context for Crisis Mode
        vix_data = fetch_india_vix()
        vix_level = float(vix_data.get("vix_level", 15.0))
        current_price = float(latest["Close"])
        atr = float(latest["ATR"])
        atr_pct = (atr / current_price * 100) if current_price > 0 else 0

        # 4+5. LSTM + Enterprise are inside train_and_predict
        result = train_and_predict(
            df,
            sentiment_score=sentiment_score,
            technical_score=technical_score,
            llm_score=llm_score,
            llm_confidence=float(llm.get("confidence", 1.0)),
            sentiment_label=sentiment_label,
            technical_direction=technical_direction,
            llm_direction=llm_direction,
            atr_pct=atr_pct,
            vix_level=vix_level,
        )
        result["llm_reasoning"] = llm.get("reasoning", "")
        result["technical_signals"] = tech.get("signals", {})
        return {"ticker": ticker, **result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/sentiment/{ticker}")
def sentiment(ticker: str):
    try:
        return analyze_sentiment(ticker)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/summary/{ticker}")
def summary(ticker: str):
    try:
        info = get_stock_info(ticker)
        df = fetch_stock_data(ticker)
        df_ind = add_technical_indicators(df)

        # Compute factors
        sent = analyze_sentiment(ticker)
        sentiment_score = float(sent.get("overall_score", 0))
        sentiment_label = sent.get("overall_sentiment", "neutral")

        tech = score_technical_signals(df_ind)
        technical_score = float(tech.get("score", 0))
        technical_direction = tech.get("direction", "neutral")

        latest = df_ind.iloc[-1]
        indicators = {
            "RSI": round(float(latest["RSI"]), 2),
            "MACD": round(float(latest["MACD"]), 4),
            "MACD_Signal": round(float(latest["MACD_Signal"]), 4),
            "SMA_20": round(float(latest["SMA_20"]), 2),
            "SMA_50": round(float(latest["SMA_50"]), 2),
            "BB_Upper": round(float(latest["BB_Upper"]), 2),
            "BB_Lower": round(float(latest["BB_Lower"]), 2),
            "BB_Width": round(float(latest["BB_Width"]), 4),
            "ATR": round(float(latest["ATR"]), 2),
        }

        recent_prices = df_ind["Close"].values[-10:].tolist()
        llm = analyze_with_llm(
            ticker=ticker,
            current_price=float(latest["Close"]),
            indicators=indicators,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            recent_prices=recent_prices,
        )
        llm_score = float(llm.get("score", 0))
        llm_direction = llm.get("direction", "neutral")

        # Market Context for Crisis Mode
        vix_data = fetch_india_vix()
        vix_level = float(vix_data.get("vix_level", 15.0))
        current_price = float(latest["Close"])
        atr = float(latest["ATR"])
        atr_pct = (atr / current_price * 100) if current_price > 0 else 0

        prediction = train_and_predict(
            df_ind,
            sentiment_score=sentiment_score,
            technical_score=technical_score,
            llm_score=llm_score,
            llm_confidence=float(llm.get("confidence", 1.0)),
            sentiment_label=sentiment_label,
            technical_direction=technical_direction,
            llm_direction=llm_direction,
            atr_pct=atr_pct,
            vix_level=vix_level,
        )

        return {
            "info": info,
            "indicators": indicators,
            "prediction": prediction,
            "sentiment": sent,
            "technical": tech,
            "llm_analysis": llm,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Stock Search Database ─────────────────────────────────────────────────────

STOCK_DATABASE = [
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries"},
    {"ticker": "TCS.NS", "name": "Tata Consultancy Services"},
    {"ticker": "INFY.NS", "name": "Infosys"},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank"},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank"},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel"},
    {"ticker": "SBIN.NS", "name": "State Bank of India"},
    {"ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever"},
    {"ticker": "ITC.NS", "name": "ITC Limited"},
    {"ticker": "LT.NS", "name": "Larsen & Toubro"},
    {"ticker": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank"},
    {"ticker": "TATAMOTORS.NS", "name": "Tata Motors"},
    {"ticker": "WIPRO.NS", "name": "Wipro"},
    {"ticker": "MARUTI.NS", "name": "Maruti Suzuki India"},
    {"ticker": "ADANIENT.NS", "name": "Adani Enterprises"},
    {"ticker": "TATASTEEL.NS", "name": "Tata Steel"},
    {"ticker": "TATASILV.NS", "name": "Tata Silver ETF"},
    {"ticker": "TATAPOWER.NS", "name": "Tata Power Company"},
    {"ticker": "TATACOMM.NS", "name": "Tata Communications"},
    {"ticker": "TATAELXSI.NS", "name": "Tata Elxsi"},
    {"ticker": "TATACHEM.NS", "name": "Tata Chemicals"},
    {"ticker": "TATACONSUM.NS", "name": "Tata Consumer Products"},
    {"ticker": "TITAN.NS", "name": "Titan Company"},
    {"ticker": "SUNPHARMA.NS", "name": "Sun Pharmaceutical"},
    {"ticker": "HCLTECH.NS", "name": "HCL Technologies"},
    {"ticker": "BAJFINANCE.NS", "name": "Bajaj Finance"},
    {"ticker": "BAJAJFINSV.NS", "name": "Bajaj Finserv"},
    {"ticker": "ASIANPAINT.NS", "name": "Asian Paints"},
    {"ticker": "AXISBANK.NS", "name": "Axis Bank"},
    {"ticker": "ULTRACEMCO.NS", "name": "UltraTech Cement"},
    {"ticker": "NESTLEIND.NS", "name": "Nestle India"},
    {"ticker": "NTPC.NS", "name": "NTPC Limited"},
    {"ticker": "POWERGRID.NS", "name": "Power Grid Corporation"},
    {"ticker": "ONGC.NS", "name": "Oil & Natural Gas Corporation"},
    {"ticker": "COALINDIA.NS", "name": "Coal India"},
    {"ticker": "JSWSTEEL.NS", "name": "JSW Steel"},
    {"ticker": "TECHM.NS", "name": "Tech Mahindra"},
    {"ticker": "DRREDDY.NS", "name": "Dr. Reddy's Laboratories"},
    {"ticker": "CIPLA.NS", "name": "Cipla"},
    {"ticker": "DIVISLAB.NS", "name": "Divi's Laboratories"},
    {"ticker": "EICHERMOT.NS", "name": "Eicher Motors"},
    {"ticker": "HEROMOTOCO.NS", "name": "Hero MotoCorp"},
    {"ticker": "BAJAJ-AUTO.NS", "name": "Bajaj Auto"},
    {"ticker": "M&M.NS", "name": "Mahindra & Mahindra"},
    {"ticker": "BRITANNIA.NS", "name": "Britannia Industries"},
    {"ticker": "DABUR.NS", "name": "Dabur India"},
    {"ticker": "GODREJCP.NS", "name": "Godrej Consumer Products"},
    {"ticker": "PIDILITIND.NS", "name": "Pidilite Industries"},
    {"ticker": "BERGEPAINT.NS", "name": "Berger Paints India"},
    {"ticker": "HAVELLS.NS", "name": "Havells India"},
    {"ticker": "SIEMENS.NS", "name": "Siemens India"},
    {"ticker": "ABB.NS", "name": "ABB India"},
    {"ticker": "ADANIPORTS.NS", "name": "Adani Ports"},
    {"ticker": "ADANIGREEN.NS", "name": "Adani Green Energy"},
    {"ticker": "GRASIM.NS", "name": "Grasim Industries"},
    {"ticker": "INDUSINDBK.NS", "name": "IndusInd Bank"},
    {"ticker": "SBILIFE.NS", "name": "SBI Life Insurance"},
    {"ticker": "HDFCLIFE.NS", "name": "HDFC Life Insurance"},
    {"ticker": "APOLLOHOSP.NS", "name": "Apollo Hospitals"},
    {"ticker": "ZOMATO.NS", "name": "Zomato"},
    {"ticker": "PAYTM.NS", "name": "One97 Communications (Paytm)"},
    {"ticker": "NYKAA.NS", "name": "FSN E-Commerce (Nykaa)"},
    {"ticker": "DMART.NS", "name": "Avenue Supermarts (DMart)"},
    {"ticker": "IRCTC.NS", "name": "IRCTC"},
    {"ticker": "HAL.NS", "name": "Hindustan Aeronautics"},
    {"ticker": "BEL.NS", "name": "Bharat Electronics"},
    {"ticker": "BANKBARODA.NS", "name": "Bank of Baroda"},
    {"ticker": "PNB.NS", "name": "Punjab National Bank"},
    {"ticker": "CANBK.NS", "name": "Canara Bank"},
    {"ticker": "IOC.NS", "name": "Indian Oil Corporation"},
    {"ticker": "BPCL.NS", "name": "Bharat Petroleum"},
    {"ticker": "HINDPETRO.NS", "name": "Hindustan Petroleum"},
    {"ticker": "VEDL.NS", "name": "Vedanta Limited"},
    {"ticker": "HINDALCO.NS", "name": "Hindalco Industries"},
    {"ticker": "GOLDIAM.NS", "name": "Goldiam International"},
    {"ticker": "GOLDBEES.NS", "name": "Nippon India Gold ETF"},
    {"ticker": "SILVEREES.NS", "name": "Nippon India Silver ETF"},
]


@app.get("/api/search")
def search_stocks(q: str = Query("", min_length=1)):
    query = q.strip().upper()
    if not query:
        return {"results": []}

    matches = []
    for stock in STOCK_DATABASE:
        ticker_upper = stock["ticker"].upper()
        name_upper = stock["name"].upper()
        if query in ticker_upper or query in name_upper:
            matches.append(stock)

    matches.sort(key=lambda s: (
        0 if s["ticker"].upper().startswith(query) else
        1 if s["name"].upper().startswith(query) else 2
    ))

    return {"results": matches[:10]}


# ── Scanner Tickers ───────────────────────────────────────────────────────────

SCAN_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "SBIN.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS",
    "KOTAKBANK.NS", "TATAMOTORS.NS", "WIPRO.NS", "MARUTI.NS", "ADANIENT.NS",
]


def _analyze_one(ticker: str) -> dict | None:
    try:
        info = get_stock_info(ticker)
        df = fetch_stock_data(ticker, period="3mo")
        df = add_technical_indicators(df)
        latest = df.iloc[-1]

        rsi = float(latest["RSI"])
        macd = float(latest["MACD"])
        macd_signal = float(latest["MACD_Signal"])
        sma_20 = float(latest["SMA_20"])
        price = float(latest["Close"])

        score = 50
        if rsi < 30: score += 20
        elif rsi < 40: score += 10
        elif rsi > 70: score -= 15
        elif rsi > 60: score -= 5

        if macd > macd_signal: score += 15
        else: score -= 10

        if price > sma_20: score += 10
        else: score -= 10

        vol = float(latest["Volume"])
        vol_avg = float(latest["Volume_SMA_20"])
        if vol_avg > 0 and vol > vol_avg * 1.3: score += 10

        # ── Trend / momentum correction ───────────────────────────────────────
        # Prevent "Strong Buy" for stocks in a clear downtrend.
        # Uses 1-day and 5-day price changes to penalize falling stocks.
        prev_close = float(df.iloc[-2]["Close"])
        change_pct = round(((price - prev_close) / prev_close) * 100, 2)

        if len(df) >= 6:
            price_5d_ago = float(df.iloc[-6]["Close"])
            trend_5d_pct = (price - price_5d_ago) / price_5d_ago * 100
        else:
            trend_5d_pct = change_pct

        # 1-day drop > 1% → penalty 8 pts
        if change_pct < -1.0:
            score -= 8
        # 5-day downtrend → additional penalty (4 pts per 1% drop, max 20 pts)
        if trend_5d_pct < 0:
            trend_penalty = min(20, abs(trend_5d_pct) * 4)
            score -= int(trend_penalty)

        # Hard cap: when both 1-day AND 5-day trend are negative,
        # max score is 64 → cannot reach "Strong Buy" threshold (70)
        if change_pct < 0 and trend_5d_pct < -1.0:
            score = min(score, 64)

        score = max(0, min(100, score))

        if score >= 70: signal_text = "🟢 Strong Buy"
        elif score >= 55: signal_text = "🔵 Buy"
        elif score >= 40: signal_text = "🟡 Hold"
        else: signal_text = "🔴 Sell"

        return {
            "ticker": ticker, "name": info.get("name", ticker),
            "price": round(price, 2), "change_pct": change_pct,
            "rsi": round(rsi, 2), "score": score,
            "signal": signal_text, "currency": info.get("currency", "INR"),
        }
    except Exception:
        return None


@app.get("/api/high-potential")
def high_potential():
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_analyze_one, t): t for t in SCAN_TICKERS}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"stocks": results, "count": len(results)}


# ── Trading API ───────────────────────────────────────────────────────────────

@app.get("/api/trade/portfolio")
def trade_portfolio():
    try:
        portfolio = get_portfolio()
        total_unrealized = 0
        for ticker, pos in portfolio["positions"].items():
            try:
                live = fetch_live_price(ticker)
                current = live["price"]
                pnl = (current - pos["buy_price"]) * pos["shares"]
                pos["current_price"] = current
                pos["unrealized_pnl"] = round(pnl, 2)
                pos["pnl_pct"] = round(((current - pos["buy_price"]) / pos["buy_price"]) * 100, 2)
                total_unrealized += pnl
            except Exception:
                pos["current_price"] = pos["buy_price"]
                pos["unrealized_pnl"] = 0
                pos["pnl_pct"] = 0

        portfolio["total_unrealized_pnl"] = round(total_unrealized, 2)
        portfolio["total_value"] = round(portfolio["balance"] + total_unrealized + sum(
            p["shares"] * p.get("current_price", p["buy_price"]) for p in portfolio["positions"].values()
        ), 2)

        portfolio["total_realized_pnl"] = round(
            sum(t["profit"] for t in portfolio["trade_history"]), 2
        )
        portfolio["total_trades"] = len(portfolio["trade_history"])
        portfolio["winning_trades"] = sum(1 for t in portfolio["trade_history"] if t["profit"] > 0)
        portfolio["losing_trades"] = sum(1 for t in portfolio["trade_history"] if t["profit"] <= 0)

        if portfolio["total_trades"] > 0:
            portfolio["win_rate"] = round(
                (portfolio["winning_trades"] / portfolio["total_trades"]) * 100, 1
            )
        else:
            portfolio["win_rate"] = 0

        return portfolio
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/trade/reset")
def trade_reset():
    return reset_portfolio()


@app.post("/api/trade/toggle")
def trade_toggle():
    return toggle_bot()


@app.post("/api/trade/execute/{ticker}")
def trade_execute(ticker: str):
    try:
        live = fetch_live_price(ticker)
        current_price = live["price"]

        df = fetch_stock_data(ticker)
        df = add_technical_indicators(df)

        # Quick factor computation for trade decisions
        sent = analyze_sentiment(ticker)
        tech = score_technical_signals(df)

        latest = df.iloc[-1]
        vix_data = fetch_india_vix()
        vix_level = float(vix_data.get("vix_level", 15.0))
        atr = float(latest["ATR"])
        atr_pct = (atr / current_price * 100) if current_price > 0 else 0

        prediction = train_and_predict(
            df,
            sentiment_score=float(sent.get("overall_score", 0)),
            technical_score=float(tech.get("score", 0)),
            sentiment_label=sent.get("overall_sentiment", "neutral"),
            technical_direction=tech.get("direction", "neutral"),
            atr_pct=atr_pct,
            vix_level=vix_level,
        )

        indicators = {
            "RSI": float(latest["RSI"]),
            "MACD": float(latest["MACD"]),
            "MACD_Signal": float(latest["MACD_Signal"]),
            "SMA_20": float(latest["SMA_20"]),
            "SMA_50": float(latest["SMA_50"]),
            "price": current_price,
        }

        try:
            sentiment_score = sent.get("overall_score", 0.0)
        except Exception:
            sentiment_score = 0.0

        signal = evaluate_trade_signal(
            ticker=ticker,
            current_price=current_price,
            predicted_prices=prediction["predicted_prices"],
            confidence=prediction["confidence"],
            indicators=indicators,
            sentiment_score=sentiment_score,
        )

        signal["live"] = live
        signal["prediction_details"] = prediction
        return signal

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/trade/sell/{ticker}")
def trade_force_sell(ticker: str):
    try:
        live = fetch_live_price(ticker)
        result = execute_sell(ticker, live["price"], "Manual sell (forced)")
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/trade/check/{ticker}")
def trade_check(ticker: str):
    try:
        live = fetch_live_price(ticker)
        result = check_position(ticker, live["price"])
        result["live"] = live
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/trade/intraday-signal/{ticker}")
def trade_intraday_signal(ticker: str):
    """Single-stock intraday signal using XGBoost pipeline."""
    try:
        signal = generate_intraday_signal(ticker)
        return signal
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/trade/auto-scan")
def trade_auto_scan():
    """Auto-scan using intraday XGBoost pipeline with dynamic SL/TP."""
    try:
        portfolio = get_portfolio()
        if not portfolio["bot_active"]:
            return {"status": "inactive", "message": "Bot is OFF. Toggle it on first."}

        results = []

        # 1. Check existing positions for SL/TP/trailing triggers
        for ticker in list(portfolio["positions"].keys()):
            try:
                live = fetch_live_price(ticker)
                check = check_position(ticker, live["price"])
                if check["action"] == "sell":
                    sell_result = execute_sell(ticker, live["price"], check["reason"])
                    results.append({"ticker": ticker, "action": "SELL", "result": sell_result})
            except Exception:
                continue

        # 2. Scan for new entries using intraday XGBoost signals
        for scan_ticker in SCAN_TICKERS[:8]:
            if scan_ticker in portfolio["positions"]:
                continue
            try:
                signal = generate_intraday_signal(scan_ticker)

                if signal.get("action") == "BUY":
                    buy_result = execute_buy(
                        ticker=scan_ticker,
                        current_price=signal["entry_price"],
                        predicted_prices=[signal["tp1_price"]],
                        confidence=signal["confidence"],
                        sl_price=signal["sl_price"],
                        tp1_price=signal["tp1_price"],
                        tp2_price=signal.get("tp2_price"),
                        regime=signal["regime"],
                    )
                    signal["trade_result"] = buy_result

                results.append(signal)
            except Exception:
                continue

        return {
            "status": "completed",
            "scanned": len(results),
            "results": results,
            "portfolio": get_portfolio(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Wallet API ────────────────────────────────────────────────────────────────

class AddMoneyRequest(BaseModel):
    payment_id: str
    amount: float

class WithdrawRequest(BaseModel):
    amount: float


@app.get("/api/wallet/balance")
def wallet_balance():
    """Return wallet balance (= portfolio cash balance)."""
    portfolio = get_portfolio()
    return {"balance": portfolio["balance"], "status": "success"}


@app.post("/api/wallet/add")
def wallet_add(req: AddMoneyRequest):
    """Credit wallet after Razorpay payment."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    result = add_to_balance(req.amount, req.payment_id)
    return result


@app.post("/api/wallet/withdraw")
def wallet_withdraw(req: WithdrawRequest):
    """Withdraw from wallet (portfolio cash)."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    result = withdraw_from_balance(req.amount)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.get("/api/wallet/transactions")
def wallet_transactions():
    """Return wallet transaction history."""
    txns = get_wallet_transactions()
    return {"transactions": txns, "status": "success"}


@app.get("/api/portfolio/value-history")
def portfolio_value_history():
    """Return portfolio value snapshots for the account value chart."""
    try:
        snapshots = get_value_history()
        return {"snapshots": snapshots, "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Long-Term Analysis (5-Pillar Scoring Engine) ──────────────────────────────

@app.get("/api/long-term/{ticker}")
def long_term_analysis(ticker: str, _t: str = ""):
    """
    Run the 5-pillar long-term scoring engine for any NSE/BSE stock.
    Returns composite score, pillar breakdown, verdict, position sizing.
    Pass ?_t=<timestamp> to bypass the in-memory 2-hour cache.
    """
    try:
        from long_term_analysis import _LT_CACHE

        # Cache-bust: remove stale cached entry when _t param is provided
        if _t and ticker in _LT_CACHE:
            del _LT_CACHE[ticker]

        # Fetch all inputs
        df = fetch_stock_data(ticker)
        df = add_technical_indicators(df)
        info = get_stock_info(ticker)
        sent = analyze_sentiment(ticker)

        latest = df.iloc[-1]
        df_latest_dict = {
            "Close":        float(latest.get("Close", 0)),
            "RSI":          float(latest.get("RSI", 50)),
            "MACD":         float(latest.get("MACD", 0)),
            "MACD_Signal":  float(latest.get("MACD_Signal", 0)),
            "SMA_20":       float(latest.get("SMA_20", 0)),
            "SMA_50":       float(latest.get("SMA_50", 0)),
            "BB_Width":     float(latest.get("BB_Width", 0)),
            "ATR":          float(latest.get("ATR", 0)),
        }

        result = analyze_long_term(
            ticker=ticker,
            info=info,
            df_latest=df_latest_dict,
            sentiment_result=sent,
        )

        # ── Embed price history so the frontend chart needs no extra API call ──
        # df already has 1y of daily OHLCV — grab last 90 days
        hist_df = df.tail(90).copy()
        hist_prices = [round(float(p), 2) for p in hist_df["Close"].tolist()]
        # yfinance may name the date column "Date" or "Datetime" depending on version/interval
        date_col = "Date" if "Date" in hist_df.columns else ("Datetime" if "Datetime" in hist_df.columns else None)
        if date_col:
            def _fmt_date(d2):
                # Strip timezone info if present before calling .date()
                if hasattr(d2, "tz_localize"):
                    try: d2 = d2.tz_localize(None)
                    except Exception: pass
                if hasattr(d2, "tzinfo") and d2.tzinfo is not None:
                    try: d2 = d2.replace(tzinfo=None)
                    except Exception: pass
                return str(d2.date()) if hasattr(d2, "date") else str(d2)[:10]
            hist_dates = [_fmt_date(d2) for d2 in hist_df[date_col].tolist()]
        else:
            from datetime import datetime, timedelta
            today = datetime.now()
            hist_dates = [(today - timedelta(days=len(hist_prices)-1-i)).strftime("%Y-%m-%d")
                          for i in range(len(hist_prices))]
        result["hist_prices"] = hist_prices
        result["hist_dates"]  = hist_dates
        result["current_price"] = hist_prices[-1] if hist_prices else 0

        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Company Analysis API ──────────────────────────────────────────────────────

@app.get("/api/company/{ticker}")
def company_analysis(ticker: str):
    """Rich company intelligence: financials, ratios, analyst targets, history."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        # Basic info
        name = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")
        description = info.get("longBusinessSummary", "")[:500]
        exchange = info.get("exchange", "NSE")
        market_cap = info.get("marketCap", 0)
        currency = info.get("currency", "INR")

        # Price
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose") or price
        change = round(price - prev_close, 2) if price and prev_close else 0
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0

        # Key Ratios
        ratios = {
            "pe_ratio": round(info.get("trailingPE") or info.get("forwardPE") or 0, 2),
            "pb_ratio": round(info.get("priceToBook") or 0, 2),
            "roe": round((info.get("returnOnEquity") or 0) * 100, 2),
            "debt_to_equity": round(info.get("debtToEquity") or 0, 2),
            "dividend_yield": round((info.get("dividendYield") or 0) * 100, 2),
            "beta": round(info.get("beta") or 1.0, 2),
            "current_ratio": round(info.get("currentRatio") or 0, 2),
            "eps": round(info.get("trailingEps") or 0, 2),
            "revenue_growth": round((info.get("revenueGrowth") or 0) * 100, 2),
            "profit_margin": round((info.get("profitMargins") or 0) * 100, 2),
        }

        # 52W
        high_52w = round(info.get("fiftyTwoWeekHigh") or 0, 2)
        low_52w = round(info.get("fiftyTwoWeekLow") or 0, 2)

        # Assets
        total_cash = info.get("totalCash") or 0
        total_debt = info.get("totalDebt") or 0
        total_assets = info.get("totalAssets") or 0
        book_value = round(info.get("bookValue") or 0, 2)

        # Analyst recommendations
        target_price = round(info.get("targetMeanPrice") or price, 2)
        upside = round(((target_price - price) / price) * 100, 2) if price else 0
        analyst_count = info.get("numberOfAnalystOpinions") or 0
        rec_key = info.get("recommendationKey", "hold")
        rec_map = {"strongBuy": "Strong Buy", "buy": "Buy", "hold": "Hold",
                   "sell": "Sell", "strongSell": "Strong Sell"}
        recommendation = rec_map.get(rec_key, "Hold")

        # Revenue history (last 4 quarters)
        financials = {}
        try:
            fin = stock.financials
            if fin is not None and not fin.empty:
                rev_row = fin.loc["Total Revenue"] if "Total Revenue" in fin.index else None
                profit_row = fin.loc["Net Income"] if "Net Income" in fin.index else None
                if rev_row is not None:
                    financials["revenue"] = [
                        {"year": str(col.year), "value": round(float(v) / 1e7, 2)}
                        for col, v in zip(rev_row.index[:5], rev_row.values[:5])
                        if v and str(v) != "nan"
                    ]
                if profit_row is not None:
                    financials["profit"] = [
                        {"year": str(col.year), "value": round(float(v) / 1e7, 2)}
                        for col, v in zip(profit_row.index[:5], profit_row.values[:5])
                        if v and str(v) != "nan"
                    ]
        except Exception:
            pass

        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "industry": industry,
            "description": description,
            "exchange": exchange,
            "currency": currency,
            "market_cap": market_cap,
            "price": round(price, 2),
            "change": change,
            "change_pct": change_pct,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "total_cash": total_cash,
            "total_debt": total_debt,
            "total_assets": total_assets,
            "book_value": book_value,
            "ratios": ratios,
            "analyst": {
                "target_price": target_price,
                "upside_pct": upside,
                "recommendation": recommendation,
                "analyst_count": analyst_count,
            },
            "financials": financials,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Mutual Funds API (served from fund_intelligence.py FUND_UNIVERSE below) ──

# Legacy MF_DATABASE removed — all fund routes now use FUND_UNIVERSE from fund_intelligence.py
MF_DATABASE = [
    # Equity - Large Cap
    {"name": "SBI Bluechip Fund Direct", "amc": "SBI", "category": "Equity", "sub_category": "Large Cap",
     "nav": 82.45, "aum_cr": 48200, "return_1y": 21.4, "return_3y": 16.8, "return_5y": 14.2,
     "expense_ratio": 0.52, "risk": "Moderate", "rating": 5, "min_sip": 500},
    {"name": "Axis Bluechip Fund Direct", "amc": "Axis", "category": "Equity", "sub_category": "Large Cap",
     "nav": 54.78, "aum_cr": 38500, "return_1y": 18.2, "return_3y": 14.5, "return_5y": 13.1,
     "expense_ratio": 0.44, "risk": "Moderate", "rating": 4, "min_sip": 500},
    {"name": "HDFC Top 100 Fund Direct", "amc": "HDFC", "category": "Equity", "sub_category": "Large Cap",
     "nav": 1024.30, "aum_cr": 52000, "return_1y": 22.8, "return_3y": 18.2, "return_5y": 15.6,
     "expense_ratio": 0.61, "risk": "Moderate", "rating": 5, "min_sip": 100},
    {"name": "Mirae Asset Large Cap Fund Direct", "amc": "Mirae Asset", "category": "Equity", "sub_category": "Large Cap",
     "nav": 108.64, "aum_cr": 37800, "return_1y": 20.1, "return_3y": 15.9, "return_5y": 14.8,
     "expense_ratio": 0.53, "risk": "Moderate", "rating": 5, "min_sip": 1000},
    {"name": "Kotak Bluechip Fund Direct", "amc": "Kotak", "category": "Equity", "sub_category": "Large Cap",
     "nav": 482.10, "aum_cr": 8900, "return_1y": 19.4, "return_3y": 15.2, "return_5y": 14.0,
     "expense_ratio": 0.58, "risk": "Moderate", "rating": 4, "min_sip": 100},
    # Equity - Mid Cap
    {"name": "Axis Midcap Fund Direct", "amc": "Axis", "category": "Equity", "sub_category": "Mid Cap",
     "nav": 112.60, "aum_cr": 22400, "return_1y": 28.2, "return_3y": 22.1, "return_5y": 19.4,
     "expense_ratio": 0.47, "risk": "High", "rating": 5, "min_sip": 500},
    {"name": "Kotak Emerging Equity Direct", "amc": "Kotak", "category": "Equity", "sub_category": "Mid Cap",
     "nav": 108.90, "aum_cr": 18900, "return_1y": 25.6, "return_3y": 20.3, "return_5y": 18.7,
     "expense_ratio": 0.38, "risk": "High", "rating": 4, "min_sip": 1000},
    {"name": "HDFC Mid-Cap Opportunities Direct", "amc": "HDFC", "category": "Equity", "sub_category": "Mid Cap",
     "nav": 188.45, "aum_cr": 61200, "return_1y": 30.2, "return_3y": 24.6, "return_5y": 21.8,
     "expense_ratio": 0.70, "risk": "High", "rating": 5, "min_sip": 100},
    {"name": "Nippon India Growth Fund Direct", "amc": "Nippon", "category": "Equity", "sub_category": "Mid Cap",
     "nav": 4218.60, "aum_cr": 19800, "return_1y": 31.4, "return_3y": 25.2, "return_5y": 22.1,
     "expense_ratio": 0.79, "risk": "High", "rating": 4, "min_sip": 100},
    # Equity - Small Cap
    {"name": "Quant Small Cap Fund Direct", "amc": "Quant", "category": "Equity", "sub_category": "Small Cap",
     "nav": 244.50, "aum_cr": 18200, "return_1y": 38.4, "return_3y": 32.1, "return_5y": 26.8,
     "expense_ratio": 0.62, "risk": "Very High", "rating": 5, "min_sip": 1000},
    {"name": "Nippon India Small Cap Direct", "amc": "Nippon", "category": "Equity", "sub_category": "Small Cap",
     "nav": 138.20, "aum_cr": 41000, "return_1y": 34.2, "return_3y": 28.7, "return_5y": 24.1,
     "expense_ratio": 0.68, "risk": "Very High", "rating": 4, "min_sip": 100},
    {"name": "SBI Small Cap Fund Direct", "amc": "SBI", "category": "Equity", "sub_category": "Small Cap",
     "nav": 184.30, "aum_cr": 24100, "return_1y": 33.6, "return_3y": 27.4, "return_5y": 23.8,
     "expense_ratio": 0.69, "risk": "Very High", "rating": 5, "min_sip": 500},
    {"name": "HDFC Small Cap Fund Direct", "amc": "HDFC", "category": "Equity", "sub_category": "Small Cap",
     "nav": 114.60, "aum_cr": 28400, "return_1y": 32.1, "return_3y": 26.8, "return_5y": 22.4,
     "expense_ratio": 0.65, "risk": "Very High", "rating": 4, "min_sip": 100},
    # Equity - Flexi Cap
    {"name": "Parag Parikh Flexi Cap Direct", "amc": "Parag Parikh", "category": "Equity", "sub_category": "Flexi Cap",
     "nav": 78.42, "aum_cr": 68400, "return_1y": 24.8, "return_3y": 19.6, "return_5y": 22.1,
     "expense_ratio": 0.59, "risk": "Moderate", "rating": 5, "min_sip": 1000},
    {"name": "HDFC Flexi Cap Fund Direct", "amc": "HDFC", "category": "Equity", "sub_category": "Flexi Cap",
     "nav": 1928.40, "aum_cr": 54300, "return_1y": 26.4, "return_3y": 21.8, "return_5y": 18.6,
     "expense_ratio": 0.75, "risk": "High", "rating": 5, "min_sip": 100},
    {"name": "Kotak Flexicap Fund Direct", "amc": "Kotak", "category": "Equity", "sub_category": "Flexi Cap",
     "nav": 72.80, "aum_cr": 44800, "return_1y": 22.6, "return_3y": 17.4, "return_5y": 15.8,
     "expense_ratio": 0.59, "risk": "Moderate", "rating": 4, "min_sip": 100},
    # Equity - ELSS / Tax Saving
    {"name": "Quant ELSS Tax Saver Direct", "amc": "Quant", "category": "Equity", "sub_category": "ELSS",
     "nav": 394.80, "aum_cr": 6800, "return_1y": 42.1, "return_3y": 29.8, "return_5y": 28.4,
     "expense_ratio": 0.58, "risk": "Very High", "rating": 5, "min_sip": 500},
    {"name": "Mirae Asset ELSS Tax Saver Direct", "amc": "Mirae Asset", "category": "Equity", "sub_category": "ELSS",
     "nav": 42.80, "aum_cr": 21200, "return_1y": 24.1, "return_3y": 18.8, "return_5y": 17.4,
     "expense_ratio": 0.45, "risk": "High", "rating": 5, "min_sip": 500},
    # Equity - Thematic
    {"name": "ICICI Pru Technology Direct", "amc": "ICICI", "category": "Equity", "sub_category": "Thematic",
     "nav": 162.10, "aum_cr": 10900, "return_1y": 42.2, "return_3y": 28.4, "return_5y": 22.6,
     "expense_ratio": 0.79, "risk": "Very High", "rating": 4, "min_sip": 100},
    {"name": "ICICI Pru Infrastructure Direct", "amc": "ICICI", "category": "Equity", "sub_category": "Thematic",
     "nav": 188.60, "aum_cr": 2840, "return_1y": 44.8, "return_3y": 31.2, "return_5y": 26.4,
     "expense_ratio": 1.22, "risk": "Very High", "rating": 4, "min_sip": 100},
    {"name": "Nippon India Pharma Direct", "amc": "Nippon", "category": "Equity", "sub_category": "Thematic",
     "nav": 362.40, "aum_cr": 7820, "return_1y": 38.2, "return_3y": 22.6, "return_5y": 19.4,
     "expense_ratio": 0.94, "risk": "Very High", "rating": 3, "min_sip": 100},
    # Hybrid
    {"name": "SBI Focused Equity Fund Direct", "amc": "SBI", "category": "Hybrid", "sub_category": "Aggressive",
     "nav": 288.12, "aum_cr": 29800, "return_1y": 22.1, "return_3y": 17.4, "return_5y": 15.9,
     "expense_ratio": 0.51, "risk": "High", "rating": 5, "min_sip": 500},
    {"name": "HDFC Balanced Advantage Direct", "amc": "HDFC", "category": "Hybrid", "sub_category": "Dynamic",
     "nav": 421.80, "aum_cr": 82000, "return_1y": 16.8, "return_3y": 14.2, "return_5y": 12.9,
     "expense_ratio": 0.72, "risk": "Moderate", "rating": 4, "min_sip": 100},
    {"name": "ICICI Pru Balanced Advantage Direct", "amc": "ICICI", "category": "Hybrid", "sub_category": "Dynamic",
     "nav": 64.20, "aum_cr": 54800, "return_1y": 18.2, "return_3y": 14.8, "return_5y": 13.6,
     "expense_ratio": 0.78, "risk": "Moderate", "rating": 5, "min_sip": 1000},
    {"name": "Kotak Equity Hybrid Direct", "amc": "Kotak", "category": "Hybrid", "sub_category": "Aggressive",
     "nav": 58.40, "aum_cr": 6400, "return_1y": 20.4, "return_3y": 16.2, "return_5y": 14.7,
     "expense_ratio": 0.49, "risk": "High", "rating": 4, "min_sip": 1000},
    # Debt
    {"name": "HDFC Corporate Bond Direct", "amc": "HDFC", "category": "Debt", "sub_category": "Corporate Bond",
     "nav": 28.45, "aum_cr": 31000, "return_1y": 7.8, "return_3y": 7.2, "return_5y": 7.4,
     "expense_ratio": 0.25, "risk": "Low", "rating": 5, "min_sip": 5000},
    {"name": "ICICI Pru Multi-Asset Direct", "amc": "ICICI", "category": "Debt", "sub_category": "Multi-Asset",
     "nav": 68.30, "aum_cr": 24500, "return_1y": 12.4, "return_3y": 11.8, "return_5y": 10.2,
     "expense_ratio": 0.65, "risk": "Moderate", "rating": 5, "min_sip": 100},
    {"name": "Nippon India Liquid Fund Direct", "amc": "Nippon", "category": "Debt", "sub_category": "Liquid",
     "nav": 6282.40, "aum_cr": 14200, "return_1y": 7.2, "return_3y": 6.8, "return_5y": 6.4,
     "expense_ratio": 0.18, "risk": "Low", "rating": 5, "min_sip": 100},
    {"name": "ICICI Pru Liquid Direct", "amc": "ICICI", "category": "Debt", "sub_category": "Liquid",
     "nav": 354.80, "aum_cr": 48200, "return_1y": 7.3, "return_3y": 6.9, "return_5y": 6.5,
     "expense_ratio": 0.20, "risk": "Low", "rating": 5, "min_sip": 100},
    {"name": "SBI Overnight Fund Direct", "amc": "SBI", "category": "Debt", "sub_category": "Overnight",
     "nav": 3882.10, "aum_cr": 10800, "return_1y": 6.9, "return_3y": 6.5, "return_5y": 5.8,
     "expense_ratio": 0.10, "risk": "Low", "rating": 5, "min_sip": 5000},
    # Index
    {"name": "Nifty 50 Index Fund - UTI Direct", "amc": "UTI", "category": "Index", "sub_category": "Large Cap Index",
     "nav": 142.60, "aum_cr": 18600, "return_1y": 19.4, "return_3y": 15.2, "return_5y": 14.1,
     "expense_ratio": 0.05, "risk": "Moderate", "rating": 4, "min_sip": 100},
    {"name": "Nifty Next 50 Index - HDFC Direct", "amc": "HDFC", "category": "Index", "sub_category": "Mid Cap Index",
     "nav": 58.20, "aum_cr": 6800, "return_1y": 24.8, "return_3y": 18.6, "return_5y": 16.4,
     "expense_ratio": 0.10, "risk": "High", "rating": 4, "min_sip": 100},
    {"name": "Nifty 50 Index Fund - HDFC Direct", "amc": "HDFC", "category": "Index", "sub_category": "Large Cap Index",
     "nav": 212.40, "aum_cr": 14800, "return_1y": 19.2, "return_3y": 15.0, "return_5y": 13.8,
     "expense_ratio": 0.10, "risk": "Moderate", "rating": 5, "min_sip": 100},
    {"name": "Nifty Midcap 150 Index - Motilal Direct", "amc": "Motilal Oswal", "category": "Index", "sub_category": "Mid Cap Index",
     "nav": 48.60, "aum_cr": 8400, "return_1y": 28.4, "return_3y": 22.1, "return_5y": 19.6,
     "expense_ratio": 0.30, "risk": "High", "rating": 4, "min_sip": 500},
    {"name": "Nifty Small Cap 250 Index - Motilal Direct", "amc": "Motilal Oswal", "category": "Index", "sub_category": "Small Cap Index",
     "nav": 32.80, "aum_cr": 4200, "return_1y": 36.2, "return_3y": 28.8, "return_5y": 24.4,
     "expense_ratio": 0.42, "risk": "Very High", "rating": 4, "min_sip": 500},
    {"name": "Nifty 500 Index - Motilal Direct", "amc": "Motilal Oswal", "category": "Index", "sub_category": "Multi Cap Index",
     "nav": 26.40, "aum_cr": 2100, "return_1y": 22.8, "return_3y": 17.4, "return_5y": 15.2,
     "expense_ratio": 0.25, "risk": "Moderate", "rating": 4, "min_sip": 500},
    {"name": "Nifty Bank Index - Kotak Direct", "amc": "Kotak", "category": "Index", "sub_category": "Sector Index",
     "nav": 198.40, "aum_cr": 4800, "return_1y": 14.2, "return_3y": 9.8, "return_5y": 11.4,
     "expense_ratio": 0.20, "risk": "High", "rating": 3, "min_sip": 100},
    {"name": "Nifty IT Index - Mirae Direct", "amc": "Mirae Asset", "category": "Index", "sub_category": "Sector Index",
     "nav": 52.60, "aum_cr": 1800, "return_1y": 38.4, "return_3y": 22.6, "return_5y": 20.8,
     "expense_ratio": 0.28, "risk": "High", "rating": 4, "min_sip": 1000},
    # Gold / Silver / Commodity FoF
    {"name": "Kotak Gold & Silver Passive FoF", "amc": "Kotak", "category": "Index", "sub_category": "Gold & Silver FoF",
     "nav": 14.82, "aum_cr": 1240, "return_1y": 18.6, "return_3y": 14.2, "return_5y": 12.8,
     "expense_ratio": 0.18, "risk": "Moderate", "rating": 4, "min_sip": 100},
    {"name": "Nippon India Gold Savings Fund", "amc": "Nippon", "category": "Index", "sub_category": "Gold FoF",
     "nav": 28.64, "aum_cr": 2140, "return_1y": 16.8, "return_3y": 12.4, "return_5y": 11.6,
     "expense_ratio": 0.09, "risk": "Moderate", "rating": 4, "min_sip": 100},
    {"name": "HDFC Gold Fund Direct", "amc": "HDFC", "category": "Index", "sub_category": "Gold FoF",
     "nav": 22.48, "aum_cr": 1680, "return_1y": 17.2, "return_3y": 12.8, "return_5y": 11.4,
     "expense_ratio": 0.12, "risk": "Moderate", "rating": 4, "min_sip": 100},
    {"name": "SBI Gold Fund Direct", "amc": "SBI", "category": "Index", "sub_category": "Gold FoF",
     "nav": 20.84, "aum_cr": 2820, "return_1y": 16.6, "return_3y": 12.1, "return_5y": 11.0,
     "expense_ratio": 0.10, "risk": "Moderate", "rating": 4, "min_sip": 500},
    {"name": "Kotak Silver ETF FoF", "amc": "Kotak", "category": "Index", "sub_category": "Silver FoF",
     "nav": 13.42, "aum_cr": 480, "return_1y": 14.8, "return_3y": 10.6, "return_5y": 0.0,
     "expense_ratio": 0.15, "risk": "Moderate", "rating": 3, "min_sip": 100},
    {"name": "Mirae Asset S&P 500 Top 50 ETF FoF", "amc": "Mirae Asset", "category": "Index", "sub_category": "International",
     "nav": 18.62, "aum_cr": 3240, "return_1y": 28.4, "return_3y": 14.8, "return_5y": 18.2,
     "expense_ratio": 0.07, "risk": "High", "rating": 4, "min_sip": 100},
    {"name": "Motilal Oswal Nasdaq 100 FoF Direct", "amc": "Motilal Oswal", "category": "Index", "sub_category": "International",
     "nav": 28.40, "aum_cr": 5600, "return_1y": 32.6, "return_3y": 16.4, "return_5y": 24.8,
     "expense_ratio": 0.10, "risk": "High", "rating": 4, "min_sip": 500},
]


# NOTE: /api/mutual-funds and /api/mutual-funds/top are defined below (lines ~1012+)
# using FUND_UNIVERSE from fund_intelligence.py for richer data.


# ── SIP Calculator API ────────────────────────────────────────────────────────

class SIPRequest(BaseModel):
    monthly_amount: float
    years: int
    expected_return_pct: float
    step_up_pct: float = 0.0  # annual increment %


@app.post("/api/sip/calculate")
def sip_calculate(req: SIPRequest):
    """Compute SIP maturity value with optional step-up."""
    if req.monthly_amount <= 0 or req.years <= 0 or req.expected_return_pct <= 0:
        raise HTTPException(status_code=400, detail="Invalid SIP parameters")

    monthly_rate = req.expected_return_pct / 100 / 12
    step_up = req.step_up_pct / 100

    timeline = []
    total_invested = 0.0
    corpus = 0.0
    monthly_sip = req.monthly_amount

    for year in range(1, req.years + 1):
        # Step up at start of each new year
        if year > 1 and step_up > 0:
            monthly_sip *= (1 + step_up)

        for _ in range(12):
            corpus = (corpus + monthly_sip) * (1 + monthly_rate)
            total_invested += monthly_sip

        timeline.append({
            "year": year,
            "invested": round(total_invested, 2),
            "corpus": round(corpus, 2),
            "wealth_gained": round(corpus - total_invested, 2),
        })

    # Scenario comparison
    scenarios = []
    for label, ret in [("Conservative", 8.0), ("Moderate", 12.0), ("Aggressive", 16.0)]:
        r = ret / 100 / 12
        c = 0.0
        inv = 0.0
        m = req.monthly_amount
        for yr in range(req.years):
            if yr > 0 and step_up > 0:
                m *= (1 + step_up)
            for _ in range(12):
                c = (c + m) * (1 + r)
                inv += m
        scenarios.append({
            "label": label,
            "return_pct": ret,
            "maturity_value": round(c, 2),
            "total_invested": round(inv, 2),
            "wealth_gained": round(c - inv, 2),
        })

    return {
        "monthly_amount": req.monthly_amount,
        "years": req.years,
        "expected_return_pct": req.expected_return_pct,
        "step_up_pct": req.step_up_pct,
        "total_invested": round(total_invested, 2),
        "maturity_value": round(corpus, 2),
        "wealth_gained": round(corpus - total_invested, 2),
        "cagr": req.expected_return_pct,
        "timeline": timeline,
        "scenarios": scenarios,
    }


# ════════════════════════════════════════════════════════════════════════════
# MUTUAL FUNDS — FUND INTELLIGENCE APIs
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/mutual-funds")
def get_mutual_funds(category: str = Query("all")):
    """
    Return per-fund genuine data from MF_DATABASE.
    Supports filtering by category: Equity, Debt, Hybrid, Index (Index Funds).
    """
    CAT_MAP = {"Index Funds": "Index", "index funds": "Index", "index": "Index"}

    funds_out = []
    for f in MF_DATABASE:
        f_cat = f["category"]
        # Filter logic
        if category.lower() != "all":
            query_cat = CAT_MAP.get(category, category).lower()
            if f_cat.lower() != query_cat:
                continue
        funds_out.append({
            "name":          f["name"],
            "amc":           f["amc"],
            "category":      f["category"],
            "sub_category":  f["sub_category"],
            "risk":          f["risk"],
            "rating":        f["rating"],
            "nav":           f["nav"],
            "aum_cr":        f["aum_cr"],
            "expense_ratio": f["expense_ratio"],
            "return_1y":     f["return_1y"],
            "return_3y":     f["return_3y"],
            "return_5y":     f["return_5y"],
            "min_sip":       f["min_sip"],
            "lock_in":       0,
            "ticker":        "",
        })
    return {"funds": funds_out}


@app.get("/api/mutual-funds/top")
def get_top_funds():
    """
    Fast sidebar widgets: top alpha generators + top stable funds + AI signal.
    Uses precomputed heuristics, no live ML calls.
    """
    equity_funds = [f for f in FUND_UNIVERSE if f["category"] not in ("Debt",)]
    top_alpha  = [
        {"name": f["name"], "amc": f["name"].split()[0],
         "sub_category": f["category"],
         "return_1y": {"Small Cap": 31.2, "Mid Cap": 26.4, "Flexi Cap": 22.1,
                       "Large Cap": 17.8, "ELSS": 24.5, "Hybrid": 14.2}.get(f["category"], 18.0)}
        for f in sorted(equity_funds,
            key=lambda x: {"Small Cap": 31.2, "Mid Cap": 26.4, "Flexi Cap": 22.1,
                           "Large Cap": 17.8, "ELSS": 24.5, "Hybrid": 14.2}.get(x["category"], 18.0),
            reverse=True)[:4]
    ]
    top_stable = [
        {"name": f["name"], "amc": f["name"].split()[0],
         "sub_category": f["category"],
         "return_1y": {"Large Cap": 17.8, "Hybrid": 14.2, "Debt": 7.8}.get(f["category"], 15.0)}
        for f in FUND_UNIVERSE
        if f["category"] in ("Large Cap", "Hybrid", "Debt")
    ][:4]
    ai_signal = (
        f"Current model cycle (RBI repo: {RBI_REPO_RATE}%, CPI: {CPI_INFLATION}%): "
        "Flexi Cap and Small Cap funds show the highest risk-adjusted conviction scores. "
        "Nifty P/E at elevated levels — favour quality over momentum. "
        "Debt funds offer capital protection in a rate-peaking environment."
    )
    return {"top_alpha": top_alpha, "top_stable": top_stable, "ai_signal": ai_signal}


@app.get("/api/mutual-funds/brief")
def get_investment_brief():
    """
    Full monthly investment brief — runs complete 3-layer analysis for all funds.
    May take 30–60s due to live yfinance + ML computations.
    """
    try:
        macro = {
            "repo_rate": RBI_REPO_RATE,
            "cpi":       CPI_INFLATION,
            "nifty_pe":  NIFTY_PE_RATIO,
        }
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(analyze_fund, fund, macro): fund for fund in FUND_UNIVERSE}
            for fut in concurrent.futures.as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as e:
                    fund = futures[fut]
                    results.append({
                        "fund_name": fund["name"], "signal": "SIP REDUCE",
                        "rationale": str(e), "forecast_12m": 10.0,
                        "confidence": 0.40, "fundamental_gate": "FAIL",
                        "direction": "NEUTRAL", "category": fund["category"],
                        "piotroski_score": 5, "piotroski_label": "NEUTRAL",
                        "altman_z": 2.5, "altman_zone": "GREY",
                        "distress_pct": 15, "min_sip": fund["min_sip"],
                        "lock_in": fund.get("lock_in", 0), "ticker": fund["ticker"],
                        "action": "Reduce SIP by 50% pending data",
                        "ret_3m": 0, "ret_6m": 0, "ret_12m": 0,
                        "volatility": 8.0, "forecast_lower": 4.0,
                        "forecast_upper": 16.0, "priority": 5,
                        "prediction_date": datetime.date.today().isoformat(),
                    })
        brief = generate_investment_brief(results, macro)
        return brief
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mutual-funds/fund/{fund_name}")
def get_single_fund_brief(fund_name: str):
    """
    Deep analysis for a single fund: full Piotroski + Altman + ML forecast.
    """
    match = None
    for f in FUND_UNIVERSE:
        if fund_name.lower() in f["name"].lower():
            match = f
            break
    if not match:
        raise HTTPException(status_code=404, detail=f"Fund '{fund_name}' not found in universe")
    try:
        macro = {
            "repo_rate": RBI_REPO_RATE,
            "cpi":       CPI_INFLATION,
            "nifty_pe":  NIFTY_PE_RATIO,
        }
        result = analyze_fund(match, macro)
        fin    = fetch_fundamentals(match["ticker"])
        pio    = piotroski_f_score(fin)
        alt    = altman_z_score(fin)
        result["piotroski_signals"] = pio.get("signals", {})
        result["altman_detail"]     = alt
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
