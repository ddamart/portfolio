from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_path: str = "data/portfolio.duckdb"
    debug: bool = False
    log_level: str = "INFO"
    price_refresh_ttl_open: int = 15
    price_refresh_ttl_closed: int = 1440

    # LLM-powered import
    llm_provider: str = "gemini"          # "gemini" | "anthropic"
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = ""                   # blank → provider default


settings = Settings()
