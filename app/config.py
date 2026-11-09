from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # Forecast dates are local to the fields, so "today" must be too.
    timezone: str = "America/Argentina/Buenos_Aires"
    # Percentage points above the last notice needed to notify again.
    renotify_step: int = Field(default=15, ge=1)
    # Seconds between worker cycles. Should follow how often the ingestion writes forecasts.
    evaluation_interval: float = Field(default=60, gt=0)


settings = Settings()
