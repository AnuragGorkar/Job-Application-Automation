import logging
import os
from logging.handlers import RotatingFileHandler

from app.core.config import settings


def _should_overwrite_logs() -> bool:
    env_value = os.getenv("LOG_OVERWRITE", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    if env_value in {"0", "false", "no", "off"}:
        return False

    return settings.log_overwrite or settings.env.lower() in {"dev", "development", "local"}


def setup_logging() -> None:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(log_format)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        mode="w" if _should_overwrite_logs() else "a",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if root_logger.handlers:
        for existing_handler in root_logger.handlers[:]:
            root_logger.removeHandler(existing_handler)
            existing_handler.close()

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
