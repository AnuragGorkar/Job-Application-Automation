import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # System Configurations
    port: int = 8000
    env: str = "development"
    log_overwrite: bool = False
    
    # Email Configurations 
    GMAIL_USERNAME: str
    GMAIL_APP_PASSWORD: str
    IMAP_SERVER: str = "imap.gmail.com"

    # Configure Pydantic to read from the environment file
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore" # Prevents crashing if extra variables exist in .env
    )

settings = Settings()
