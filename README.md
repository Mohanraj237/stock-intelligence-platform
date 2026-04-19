# Indian Stock AI Agent

Production-ready Stage 1 and Stage 2 starter app for Indian stock analysis across NSE/BSE.

## Features

- Streamlit multipage dashboard: Dashboard, Scanner, Watchlist, Settings
- FastAPI backend for stock analysis, scanner results, and watchlist APIs
- Multi-provider stock data: direct Yahoo chart API, NSE public endpoints, Twelve Data, Alpha Vantage
- Technical indicators: RSI, MACD, 20 EMA, 50 DMA, 200 DMA, Bollinger Bands
- Support, resistance, trend direction, and breakout probability
- Plotly candlestick chart with moving averages and volume
- TradingView technical recommendation enrichment
- Screener.in and Trendlyne fundamental/snapshot parsers with Yahoo Finance fallback
- Explainable scanner tabs for data sources, technical checks, pattern checks, fundamental checks, TradingView checks, and final score calculation
- OpenAI-powered stock analysis summary with rule-based fallback
- SQLite watchlist and settings storage
- Bonus hooks: Telegram alerts, daily scanner report, PDF report export

## Project Structure

```text
indian-stock-ai-agent/
  app/
    main.py
    pages/
      Scanner.py
      Watchlist.py
      Settings.py
  backend/
    main.py
    stock_data.py
    technical_analysis.py
    fundamentals.py
    ai_analysis.py
    scanner.py
    watchlist.py
    database.py
  data/
  utils/
  .env
  .env.example
  requirements.txt
  README.md
```

## Local Setup

```powershell
cd "C:\Users\mohan\Stock App\indian-stock-ai-agent"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Update `.env`:

```text
OPENAI_API_KEY=your_openai_key
DEFAULT_WATCHLIST=RELIANCE,TCS,INFY,HDFCBANK,TATAMOTORS
REFRESH_INTERVAL_SECONDS=300
DATABASE_PATH=data/stock_agent.db
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TWELVE_DATA_API_KEY=
ALPHA_VANTAGE_API_KEY=
```

## Run Streamlit

```powershell
streamlit run app/main.py
```

## Run FastAPI

```powershell
uvicorn backend.main:app --reload
```

Then open:

- Streamlit app: http://localhost:8501
- FastAPI docs: http://localhost:8000/docs

## Scanner Pages

The Scanner page includes:

- Breakout Stocks
- Undervalued Stocks
- Swing Trade Stocks
- Strong Fundamentals

Each scan ranks the top 10 matches from the configured NSE universe. Keep the universe smaller for faster scans, because live quote and fundamental lookups take time.

## Deploy on Streamlit Cloud

1. Push this folder to GitHub.
2. Create a Streamlit Cloud app.
3. Set the main file path to `app/main.py`.
4. Add secrets/environment variables:
   - `OPENAI_API_KEY`
   - `DEFAULT_WATCHLIST`
   - `REFRESH_INTERVAL_SECONDS`
5. Deploy.

SQLite works on Streamlit Cloud for lightweight state, but the filesystem can be ephemeral. For persistent multi-user production state, upgrade `backend/database.py` to Postgres.

## Deploy FastAPI on Render

1. Create a new Web Service on Render.
2. Use Python 3.11.
3. Build command:

```bash
pip install -r requirements.txt
```

4. Start command:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

5. Add environment variables from `.env.example`.

## Production Notes

- Screener.in may block automated requests. The app catches that and falls back to Yahoo Finance fields or an empty parser structure.
- Trendlyne may block automated requests or require stock-specific numeric URLs. It is used as enrichment, not as the only source.
- If free public providers throttle or block requests, add `TWELVE_DATA_API_KEY` or `ALPHA_VANTAGE_API_KEY` in Settings or `.env`.
- yfinance is intentionally not used because rate-limit failures slowed down scans.
- OpenAI analysis falls back to a local rule-based summary if no key is configured or the API request fails.
- This is an educational research tool, not financial advice.
- For high-scale use, add caching, background jobs, rate limits, and a durable database.

## Upgrade Path

- Replace SQLite with Postgres.
- Add Redis caching for scanner results.
- Add scheduled daily reports using `utils/daily_report.py`.
- Add broker integrations only after proper authentication, audit logging, and compliance checks.
