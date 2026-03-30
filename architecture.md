# StockSense AI — System Flow

This flowchart describes how a single prediction request is processed through the system.

```mermaid
graph LR
    %% User Entry
    User((User)) -- "Enters Ticker" --> API[FastAPI Entry Point]

    %% Data Layer
    subgraph "Data Acquisition"
        API --> YF[yfinance: Market OHLCV]
        API --> News[News Aggregator: RSS/APIs]
    end

    %% Engine Layer
    subgraph "AI Core Processing"
        YF --> Indicators[Technical Signals: RSI, MACD, SMA]
        YF --> LSTM[Deep Learning: LSTM Pattern Recognition]
        News --> FinBERT[NLP: FinBERT Sentiment Scoring]
        News --> Gemini[LLM: Gemini Market Reasoning]
    end

    %% Synthesis Layer
    subgraph "Decision Engine"
        Indicators & LSTM & FinBERT & Gemini --> Blender[5-Factor Weighted Blender]
        Blender --> Regime[Crisis/Volatility Detection]
    end

    %% Output Layer
    Regime --> Dashboard[[Final User Dashboard]]
    Dashboard -- "JSON/Chart" --> User
```

### Flow Components:
1. **User Request**: Initiated when a ticker (e.g., `RELIANCE.NS`) is searched.
2. **Data Acquisition**: Simultaneously fetches 2 years of price history and current news.
3. **AI Logic**:
   - **LSTM**: Predicts price movement based on historical "waves."
   - **Technical Signals**: Checks momentum and volume.
   - **FinBERT**: Measures if the news is "Bullish" or "Bearish."
   - **Gemini**: Provides a human-like explanation of why the score is what it is.
4. **Blender**: Adjusts weights dynamically (e.g., news counts more if volatility is high).
5. **Dashboard**: Returns the 5-day forecast, confidence level, and risk assessment.
