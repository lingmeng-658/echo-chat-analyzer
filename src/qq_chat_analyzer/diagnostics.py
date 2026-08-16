"""Shared privacy-first diagnostics for the Echo desktop application."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from .logging_config import (
    DESKTOP_DIAGNOSTIC_LOGGERS,
    SensitiveDataFilter,
    build_diagnostic_handler,
)


LOGGER_NAME = "qq_chat_analyzer.diagnostics"
LOG_FILENAME = "echo.log"


def runtime_root() -> Path:
    """Return the directory beside the executable, or the development root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2] / "Echo"


def log_path() -> Path:
    """Return the shared Echo log path."""
    return runtime_root() / "logs" / LOG_FILENAME


def configure_diagnostics() -> logging.Logger:
    """Configure one idempotent logger and share its handler with diagnostics."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = next(
        (
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename).resolve() == path.resolve()
        ),
        None,
    )
    if existing is None:
        logger.addHandler(build_diagnostic_handler(path))
    handlers = tuple(logger.handlers)
    for logger_name in DESKTOP_DIAGNOSTIC_LOGGERS:
        target = logging.getLogger(logger_name)
        target.setLevel(logging.INFO)
        for handler in handlers:
            if handler not in target.handlers:
                target.addHandler(handler)
    return logger


__all__ = [
    "LOGGER_NAME",
    "LOG_FILENAME",
    "SensitiveDataFilter",
    "configure_diagnostics",
    "log_path",
    "runtime_root",
]
