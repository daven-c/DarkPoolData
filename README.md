# DarkPoolData Platform

An institutional-grade platform to ingest, explore, backtest, and alert on off-exchange (dark pool/TRF) trade data using the **Massive.com** (formerly Polygon.io) market data APIs. 

The platform integrates a custom Python simulation engine, a FastAPI backend router, a React + Vite dashboard web app, a Discord gateway announcer, and an interactive Marimo exploratory notebook.

---

## 📂 Project Architecture

```
├── backend/
│   ├── app/
│   │   ├── api/             # API Router controllers
│   │   │   ├── darkpool.py   # TRF trade details and aggregates
│   │   │   ├── backtest.py   # Runs historical backtests
│   │   │   └── portfolio.py  # Active holdings and transactions ledger
│   │   ├── core/
│   │   │   └── config.py     # Configuration variables loader
│   │   ├── services/
│   │   │   ├── massive.py    # Massive.com REST API client interface
│   │   │   └── discord.py    # Broadcaster to bot receiver webhook
│   │   └── main.py          # FastAPI application server entrypoint
│   └── .env                  # Local API keys and credentials
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Single-Page Dashboard (Recharts + router tabs)
│   │   ├── index.css        # Premium dark mode glassmorphic stylesheet
│   │   └── main.tsx
│   └── package.json          # Node dependencies (React 19, recharts, lucide-react)
├── backtester/
│   ├── engine.py            # Chronological tick-by-tick simulation loop
│   ├── portfolio.py         # Position management, trade logs, and metrics math
│   ├── data.py              # APIDataProvider, CSVDataProvider, MockDataProvider
│   ├── strategy.py          # Abstract base Strategy class
│   └── strategies.py        # Configurable indicator strategies
├── bot/
│   └── bot.py               # discord.py bot + integrated aiohttp webhook server
├── notebooks/
│   ├── darkpool_exploration.py # Marimo interactive data notebook
│   └── csv_downloader.py        # Marimo utility to download and inspect tick CSVs
└── requirements.txt          # Shared Python dependencies
```

---

## 🛠️ Prerequisites & Environment Setup

Ensure you have **Python 3.10+** and **Node 18+** installed locally.

### 1. Create a Unified Virtual Environment
Since the shared `backtester` code is used by the backend, Discord bot, and notebooks, configure a single virtual environment at the project root:

```bash
# From the project root directory
python3 -m venv .venv
source .venv/bin/activate

# Install shared requirements
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy and fill in your API credentials in the configuration file located at `.env`:

```env
# Massive.com API Key (formerly Polygon.io)
MASSIVE_API_KEY=YOUR_MASSIVE_API_KEY_HERE

# Discord Configuration (Optional)
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
DISCORD_CHANNEL_ID=YOUR_DISCORD_CHANNEL_ID_HERE
```

---

## 🚀 Running the Services

Activate the virtual environment (`source .venv/bin/activate`) before starting any Python processes.

### 1. Start the FastAPI Backend Server
The backend handles routing, aggregates TRF metrics from Massive.com, runs simulations, and triggers alerts.

```bash
python3 backend/app/main.py
```
* The API will boot on `http://localhost:8000`.
* Open `http://localhost:8000/docs` to access the interactive Swagger documentation.

### 2. Launch the React Web Application
Install the frontend node modules and launch the Vite dev server:

```bash
# Navigate to frontend folder or execute:
npm install --prefix frontend
npm run dev --prefix frontend
```
* The glassmorphic dashboard will run at `http://localhost:5173`.
* Switch between the **Backtest Engine** (run strategy simulations, view equity growth curves, and push manual alerts to Discord) and **Dark Pool Scanner** (pie chart volume distribution and detailed trade logs) tabs.

### 3. Start the Discord Alert Bot (Optional)
Starts the bot client and activates its webhook listener:

```bash
python3 bot/bot.py
```
* The bot registers commands (e.g. `!status`, `!ping`) and listens for POST events on `http://localhost:5000/alert` to broadcast trade indicators to your channel.

### 4. Open the Marimo Notebooks
To interactively prototype custom strategies:

```bash
marimo edit notebooks/darkpool_exploration.py
```

To run the utility for downloading trade details to CSV files:

```bash
marimo edit notebooks/csv_downloader.py
```

---

## 📈 Backtesting Custom Strategies

You can create plug-and-play strategies by subclassing `Strategy` (in `backtester/strategy.py`) and implementing the `on_data` method:

```python
from backtester import Strategy

class MyStrategy(Strategy):
    def on_data(self, current_time, data, portfolio):
        # Fetch indicators
        # Trigger portfolio.buy(symbol, qty, price, current_time) 
        # or portfolio.sell(symbol, qty, price, current_time)
        pass
```

When calling the `/api/v1/backtest/run` endpoint, if the Massive.com API key is not configured, the engine will fallback to the `MockDataProvider` to simulate market environments so you can test integrations instantly.
