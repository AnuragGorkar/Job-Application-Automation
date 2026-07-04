from pathlib import Path

from app.core.logger import setup_logging


def test_setup_logging_creates_log_directory_and_handlers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    setup_logging()

    log_dir = tmp_path / "logs"
    assert log_dir.exists()
    assert (log_dir / "app.log").exists()

    import logging

    root_logger = logging.getLogger()
    assert any(isinstance(handler, logging.FileHandler) for handler in root_logger.handlers)
    assert any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers)
