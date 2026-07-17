import os
from functools import lru_cache
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = os.getenv("ENV_FILE", ".env.dev")

class BaseConfig(BaseSettings):
    app_name: str = "job-application-automation"
    
    env_state: str 
    
    # Backend port
    be_host: str
    be_port: int
    
    # DB Variables
    db_user: str
    db_pass: str
    db_name: str
    db_port: int
    @computed_field
    def db_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_pass}@localhost:{self.db_port}/{self.db_name}"

    # Logging Variables
    log_overwrite: bool
     
    # G-mail Variables
    gmail_username: str
    gmail_app_password: str
    imap_server: str

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

class DevConfig(BaseConfig):
    debug: bool = True
    log_overwrite: bool = True

class ProdConfig(BaseConfig):
    debug: bool = False

@lru_cache
def get_settings() -> BaseConfig:
    # Loads the variables from the chosen file
    base = BaseConfig()
    
    if base.env_state == "prod":
        return ProdConfig()
    
    return DevConfig()