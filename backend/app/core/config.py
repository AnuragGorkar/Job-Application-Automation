from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = 8000
    env: str = "development"
    log_overwrite: bool = False

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()