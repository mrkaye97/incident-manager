from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    slack_bot_oauth_token: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
