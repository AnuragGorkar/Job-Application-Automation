import os
from dotenv import load_dotenv

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    _instance = None

    def __new__(cls, self, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    port: int = 8000
    env: str = "development"
    log_overwrite: bool = False

    model_config = SettingsConfigDict(env_file=".env")

    GMAIL_USERNAME: str = os.getenv("GMAIL_USERNAME")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD")
    IMAP_SERVER: str = os.getenv("IMAP_SERVER", "imap.gmail.com")

settings = Settings()