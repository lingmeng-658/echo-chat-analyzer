"""External data-source providers.

Providers only talk to third-party tools over their public interfaces. They do
not parse chat payloads themselves; conversion to :class:`ChatMessage` stays in
the matching adapter module.
"""

from __future__ import annotations

from .qq_chat_exporter_provider import (
    DEFAULT_BASE_URL,
    ExportGroup,
    ExportTask,
    ExportTaskCancelled,
    ExportTaskFailed,
    ExportTaskLimitReached,
    ExportTimeout,
    QQChatExporterError,
    QQChatExporterProvider,
    RequestFailed,
    ServiceHealth,
    ServiceUnavailable,
    TaskNotFound,
    TokenUnavailable,
    read_token,
    resolve_security_candidates,
    resolve_security_path,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "ExportGroup",
    "ExportTask",
    "ExportTaskCancelled",
    "ExportTaskFailed",
    "ExportTaskLimitReached",
    "ExportTimeout",
    "QQChatExporterError",
    "QQChatExporterProvider",
    "RequestFailed",
    "ServiceHealth",
    "ServiceUnavailable",
    "TaskNotFound",
    "TokenUnavailable",
    "read_token",
    "resolve_security_candidates",
    "resolve_security_path",
]
