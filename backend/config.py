from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    default_watchlist: str = Field(
        default="RELIANCE,TCS,INFY,HDFCBANK,TATAMOTORS",
        alias="DEFAULT_WATCHLIST",
    )
    refresh_interval_seconds: int = Field(default=300, alias="REFRESH_INTERVAL_SECONDS")
    database_path: str = Field(default="data/stock_agent.db", alias="DATABASE_PATH")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    twelve_data_api_key: str = Field(default="", alias="TWELVE_DATA_API_KEY")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    @property
    def db_file(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def watchlist_symbols(self) -> list[str]:
        return [item.strip().upper() for item in self.default_watchlist.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
