"""Orchestrate a QCE service export into the existing import pipeline.

This module is a thin seam between two pieces that must not know about each
other: the QCE HTTP provider produces a local JSON file, and the existing
:class:`~qq_chat_analyzer.application.import_service.ImportService` turns local
files into :class:`~qq_chat_analyzer.message.ChatMessage` objects.

Deliberate boundaries:

* No HTTP lives here. The provider is injected and only has to satisfy
  :class:`QQExportProvider`, so tests can supply a stub.
* The adapter is untouched and stays unaware that a provider exists. It is
  reached indirectly through the normal ``ImportService`` file dispatch and,
  for time-range defaults, through ``load_qce_json`` without any adapter edits.
* ``parser.py`` and the analysis core are not involved.

The provider contract is intentionally narrow: given a group code and an
optional time window, hand back a path to a finished QCE JSON export.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from ..analysis.timestamps import to_epoch_seconds
from ..qq_chat_exporter_adapter import load_qce_json
from .chat_data_snapshot import (
    ChatDataSnapshotManager,
    ChatDataSource,
    SnapshotSaveError,
)
from .errors import ApplicationServiceError
from .import_outcome import ImportOutcome
from .import_request import ImportRequest
from .import_service import ImportService


QQ_PLATFORM = "qq"
QQ_PRIVATE_CHAT_TYPE = 1
QQ_GROUP_CHAT_TYPE = 2
_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_export_import")


class QQExportUnavailable(ApplicationServiceError):
    """Raised when the QCE service could not produce an export file."""

    code = "qq_export_unavailable"
    public_message = "无法获取 QQ 聊天记录导出文件。"


class QQExportFileMissing(ApplicationServiceError):
    """Raised when the export reports success but the file is not on disk."""

    code = "qq_export_file_missing"
    public_message = "QQ 聊天记录导出未生成文件，请稍后重试。"


@runtime_checkable
class QQExportProvider(Protocol):
    """Minimal surface this orchestrator needs from a QCE provider."""

    def list_groups(self) -> list[Any]:  # pragma: no cover - contract only
        """Return the groups that are available for export."""
        ...

    def list_friends(self) -> list[Any]:  # pragma: no cover - contract only
        """Return normal private conversations available for export."""
        ...

    def list_tasks(self) -> list[Any]:  # pragma: no cover - contract only
        """Return the current QCE export task list."""
        ...

    def export_group_json(
        self,
        group_code: str,
        start_time: Any = None,
        end_time: Any = None,
    ) -> Path:  # pragma: no cover - structural contract only
        ...


@dataclass(frozen=True, slots=True)
class QQExportImportRequest:
    """Describe one "export from QCE, then import" operation."""

    group_code: str
    start_time: Any = None
    end_time: Any = None
    chat_type: int = QQ_GROUP_CHAT_TYPE
    peer_uin: str | None = None
    session_name: str | None = None
    force_refresh: bool = False


@dataclass(frozen=True, slots=True)
class QQExportAcquisition:
    """One QQ export payload plus optional persisted snapshot identity."""

    payload_path: Path
    snapshot_id: str | None = None
    acquired_at: datetime | None = None
    reused_snapshot: bool = False


class QQExportImportService:
    """Export one QQ group through a provider, then import the result."""

    def __init__(
        self,
        provider: QQExportProvider | None = None,
        import_service: ImportService | None = None,
        *,
        provider_factory: Any = None,
        cache_directory: str | Path | None = None,
        snapshot_manager: ChatDataSnapshotManager | None = None,
    ) -> None:
        if provider is None and provider_factory is None:
            raise TypeError(
                "QQExportImportService needs a provider or provider_factory"
            )
        self._injected_provider = provider
        self._provider_factory = provider_factory
        self._import_service = import_service or ImportService()
        self._snapshot_manager = snapshot_manager or ChatDataSnapshotManager()
        # Kept only so existing constructor calls remain valid. Phase 3B does
        # not read, migrate, or delete the legacy metadata cache.
        del cache_directory

    def provider(self) -> QQExportProvider:
        """Return the provider used for exports.

        When a shared provider factory is injected, the instance comes from
        that factory, so session listing and export use the same configuration
        and provider as the connection status check.
        """
        if self._provider_factory is not None:
            return self._provider_factory.create()
        return self._injected_provider

    @property
    def _provider(self) -> QQExportProvider:
        return self.provider()

    def execute(self, request: QQExportImportRequest) -> ImportOutcome:
        acquisition = self.acquire_export(request)

        return self._import_service.execute(
            ImportRequest(
                input_path=acquisition.payload_path,
                platform=QQ_PLATFORM,
            )
        )

    def list_groups(self) -> list[Any]:
        """Delegate group listing to the injected provider.

        Thin pass-through so callers such as the CLI and a future GUI reach
        provider listings through this application service instead of
        constructing a provider themselves. Provider errors propagate
        unchanged; they already carry user-facing messages.
        """
        return self._provider.list_groups()

    def list_sessions(self) -> list[Any]:
        """Return exportable groups and normal QQ friend conversations."""
        return [
            *(self._provider.list_groups() or ()),
            *(self._provider.list_friends() or ()),
        ]

    def list_tasks(self) -> list[Any]:
        """Delegate QCE task listing to the injected provider.

        This is the application-layer entry point a future GUI can call
        without touching the provider directly. Provider errors propagate
        unchanged because they already carry user-facing messages.
        """
        return self._provider.list_tasks()

    def get_session_message_range(
        self,
        group_code: str,
        *,
        chat_type: int = QQ_GROUP_CHAT_TYPE,
        peer_uin: str | None = None,
        session_name: str | None = None,
    ) -> tuple[int, int] | None:
        """Return earliest and latest message timestamps for one QQ session.

        The range comes from the actual exported QCE JSON so QQ defaults are
        based on real messages instead of a fixed window. Non-text messages are
        included because they still carry a real message time.
        """
        export_path = self.export_only(
            QQExportImportRequest(
                group_code=group_code,
                chat_type=chat_type,
                peer_uin=peer_uin,
                session_name=session_name,
            )
        )
        payload = load_qce_json(export_path)
        if not isinstance(payload, Mapping):
            return None
        raw_messages = payload.get("messages")
        if not isinstance(raw_messages, list):
            return None
        epochs = [
            epoch
            for row in raw_messages
            if isinstance(row, Mapping)
            for epoch in (to_epoch_seconds(row.get("timestamp")),)
            if epoch is not None
        ]
        if not epochs:
            return None
        return min(epochs), max(epochs)

    def export_only(self, request: QQExportImportRequest) -> Path:
        """Export one QQ group and return the finished JSON file path.

        This is the first half of :meth:`execute`, exposed for callers that
        want the export file without immediately importing it. Provider
        errors propagate unchanged; only a missing or unusable return value
        becomes :class:`QQExportUnavailable`, and a path that is not present
        on disk becomes :class:`QQExportFileMissing`.
        """
        return self.acquire_export(request).payload_path

    def acquire_export(
        self,
        request: QQExportImportRequest,
    ) -> QQExportAcquisition:
        """Reuse a valid snapshot or export and persist a new raw payload."""
        session_type = _session_type(request)
        cacheable = _is_full_session_request(request)
        if cacheable and not request.force_refresh:
            validation = self._snapshot_manager.find_latest_available(
                source=ChatDataSource.QQ,
                session_id=str(request.group_code),
                session_type=session_type,
            )
            if (
                validation is not None
                and validation.snapshot is not None
                and validation.payload_path is not None
            ):
                return QQExportAcquisition(
                    payload_path=validation.payload_path,
                    snapshot_id=validation.snapshot.id,
                    acquired_at=validation.snapshot.acquired_at,
                    reused_snapshot=True,
                )

        export_path = self._export(request)
        if not export_path.exists():
            raise QQExportFileMissing()

        if not cacheable:
            return QQExportAcquisition(payload_path=export_path)
        metadata = _snapshot_metadata(export_path)
        if metadata is None:
            return QQExportAcquisition(payload_path=export_path)
        message_count, coverage_start, coverage_end = metadata
        try:
            snapshot = self._snapshot_manager.save_snapshot(
                export_path,
                source=ChatDataSource.QQ,
                session_id=str(request.group_code),
                session_name=request.session_name,
                session_type=session_type,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
                message_count=message_count,
                storage_format="qce_json",
            )
        except SnapshotSaveError:
            _LOGGER.warning(
                "QQ export succeeded but its chat data snapshot could not "
                "be saved.",
            )
            return QQExportAcquisition(payload_path=export_path)

        snapshot_payload = self._snapshot_manager.resolve_payload_path(
            snapshot.id
        )
        if snapshot_payload is None:
            _LOGGER.warning(
                "QQ chat data snapshot failed validation after save."
            )
            return QQExportAcquisition(payload_path=export_path)
        return QQExportAcquisition(
            payload_path=snapshot_payload,
            snapshot_id=snapshot.id,
            acquired_at=snapshot.acquired_at,
            reused_snapshot=False,
        )

    # ---------------------------------------------------------------- internals

    def _export(self, request: QQExportImportRequest) -> Path:
        """Run the provider export, normalising its failures.

        Provider-level errors are re-raised untouched: they already carry
        actionable, user-facing messages such as "service not running" or
        "export cancelled". Only a missing or unusable return value is
        translated here.
        """
        export_chat = getattr(self._provider, "export_chat_json", None)
        if callable(export_chat):
            result = export_chat(
                request.group_code,
                chat_type=request.chat_type,
                peer_uin=request.peer_uin,
                session_name=request.session_name,
                start_time=request.start_time,
                end_time=request.end_time,
            )
        elif request.chat_type == QQ_GROUP_CHAT_TYPE:
            result = self._provider.export_group_json(
                request.group_code,
                start_time=request.start_time,
                end_time=request.end_time,
            )
        else:
            raise QQExportUnavailable()
        if result is None:
            raise QQExportUnavailable()
        if isinstance(result, Path):
            return result
        if isinstance(result, str) and result.strip():
            return Path(result)
        raise QQExportUnavailable()

def _session_type(request: QQExportImportRequest) -> str:
    return "private" if request.chat_type == QQ_PRIVATE_CHAT_TYPE else "group"


def _is_full_session_request(request: QQExportImportRequest) -> bool:
    return request.start_time is None and request.end_time is None


def _snapshot_metadata(
    export_path: Path,
) -> tuple[int, datetime | None, datetime | None] | None:
    payload = load_qce_json(export_path)
    if not isinstance(payload, Mapping):
        return None
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        return None
    epochs = [
        epoch
        for row in raw_messages
        if isinstance(row, Mapping)
        for epoch in (to_epoch_seconds(row.get("timestamp")),)
        if epoch is not None
    ]
    if not epochs:
        return len(raw_messages), None, None
    return (
        len(raw_messages),
        datetime.fromtimestamp(min(epochs), timezone.utc),
        datetime.fromtimestamp(max(epochs), timezone.utc),
    )
