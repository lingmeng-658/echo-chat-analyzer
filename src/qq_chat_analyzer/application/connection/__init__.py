"""Compatibility exports for connection models and QQ lifecycle modules."""

from __future__ import annotations

from ..connection_models import ConnectionSnapshot, ConnectionState
from ..qq.qq_auth_bridge import QQAuthBridge
from ..qq.qq_connection_manager import QQConnectionManager

__all__ = [
    "ConnectionSnapshot",
    "ConnectionState",
    "QQAuthBridge",
    "QQConnectionManager",
]
