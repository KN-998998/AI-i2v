# -*- coding: utf-8 -*-
"""Central logging setup for the FastAPI workbench."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from web.core.settings import LOG_DIR

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(log_dir: Path = LOG_DIR, level: int = logging.INFO) -> None:
    """Configure console and rotating file logging once."""
    root = logging.getLogger()
    if getattr(root, "_video_pipeline_logging_configured", False):
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root.addHandler(console)
    root.addHandler(file_handler)
    root._video_pipeline_logging_configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)