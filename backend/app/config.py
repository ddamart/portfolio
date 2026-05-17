from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_path: str = "data/portfolio.duckdb"
    debug: bool = False
    log_level: str = "INFO"
    # Minutes before prices are considered stale while market is open
    price_refresh_ttl_open: int = 15
    # Minutes before prices are considered stale while market is closed (24h default)
    price_refresh_ttl_closed: int = 1440


settings = Settings()
