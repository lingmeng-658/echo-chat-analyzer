"""Application logging configuration shared by entry points."""

from __future__ import annotations

import logging
from collections.abc import Iterable


DESKTOP_DIAGNOSTIC_LOGGERS = (
    "qq_chat_analyzer.providers.wechat_database_provider",
)


def attach_desktop_diagnostic_handlers(
    handlers: Iterable[logging.Handler],
) -> None:
    """Attach desktop file handlers to diagnostic loggers idempotently."""
    desktop_handlers = tuple(handlers)
    for logger_name in DESKTOP_DIAGNOSTIC_LOGGERS:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        for handler in desktop_handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)
