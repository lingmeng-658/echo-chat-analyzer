"""Compatibility exports; implementation lives in application.wechat."""

from .wechat.wechat_connection_service import (
    WeChatConnectionService,
    WeChatConnectionStatus,
)

__all__ = ["WeChatConnectionService", "WeChatConnectionStatus"]
