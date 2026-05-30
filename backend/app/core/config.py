from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "DarkPoolData Platform"

    # Massive.com (formerly Polygon.io) API key
    MASSIVE_API_KEY: str = ""

    # Discord configuration
    DISCORD_BOT_TOKEN: str = ""
    DISCORD_CHANNEL_ID: Optional[str] = None

    # Application Config
    PORTFOLIO_INITIAL_CASH: float = 100000.0
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Dashboard — universe & data source
    DASHBOARD_UNIVERSE_SIZE: int = 1000           # Top-N tickers by prior-day $ volume. Bigger = catches quieter names institutions accumulate. Env-tunable (1000-3000); ceiling is your Massive WS per-symbol subscription cap. Prior-day seeding cost scales linearly (background, non-blocking).
    DASHBOARD_SEED_PRIOR_DAY: bool = True         # Backfill prior-day TRF totals on startup
    DASHBOARD_WS_FEED: str = "delayed"            # "realtime" or "delayed" (must match your Massive plan)

    # Dashboard — aggregation rules
    DASHBOARD_TRF_EXCHANGE_ID: int = 4            # Exchange ID for FINRA TRF (off-exchange / dark pool)
    DASHBOARD_BLOCK_SIZE_THRESHOLD: int = 10_000  # Shares per trade to count as a BLOCK TRADE

    # Dashboard — API limits
    DASHBOARD_DEFAULT_LIMIT: int = 15             # Default page size for /snapshot
    DASHBOARD_MAX_LIMIT: int = 5_000              # Upper bound for ?limit= (also gates initial-load fetch)

    # Dashboard — streaming
    DASHBOARD_SSE_QUEUE_MAX: int = 1_000          # Per-subscriber backpressure queue; deltas dropped if full

    # Alerts — signal dispatch
    ALERTS_SSE_QUEUE_MAX: int = 1_000             # Per-subscriber backpressure queue for /alerts/stream
    ALERTS_DEFAULT_COOLDOWN_S: int = 300          # Default per-(rule,symbol) cooldown in seconds
    ALERTS_FORWARD_HORIZONS_MIN: List[int] = [5, 30, 1440]  # Forward-return stamping horizons (minutes)
    ALERTS_DISCORD_ENABLED: bool = True           # Set False to silence Discord without removing wiring
    ALERTS_RECENT_LIMIT: int = 100                # Max rows returned by /alerts/recent

    # Backtesting
    BACKTEST_DEFAULT_NOTIONAL: float = 10_000.0   # Default per-signal position size for P&L backtest

    class Config:
        env_file = (".env", "backend/.env", "../.env")
        extra = "ignore"


settings = Settings()
