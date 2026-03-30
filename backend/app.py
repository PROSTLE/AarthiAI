
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from stock_data import fetch_stock_data, add_technical_indicators, get_stock_info, fetch_live_price, fetch_chart_data, fetch_india_vix
from sentiment import analyze_sentiment
from model import train_and_predict
from technical_signals import score_technical_signals
from llm_analysis import analyze_with_llm
from intraday_model import generate_intraday_signal
from trader import (
    get_portfolio, reset_portfolio, toggle_bot,
    evaluate_trade_signal, execute_sell, execute_buy, check_position,
    compute_dynamic_levels, detect_market_regime,
    add_to_balance, withdraw_from_balance, get_wallet_transactions,
    get_value_history,
)
import concurrent.futures

app = FastAPI(title="StockSense AI", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "StockSense AI API v3.0 is running 🚀"}


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


# ── Mutual Funds API ──────────────────────────────────────────────────────────

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
    # Equity - Mid Cap
    {"name": "Axis Midcap Fund Direct", "amc": "Axis", "category": "Equity", "sub_category": "Mid Cap",
     "nav": 112.60, "aum_cr": 22400, "return_1y": 28.2, "return_3y": 22.1, "return_5y": 19.4,
     "expense_ratio": 0.47, "risk": "High", "rating": 5, "min_sip": 500},
    {"name": "Kotak Emerging Equity Direct", "amc": "Kotak", "category": "Equity", "sub_category": "Mid Cap",
     "nav": 108.90, "aum_cr": 18900, "return_1y": 25.6, "return_3y": 20.3, "return_5y": 18.7,
     "expense_ratio": 0.38, "risk": "High", "rating": 4, "min_sip": 1000},
    # Equity - Small Cap
    {"name": "Quant Small Cap Fund Direct", "amc": "Quant", "category": "Equity", "sub_category": "Small Cap",
     "nav": 244.50, "aum_cr": 18200, "return_1y": 38.4, "return_3y": 32.1, "return_5y": 26.8,
     "expense_ratio": 0.62, "risk": "Very High", "rating": 5, "min_sip": 1000},
    {"name": "Nippon India Small Cap Direct", "amc": "Nippon", "category": "Equity", "sub_category": "Small Cap",
     "nav": 138.20, "aum_cr": 41000, "return_1y": 34.2, "return_3y": 28.7, "return_5y": 24.1,
     "expense_ratio": 0.68, "risk": "Very High", "rating": 4, "min_sip": 100},
    # Equity - Thematic
    {"name": "ICICI Pru Technology Direct", "amc": "ICICI", "category": "Equity", "sub_category": "Thematic",
     "nav": 162.10, "aum_cr": 10900, "return_1y": 42.2, "return_3y": 28.4, "return_5y": 22.6,
     "expense_ratio": 0.79, "risk": "Very High", "rating": 4, "min_sip": 100},
    # Hybrid
    {"name": "SBI Focused Equity Fund Direct", "amc": "SBI", "category": "Hybrid", "sub_category": "Aggressive",
     "nav": 288.12, "aum_cr": 29800, "return_1y": 22.1, "return_3y": 17.4, "return_5y": 15.9,
     "expense_ratio": 0.51, "risk": "High", "rating": 5, "min_sip": 500},
    {"name": "HDFC Balanced Advantage Direct", "amc": "HDFC", "category": "Hybrid", "sub_category": "Dynamic",
     "nav": 421.80, "aum_cr": 82000, "return_1y": 16.8, "return_3y": 14.2, "return_5y": 12.9,
     "expense_ratio": 0.72, "risk": "Moderate", "rating": 4, "min_sip": 100},
    # Debt
    {"name": "HDFC Corporate Bond Direct", "amc": "HDFC", "category": "Debt", "sub_category": "Corporate Bond",
     "nav": 28.45, "aum_cr": 31000, "return_1y": 7.8, "return_3y": 7.2, "return_5y": 7.4,
     "expense_ratio": 0.25, "risk": "Low", "rating": 5, "min_sip": 5000},
    {"name": "ICICI Pru Multi-Asset Direct", "amc": "ICICI", "category": "Debt", "sub_category": "Multi-Asset",
     "nav": 68.30, "aum_cr": 24500, "return_1y": 12.4, "return_3y": 11.8, "return_5y": 10.2,
     "expense_ratio": 0.65, "risk": "Moderate", "rating": 5, "min_sip": 100},
    # Index
    {"name": "Nifty 50 Index Fund - UTI Direct", "amc": "UTI", "category": "Index", "sub_category": "Large Cap Index",
     "nav": 142.60, "aum_cr": 18600, "return_1y": 19.4, "return_3y": 15.2, "return_5y": 14.1,
     "expense_ratio": 0.05, "risk": "Moderate", "rating": 4, "min_sip": 100},
    {"name": "Nifty Next 50 Index - HDFC Direct", "amc": "HDFC", "category": "Index", "sub_category": "Mid Cap Index",
     "nav": 58.20, "aum_cr": 6800, "return_1y": 24.8, "return_3y": 18.6, "return_5y": 16.4,
     "expense_ratio": 0.10, "risk": "High", "rating": 4, "min_sip": 100},
]


@app.get("/api/mutual-funds")
def mutual_funds(category: str = Query("all")):
    """Return curated list of Indian mutual funds, optionally filtered by category."""
    data = MF_DATABASE
    if category.lower() != "all":
        data = [f for f in MF_DATABASE if f["category"].lower() == category.lower()]
    return {"funds": data, "count": len(data), "categories": ["Equity", "Debt", "Hybrid", "Index"]}


@app.get("/api/mutual-funds/top")
def mutual_funds_top():
    """Return top performers and AI signal."""
    top_alpha = sorted(MF_DATABASE, key=lambda x: x["return_1y"], reverse=True)[:4]
    top_stable = sorted(MF_DATABASE, key=lambda x: x.get("return_3y", 0) / max(0.1, x["expense_ratio"]), reverse=True)[:4]
    return {
        "top_alpha": top_alpha,
        "top_stable": top_stable,
        "ai_signal": "Indian Large-cap equity funds showing 84% probability of outperformed alpha in Q4 based on RBI interest rate trajectories.",
    }


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

