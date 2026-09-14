from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    slack_bot_oauth_token: str

    slack_client_id: str

    slack_client_secret: str

    pushover_app_token: str

    status_page_url: str = "https://status.example.com"

    app_url: str = "https://localhost:3000"

    api_url: str | None = None

    cors_origins: list[str] = ["https://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
