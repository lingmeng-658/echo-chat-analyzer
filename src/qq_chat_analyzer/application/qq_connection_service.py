"""Compatibility exports; implementation lives in application.qq."""

from .qq.qq_connection_service import QQConnectionService, QQConnectionStatus

__all__ = ["QQConnectionService", "QQConnectionStatus"]
