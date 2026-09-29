"""Anonymous, source-neutral timing and message-order diagnostics."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter

from .analysis.timestamps import to_epoch_seconds
from .message import ChatMessage


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.analysis_diagnostics")


@contextmanager
def timed_stage(stage: str) -> Iterator[None]:
    """Log one fixed pipeline stage, including when the stage raises."""
    started_at = perf_counter()
    try:
        yield
    finally:
        _LOGGER.info(
            "[analysis-timing] stage=%s elapsed_ms=%d",
            stage,
            max(0, round((perf_counter() - started_at) * 1000)),
        )


@dataclass(slots=True)
class OrderingHealth:
    """Collect order health during an existing message traversal."""

    boundary: str
    message_count: int = 0
    valid_timestamp_count: int = 0
    invalid_timestamp_count: int = 0
    adjacent_inversion_count: int = 0
    max_backward_seconds: int = 0
    _previous: int | None = None

    def observe(self, message: ChatMessage) -> None:
        self.message_count += 1
        try:
            timestamp = to_epoch_seconds(message.timestamp)
        except (OverflowError, TypeError, ValueError):
            timestamp = None
        if timestamp is None:
            self.invalid_timestamp_count += 1
            self._previous = None
            return
        self.valid_timestamp_count += 1
        if self._previous is not None and timestamp < self._previous:
            self.adjacent_inversion_count += 1
            self.max_backward_seconds = max(
                self.max_backward_seconds, self._previous - timestamp
            )
        self._previous = timestamp

    def log(self) -> None:
        _LOGGER.info(
            "[analysis-ordering] boundary=%s message_count=%d "
            "valid_timestamp_count=%d invalid_timestamp_count=%d "
            "adjacent_inversion_count=%d max_backward_seconds=%d",
            self.boundary,
            self.message_count,
            self.valid_timestamp_count,
            self.invalid_timestamp_count,
            self.adjacent_inversion_count,
            self.max_backward_seconds,
        )
