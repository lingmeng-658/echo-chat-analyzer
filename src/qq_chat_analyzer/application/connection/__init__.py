"""Connection lifecycle management for external chat sources."""

from __future__ import annotations

from .models import ConnectionSnapshot, ConnectionState
from .qq_connection_manager import QQConnectionManager

__all__ = [
    "ConnectionSnapshot",
    "ConnectionState",
    "QQConnectionManager",
]
