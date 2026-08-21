# -*- coding: utf-8 -*-
"""Central logging setup for the FastAPI workbench."""
import copy
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from colorama import just_fix_windows_console

from web.core.settings import LOG_DIR

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


class ConsoleFormatter(logging.Formatter):
    """Render log metadata with ANSI colors without writing those codes to files."""

    COLORS = {
        logging.DEBUG: "\033[90m",
        logging.INFO: "\033[36m",
        SUCCESS_LEVEL: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[1;31m",
    }
    RESET = "\033[0m"
    MUTED = "\033[90m"

    def __init__(self, use_color: bool | None = None) -> None:
        super().__init__(LOG_FORMAT, DATE_FORMAT)
        self.use_color = _should_use_color() if use_color is None else use_color

    def format(self, record: logging.LogRecord) -> str:
        if not self.use_color:
            return super().format(record)

        colored = copy.copy(record)
        color = self.COLORS.get(record.levelno, self.RESET)
        colored.levelname = f"{color}{record.levelname}{self.RESET}"
        colored.name = f"{self.MUTED}{record.name}{self.RESET}"
        return super().format(colored)


class ExpectedClientDisconnectFilter(logging.Filter):
    """Hide the expected Windows reset logged when browsers stop media streaming."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name not in {"uvicorn.error", "asyncio"}:
            return True

        exception = record.exc_info[1] if record.exc_info else None
        while exception is not None:
            if isinstance(exception, ConnectionResetError) and getattr(exception, "winerror", None) == 10054:
                return False
            exception = exception.__cause__ or exception.__context__
        return True


def _should_use_color() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False

    configured = os.environ.get("LOG_COLOR", "auto").lower()
    if configured in {"0", "false", "no", "off"}:
        return False
    if configured in {"1", "true", "yes", "on"}:
        return True
    return sys.platform == "win32" or bool(getattr(sys.stderr, "isatty", lambda: False)())


def log_request(
    logger: logging.Logger,
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    request_id: str,
) -> None:
    """Log completed HTTP requests with a level that reflects the response result."""
    message = "HTTP completed request_id=%s method=%s path=%s status=%s duration_ms=%.1f"
    args: tuple[Any, ...] = (request_id, method, path, status_code, duration_ms)
    if 200 <= status_code < 300:
        logger.log(SUCCESS_LEVEL, message, *args)
    elif status_code < 400:
        logger.info(message, *args)
    elif status_code < 500:
        logger.warning(message, *args)
    else:
        logger.error(message, *args)


def configure_logging(log_dir: Path = LOG_DIR, level: int = logging.INFO) -> None:
    """Configure console and rotating file logging once."""
    just_fix_windows_console()
    root = logging.getLogger()
    if getattr(root, "_video_pipeline_logging_configured", False):
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(ConsoleFormatter())

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    disconnect_filter = ExpectedClientDisconnectFilter()
    console.addFilter(disconnect_filter)
    file_handler.addFilter(disconnect_filter)

    root.addHandler(console)
    root.addHandler(file_handler)
    root._video_pipeline_logging_configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
