"""Source-agnostic connection lifecycle vocabulary.

The application layer owns one answer to "is this chat source usable right
now". GUI code renders these values; it never re-derives them from runtime
processes, health endpoints, or tokens.

The model is deliberately small: one state enum and one immutable snapshot,
with no source-specific fields. QQ is the only source wired to it today,
and WeChat can reuse the same vocabulary when its flow moves here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionState(str, Enum):
    """Lifecycle state of one chat source connection."""

    DISCONNECTED = "disconnected"
    INITIALIZING = "initializing"
    STARTING = "starting"
    WAITING_AUTH = "waiting_auth"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ConnectionSnapshot:
    """User-facing snapshot of one source's connection lifecycle.

    ``state`` is the only field a caller should branch on. ``message`` and
    ``action_hint`` say what happened and what to do next, already worded for
    a user. ``code`` is an optional stable machine-readable reason for an
    error state; ``version`` is display-only and may be absent.
    """

    state: ConnectionState
    source: str
    message: str
    action_hint: str = ""
    code: str | None = None
    version: str | None = None

    @property
    def connected(self) -> bool:
        """Return whether the source can be used for analysis right now."""
        return self.state is ConnectionState.CONNECTED

    @property
    def in_progress(self) -> bool:
        """Return whether a connect attempt is still running."""
        return self.state in (
            ConnectionState.INITIALIZING,
            ConnectionState.STARTING,
        )


__all__ = ["ConnectionSnapshot", "ConnectionState"]
