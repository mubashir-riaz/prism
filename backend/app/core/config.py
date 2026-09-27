from typing import Literal, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Prism"
    APP_ENV: Literal["dev", "staging", "prod"] = "dev"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/v1"
    DATABASE_URL: Optional[str] = "postgresql+asyncpg://postgres:postgres@localhost:5432/prism"
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def validate_database_url(self) -> "Settings":
        if self.APP_ENV in ("staging", "prod"):
            if not self.DATABASE_URL or not self.DATABASE_URL.strip():
                raise ValueError(
                    f"DATABASE_URL must be set and non-empty in '{self.APP_ENV}' environment."
                )
        return self


settings = Settings()
