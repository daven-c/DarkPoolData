from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "DarkPoolData Platform"
    
    # Massive.com (formerly Polygon.io) API key
    MASSIVE_API_KEY: str = ""
    
    # Discord configuration
    DISCORD_BOT_TOKEN: str = ""
    DISCORD_CHANNEL_ID: Optional[int] = None
    
    # Application Config
    PORTFOLIO_INITIAL_CASH: float = 100000.0
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
