from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # Forecast dates are local to the fields, so "today" must be too.
    timezone: str = "America/Argentina/Buenos_Aires"
    # Points a probability must rise over the last notice to notify again.
    renotify_step: int = 15


settings = Settings()
