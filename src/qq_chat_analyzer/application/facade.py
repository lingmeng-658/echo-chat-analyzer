"""One stable application entry point for user-facing callers.

This module is the seam a future GUI talks to. It exists so that a window,
a widget, or any other presentation-side caller never has to know that
providers, import services, export files, or analyzer internals exist.

Deliberate boundaries:

* No provider is constructed here. Every collaborator is injected, so tests
  can supply stubs and the desktop wiring stays in one place.
* No analysis happens here. ``AnalysisApplicationService`` owns that, and the
  presentation builder owns formatting. This layer only decides *which*
  collaborator runs and in *what* order.
* No statistics are recomputed. Numbers travel from the analysis reports into
  the dashboard view untouched.
* Intermediate export files are an implementation detail. Generated Echo HTML
  is the exception: its exact local path is retained for the desktop caller.

Everything that escapes this layer is either a plain view model or a
:class:`FacadeError` carrying a stable ``code`` and a user-safe message.
"""

from __future__ import annotations

import logging
import shutil
from tempfile import TemporaryDirectory
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol, runtime_checkable
from uuid import uuid4

from ..resources import resources_dir, user_data_dir
from ..analysis.timestamps import to_epoch_seconds
from ..presentation import DashboardView, build_dashboard_view
from .dto import AnalysisRequestDTO, AnalysisResultDTO
from .errors import ApplicationServiceError
from .connection import ConnectionSnapshot, QQConnectionManager
from .qq_connection_service import (
    QQConnectionService,
    QQConnectionStatus,
)
from .qq_environment_config import QQEnvironmentConfig
from .qq_export_import_service import QQExportImportRequest
from .qq_setup_service import QQSetupStatus
from .report_history import InputIdentitySummary
from .chat_data_snapshot import ChatDataSnapshotManager
from .wechat_connection_service import WeChatConnectionStatus
from .wechat_environment_config import WeChatEnvironmentConfig
from .wechat_export_import_service import WeChatExportImportRequest
from .wechat_setup_service import WeChatSetupStatus
from .scope_filter import AnalysisScope, AnalysisScopeMode, resolve_scope


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.facade")


class _RetainedReportDirectory:
    """Own one report directory while preserving its inherited ACL."""

    def __init__(self, parent: Path) -> None:
        while True:
            directory = parent / f"chat-analyzer-output-{uuid4().hex[:8]}"
            try:
                directory.mkdir()
            except FileExistsError:
                continue
            self.name = str(directory)
            break

    def cleanup(self) -> None:
        shutil.rmtree(self.name, ignore_errors=True)


def _report_progress(
    progress: Callable[[str], None] | None,
    message: str,
) -> None:
    """Publish a facade-owned analysis stage when a caller is listening."""
    if progress is not None:
        progress(message)


DEFAULT_TOP = 50
DEFAULT_PROFILE = "default"

_PROFILE_STOPWORD_FILES = {
    "default": "stopwords.txt",
    "topic": "stopwords_topic.txt",
    "culture": "stopwords_culture.txt",
}

class ChatSource(str, Enum):
    """Every chat origin a caller may choose from."""

    QQ = "qq"
    WECHAT = "wechat"
    LOCAL_FILE = "local_file"


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """One selectable conversation, normalised across every source."""

    source: ChatSource
    session_id: str
    display_name: str
    session_type: str = "other"
    message_count: int | None = None
    message_available: bool = True
    unavailable_reason: str | None = None
    last_message_time: int | None = None


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """One data source a caller may pick, plus whether it is usable."""

    source: ChatSource
    display_name: str
    available: bool
    description: str = ""


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Everything a caller may tune for one analysis run.

    ``scope_mode`` selects the analysis window. ``start_time`` and
    ``end_time`` are used for a custom range. Explicit legacy bounds are also
    treated as custom so existing callers retain their behavior.
    """

    start_time: Any = None
    end_time: Any = None
    scope_mode: AnalysisScopeMode = AnalysisScopeMode.ALL
    force_refresh: bool = False
    top: int = DEFAULT_TOP
    profile: str = DEFAULT_PROFILE
    output_directory: Path | None = None
    font_path: str | None = None

    def with_output_directory(self, directory: Path) -> "AnalysisConfig":
        """Return a copy that writes artifacts into ``directory``."""
        return replace(self, output_directory=directory)


class FacadeError(Exception):
    """The single error type a caller outside this layer has to handle."""

    def __init__(
        self,
        code: str,
        public_message: str,
        *,
        source: ChatSource | None = None,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message
        self.source = source


class UnknownChatSource(FacadeError):
    """Raised when a caller asks for a source this layer cannot serve."""

    def __init__(self, source: Any) -> None:
        super().__init__(
            code="unknown_source",
            public_message=(
                "\u4e0d\u652f\u6301\u7684\u6570\u636e\u6765\u6e90"
                f"\uff1a{source}\u3002"
            ),
        )


class SourceUnavailable(FacadeError):
    """Raised when a source was requested but no service was wired for it."""

    def __init__(self, source: ChatSource) -> None:
        super().__init__(
            code="source_unavailable",
            public_message=_SOURCE_UNAVAILABLE_MESSAGES[source],
            source=source,
        )


_SOURCE_UNAVAILABLE_MESSAGES = {
    ChatSource.QQ: (
        "QQ \u6570\u636e\u6e90\u6682\u4e0d\u53ef\u7528\u3002"
    ),
    ChatSource.WECHAT: (
        "\u5fae\u4fe1\u6570\u636e\u6e90\u5c1a\u672a\u914d\u7f6e\u3002"
    ),
    ChatSource.LOCAL_FILE: (
        "\u672c\u5730\u6587\u4ef6\u5206\u6790\u5c1a\u672a\u914d\u7f6e\u3002"
    ),
}

_SOURCE_DISPLAY_NAMES = {
    ChatSource.QQ: "QQ",
    ChatSource.WECHAT: "\u5fae\u4fe1",
    ChatSource.LOCAL_FILE: "\u672c\u5730\u6587\u4ef6",
}


@runtime_checkable
class SessionListingService(Protocol):
    """Shared shape of the two export services used for listing."""

    def list_sessions(self) -> list[Any]:  # pragma: no cover - contract only
        ...


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    """What one finished analysis hands back to a caller.

    ``view`` is what a GUI renders. ``result`` stays available for callers
    that need the privacy-safe DTO, and ``session`` records which
    conversation produced the view.
    """

    view: DashboardView
    result: AnalysisResultDTO
    source: ChatSource
    session: SessionInfo | None = None
    artifact_directory: Path | None = field(default=None, repr=False)
    report_path: Path | None = field(default=None, repr=False)
    history_saved: bool | None = None
    history_record_id: str | None = None
    snapshot_id: str | None = None
    data_acquired_at: datetime | None = None
    snapshot_reused: bool = False


@dataclass(frozen=True, slots=True)
class _SessionExport:
    """Internal export path plus optional snapshot acquisition metadata."""

    payload_path: Path
    snapshot_id: str | None = None
    acquired_at: datetime | None = None
    reused_snapshot: bool = False


class ChatAnalyzerFacade:
    """Coordinate sources, analysis, and presentation behind one surface."""

    def __init__(
        self,
        *,
        qq_service: Any = None,
        qq_connection_service: Any = None,
        qq_setup_service: Any = None,
        qq_connection_manager: Any = None,
        qq_auth_bridge: Any = None,
        qq_process_registry: Any = None,
        wechat_service: Any = None,
        wechat_connection_service: Any = None,
        wechat_setup_service: Any = None,
        source_builders: (
            dict[ChatSource, Callable[[], Any]] | None
        ) = None,
        analysis_service: Any = None,
        presentation_builder: Any = None,
        report_history_manager: Any = None,
        snapshot_manager: Any = None,
        stopwords_directory: Path | None = None,
    ) -> None:
        self._services: dict[ChatSource, Any] = {
            ChatSource.QQ: qq_service,
            ChatSource.WECHAT: wechat_service,
        }
        self._qq_connection_service = qq_connection_service
        self._qq_setup_service = qq_setup_service
        self._qq_connection_manager = qq_connection_manager
        self._qq_auth_bridge = qq_auth_bridge
        self._qq_process_registry = qq_process_registry
        self._wechat_connection_service_value = wechat_connection_service
        self._wechat_setup_service_value = wechat_setup_service
        self._source_builders = dict(source_builders or {})
        self._built_sources: dict[ChatSource, Any] = {}
        self._analysis_service = analysis_service
        self._presentation_builder = presentation_builder
        self._report_history_manager = report_history_manager
        self._snapshot_manager = snapshot_manager or ChatDataSnapshotManager()
        self._stopwords_directory = stopwords_directory or resources_dir()
        self._retained_output_directory: _RetainedReportDirectory | None = None

    @property
    def _wechat_connection_service(self) -> Any:
        if self._wechat_connection_service_value is None:
            bundle = self._source_bundle(ChatSource.WECHAT)
            self._wechat_connection_service_value = getattr(
                bundle,
                "connection",
                None,
            )
        return self._wechat_connection_service_value

    @property
    def _wechat_setup_service(self) -> Any:
        if self._wechat_setup_service_value is None:
            bundle = self._source_bundle(ChatSource.WECHAT)
            self._wechat_setup_service_value = getattr(bundle, "setup", None)
        return self._wechat_setup_service_value

    # ------------------------------------------------------------- discovery

    def list_sources(self) -> tuple[SourceInfo, ...]:
        """Describe every source, flagging which ones are wired up."""
        return tuple(
            SourceInfo(
                source=source,
                display_name=_SOURCE_DISPLAY_NAMES[source],
                available=self._is_available(source),
                description=(
                    ""
                    if self._is_available(source)
                    else _SOURCE_UNAVAILABLE_MESSAGES[source]
                ),
            )
            for source in ChatSource
        )

    def list_sessions(self, source: ChatSource) -> list[SessionInfo]:
        """Return the conversations one source offers, normalised."""
        chat_source = _coerce_source(source)
        if chat_source is ChatSource.LOCAL_FILE:
            return []

        service = self._require_service(chat_source)
        with _translated_errors(chat_source):
            if chat_source is ChatSource.QQ:
                raw_sessions = service.list_sessions()
            else:
                raw_sessions = service.list_sessions()

        return [
            _to_session_info(chat_source, raw_session)
            for raw_session in raw_sessions or ()
        ]

    def get_qq_export_tasks(self) -> list[Any]:
        """Return the current QCE export task list through the QQ service."""
        service = self._require_service(ChatSource.QQ)
        with _translated_errors(ChatSource.QQ):
            return service.list_tasks() or []

    def get_connection_status(
        self,
        source: ChatSource,
    ) -> QQConnectionStatus | WeChatConnectionStatus:
        """Return the user-facing connection state for one source."""
        chat_source = _coerce_source(source)
        service = self._require_connection_service(chat_source)
        with _translated_errors(chat_source):
            return service.check_status()

    def get_qq_setup_status(self) -> QQSetupStatus:
        """Report whether the QQ environment config is usable."""
        service = self._require_qq_setup_service()
        with _translated_errors(ChatSource.QQ):
            return service.check_setup()

    def get_qq_environment_config(self) -> QQEnvironmentConfig:
        """Return the effective QQ environment config for prefill.

        The GUI uses this only to prefill the setup dialog, never to read or
        write the configuration itself.
        """
        service = self._require_qq_setup_service()
        with _translated_errors(ChatSource.QQ):
            return service.get_environment_config()

    def setup_qq_environment(self, config: QQEnvironmentConfig) -> Any:
        """Save a QQ environment config and re-check the connection."""
        service = self._require_qq_setup_service()
        with _translated_errors(ChatSource.QQ):
            return service.save_environment(config)

    def get_qq_runtime_status(self) -> Any:
        """Return the current QQ runtime lifecycle status."""
        service = self._require_qq_setup_service()
        with _translated_errors(ChatSource.QQ):
            return service.get_runtime_status()

    def start_qq_runtime(self) -> Any:
        """Start the configured QQ runtime and wait until ready."""
        service = self._require_qq_setup_service()
        with _translated_errors(ChatSource.QQ):
            return service.start_runtime()

    def get_qq_connection_snapshot(self) -> ConnectionSnapshot:
        """Report the QQ connection lifecycle without starting anything.

        This is what the GUI shows when a user selects QQ. The manager never
        raises, so an unreachable service becomes a snapshot rather than an
        error the page has to interpret.
        """
        return self._require_qq_connection_manager().get_snapshot()

    def connect_qq(self) -> ConnectionSnapshot:
        """Connect QQ through the single authorization runtime path.

        Redirected to :meth:`start_qq_auth_flow` so the launcher/NapCat owns
        the qce-server lifecycle; the connection manager must not pre-start a
        standalone qce-server that would collide with the NapCat plugin.
        """
        return self.start_qq_auth_flow()

    def start_qq_auth_flow(
        self,
        progress: Callable[[str], None] | None = None,
    ) -> ConnectionSnapshot:
        """Start QQ authorization and return the resulting lifecycle state.

        The GUI calls this instead of a raw connect: the auth bridge starts
        the runtime's own login flow and the caller keeps polling
        :meth:`get_qq_connection_snapshot` until it reports ``CONNECTED``.
        """
        return self._require_qq_auth_bridge().start_auth_flow(progress=progress)

    def is_qq_qrcode_ready(self) -> bool:
        """Return whether the QQ login QR belongs to the current session."""
        return self._require_qq_auth_bridge().is_qrcode_ready()

    def shutdown_qq_runtime(self) -> None:
        """Stop only QQ processes LCA started.

        This is the application exit hook: the registry records the QCE and
        NapCat PIDs LCA created, so a user's own QQ client is never touched.
        Cleanup is best-effort and never raises.
        """
        registry = self._require_qq_process_registry()
        try:
            registry.terminate_all()
        except Exception:
            pass

    def disconnect_qq(self) -> ConnectionSnapshot:
        """Log out the current QQ account and stop LCA-owned runtime sessions.

        The runtime files and stored QQ configuration are preserved; only the
        active login session is stopped so a different account can scan a
        fresh QR code.
        """
        return self._require_qq_auth_bridge().disconnect()

    def disconnect_wechat(self) -> WeChatConnectionStatus | None:
        """Log out the current WeChat account without deleting local data.

        The database key is released from the stored environment and the
        provider cache is dropped; the data root and database files stay
        untouched.
        """
        service = self._require_setup_service()
        with _translated_errors(ChatSource.WECHAT):
            return service.disconnect()

    def get_wechat_setup_status(self) -> WeChatSetupStatus:
        """Report whether the WeChat environment config is usable."""
        service = self._require_setup_service()
        with _translated_errors(ChatSource.WECHAT):
            return service.check_setup()

    def detect_wechat_data_root(self) -> Path | None:
        """Best-effort detect the local WeChat data directory.

        The GUI uses this to prefill the setup dialog and to start the
        one-click connect flow. The detected directory is handed back as a
        config value; the GUI never probes the filesystem itself.
        """
        service = self._require_setup_service()
        with _translated_errors(ChatSource.WECHAT):
            return service.detect_wechat_data_root()

    def detect_wechat_data_roots(self) -> list[Path]:
        """Return every valid WeChat data directory detected locally.

        When several accounts or storage locations exist, the caller shows
        the list and lets the user choose; the application layer never picks
        one automatically.
        """
        service = self._require_setup_service()
        with _translated_errors(ChatSource.WECHAT):
            return service.detect_wechat_data_roots()

    def setup_wechat_environment(
        self,
        config: WeChatEnvironmentConfig,
    ) -> WeChatConnectionStatus | None:
        """Save a WeChat environment config and re-check the connection.

        The GUI hands the collected settings here instead of writing the
        config file itself, so persistence and provider refresh stay in
        the application layer.
        """
        service = self._require_setup_service()
        with _translated_errors(ChatSource.WECHAT):
            return service.save_environment(config)

    def acquire_wechat_db_key(
        self,
        progress: Callable[[str], None] | None = None,
    ) -> str | None:
        """Acquire and persist the WeChat database key for the connect flow.

        Saving the data root deliberately no longer does this, because the
        key can only be captured while WeChat is at a login moment. The
        connect flow calls this second step explicitly. ``progress`` is
        relayed to the key acquisition so long waits can surface status.
        """
        service = self._require_setup_service()
        _LOGGER.info(
            "[wechat facade] acquire_wechat_db_key progress=%s",
            progress is not None,
        )
        with _translated_errors(ChatSource.WECHAT):
            return service.acquire_db_key(progress=progress)

    def get_session_message_range(
        self,
        source: ChatSource,
        session_id: str,
    ) -> tuple[int, int] | None:
        """Return earliest and latest message timestamps for one session."""
        chat_source = _coerce_source(source)
        if chat_source is ChatSource.LOCAL_FILE:
            return None
        service = self._require_service(chat_source)
        try:
            if chat_source is ChatSource.QQ:
                range_method = getattr(service, "get_session_message_range", None)
                if range_method is None:
                    return None
                raw_session = next(
                    (
                        candidate for candidate in (service.list_sessions() or ())
                        if getattr(candidate, "session_id", None) == session_id
                        or getattr(candidate, "group_code", None) == session_id
                    ),
                    None,
                )
                if _first_string(raw_session, "session_type") == "private":
                    return range_method(
                        session_id,
                        chat_type=1,
                        peer_uin=_first_string(raw_session, "peer_uin") or None,
                        session_name=_first_string(
                            raw_session,
                            "display_name",
                        ) or None,
                    )
                return range_method(session_id)
            provider_factory = getattr(service, "provider", None)
            if provider_factory is None:
                return None
            rows = provider_factory().read_session_rows(session_id)
        except Exception:
            return None
        epochs = [
            value
            for row in rows
            if isinstance(row, Mapping)
            for value in (to_epoch_seconds(row.get("create_time")),)
            if value is not None
        ]
        if not epochs:
            return None
        return min(epochs), max(epochs)

    # ------------------------------------------------------- report history

    def list_analysis_history(self) -> tuple[Any, ...]:
        """Return metadata-only analysis history through the app boundary."""
        if self._report_history_manager is None:
            return ()
        try:
            return tuple(self._report_history_manager.list_records())
        except Exception:
            _LOGGER.exception("Analysis history could not be read.")
            return ()

    def get_analysis_history(self, analysis_id: str) -> Any | None:
        """Return one metadata-only history record by ID."""
        if self._report_history_manager is None:
            return None
        try:
            return self._report_history_manager.get_record(analysis_id)
        except Exception:
            _LOGGER.exception("Analysis history record could not be read.")
            return None

    def clear_analysis_history(self) -> None:
        """Delete every saved analysis history record."""
        if self._report_history_manager is None:
            return
        try:
            self._report_history_manager.clear()
        except Exception as exc:
            raise FacadeError(
                code="history_clear_failed",
                public_message="无法清空 Echo 历史记录，请稍后重试。",
            ) from exc

    # ------------------------------------------------------------- snapshots

    def list_snapshots(
        self,
        source: ChatSource | None = None,
        session_id: str | None = None,
    ) -> tuple[Any, ...]:
        """Return snapshot metadata through the application boundary."""
        try:
            return tuple(
                self._snapshot_manager.list_snapshots(
                    source=source,
                    session_id=session_id,
                )
            )
        except Exception as exc:
            raise FacadeError(
                code="snapshot_list_failed",
                public_message="\u5feb\u7167\u5217\u8868\u8bfb\u53d6\u5931\u8d25\u3002",
            ) from exc

    def validate_snapshot(self, snapshot_id: str) -> Any:
        """Validate one snapshot manifest and payload."""
        try:
            return self._snapshot_manager.validate_snapshot(snapshot_id)
        except Exception as exc:
            raise FacadeError(
                code="snapshot_validation_failed",
                public_message="\u5feb\u7167\u6821\u9a8c\u5931\u8d25\u3002",
            ) from exc

    def remove_snapshot(self, snapshot_id: str) -> Any | None:
        """Remove one snapshot payload and return its metadata.

        Returns ``None`` when no snapshot with that id exists, so a caller
        can distinguish success from a clear missing result.
        """
        try:
            validation = self._snapshot_manager.remove_payload(snapshot_id)
        except Exception as exc:
            raise FacadeError(
                code="snapshot_remove_failed",
                public_message="\u5feb\u7167\u5220\u9664\u5931\u8d25\u3002",
            ) from exc
        return getattr(validation, "snapshot", None)

    def get_snapshot_storage_usage(self) -> int:
        """Return total bytes of currently available snapshot payloads."""
        try:
            total = 0
            for snapshot in self._snapshot_manager.list_snapshots():
                validation = self._snapshot_manager.validate_snapshot(
                    getattr(snapshot, "id", "")
                )
                if getattr(validation, "available", False):
                    total += int(
                        getattr(
                            getattr(validation, "snapshot", None),
                            "data_size_bytes",
                            0,
                        )
                    )
            return total
        except Exception as exc:
            raise FacadeError(
                code="snapshot_storage_usage_failed",
                public_message=(
                    "\u5feb\u7167\u5b58\u50a8\u5360\u7528\u7edf\u8ba1\u5931\u8d25\u3002"
                ),
            ) from exc

    # -------------------------------------------------------------- analysis

    def analyze_file(
        self,
        path: str | Path,
        config: AnalysisConfig | None = None,
        progress: Callable[[str], None] | None = None,
        *,
        speaker_names: Mapping[str, str] | None = None,
        viewer_speaker_key: str | None = None,
    ) -> AnalysisOutcome:
        """Analyze one already-exported local file or directory."""
        resolved_config = config or AnalysisConfig()
        resolved_scope = self._resolve_scope(
            resolved_config,
            ChatSource.LOCAL_FILE,
        )
        _report_progress(progress, "正在准备分析...")
        input_path = Path(path)
        _report_progress(progress, "正在读取聊天记录...")

        return self._analyze_path(
            input_path,
            resolved_config,
            source=ChatSource.LOCAL_FILE,
            session=None,
            scope=resolved_scope,
            speaker_names=speaker_names,
            conversation_kind="unknown",
            viewer_speaker_key=viewer_speaker_key,
            progress=progress,
        )

    def analyze_session(
        self,
        source: ChatSource,
        session_id: str,
        config: AnalysisConfig | None = None,
        progress: Callable[[str], None] | None = None,
        *,
        speaker_names: Mapping[str, str] | None = None,
        viewer_speaker_key: str | None = None,
    ) -> AnalysisOutcome:
        """Export one conversation, analyze it, and return a view.

        The export file is a temporary implementation detail: it is written to
        a scratch directory, consumed by the analysis service, and discarded
        before this method returns.
        """
        chat_source = _coerce_source(source)
        if chat_source is ChatSource.LOCAL_FILE:
            raise FacadeError(
                code="session_not_supported",
                public_message=(
                    "\u672c\u5730\u6587\u4ef6\u6ca1\u6709\u4f1a\u8bdd"
                    "\u5217\u8868\uff0c\u8bf7\u76f4\u63a5\u5206\u6790"
                    "\u6587\u4ef6\u3002"
                ),
                source=chat_source,
            )

        resolved_config = config or AnalysisConfig()
        resolved_scope = self._resolve_scope(resolved_config, chat_source)
        _report_progress(progress, "正在准备分析...")
        _report_progress(progress, "正在读取聊天记录...")
        service = self._require_service(chat_source)
        if chat_source in (ChatSource.QQ, ChatSource.WECHAT):
            raw_session = next(
                (
                    candidate for candidate in (service.list_sessions() or ())
                    if getattr(candidate, "session_id", None) == session_id
                    or getattr(candidate, "group_code", None) == session_id
                ),
                None,
            )
            session = (
                _to_session_info(chat_source, raw_session)
                if raw_session is not None
                else SessionInfo(
                    source=chat_source,
                    session_id=session_id,
                    display_name=session_id,
                )
            )
            conversation_names = {session_id: session.display_name}
            conversation_kind = (
                session.session_type
                if session.session_type in ("private", "group")
                else "unknown"
            )
        else:
            session = SessionInfo(
                source=chat_source,
                session_id=session_id,
                display_name=session_id,
            )
            conversation_names = None
            conversation_kind = "unknown"

        with TemporaryDirectory(prefix="chat-analyzer-export-") as scratch:
            scratch_directory = Path(scratch)
            with _translated_errors(chat_source):
                session_export = self._export_session(
                    chat_source,
                    service,
                    session_id,
                    resolved_config,
                    scratch_directory,
                    raw_session=raw_session if chat_source is ChatSource.QQ else None,
                )

            return self._analyze_path(
                session_export.payload_path,
                resolved_config,
                source=chat_source,
                session=session,
                scope=resolved_scope,
                speaker_names=speaker_names,
                conversation_names=conversation_names,
                conversation_kind=conversation_kind,
                viewer_speaker_key=viewer_speaker_key,
                snapshot_id=session_export.snapshot_id,
                data_acquired_at=session_export.acquired_at,
                snapshot_reused=session_export.reused_snapshot,
                progress=progress,
            )

    # ------------------------------------------------------------- internals

    def _analyze_path(
        self,
        input_path: Path,
        config: AnalysisConfig,
        *,
        source: ChatSource,
        session: SessionInfo | None,
        scope: AnalysisScope,
        speaker_names: Mapping[str, str] | None = None,
        conversation_names: Mapping[str, str] | None = None,
        conversation_kind: str = "unknown",
        viewer_speaker_key: str | None = None,
        snapshot_id: str | None = None,
        data_acquired_at: datetime | None = None,
        snapshot_reused: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> AnalysisOutcome:
        """Run analysis then presentation for one local path."""
        analysis_service = self._require_analysis_service()

        output_directory, temporary_output = _create_output_directory(config)
        try:
            request = AnalysisRequestDTO(
                input_path=input_path,
                output_directory=output_directory,
                stopwords_path=self._stopwords_path(config.profile),
                font_path=config.font_path,
                top=config.top,
                scope=scope,
                speaker_names=speaker_names or {},
                conversation_names=conversation_names or {},
                conversation_kind=conversation_kind,
                viewer_speaker_key=viewer_speaker_key,
            )
            with _translated_errors(source):
                _report_progress(progress, "正在处理消息...")
                _report_progress(progress, "正在分析聊天内容...")
                result = analysis_service.execute(request)

            _report_progress(progress, "正在生成报告...")
            view = self._build_view(result)
            report_generated_at = datetime.now(timezone.utc)
        except Exception:
            if temporary_output is not None:
                temporary_output.cleanup()
            raise

        report_path = _generated_echo_report_path(result, output_directory)
        if temporary_output is not None and report_path is None:
            temporary_output.cleanup()
            temporary_output = None
        self._replace_retained_output(temporary_output)

        history_saved: bool | None = None
        history_record_id: str | None = None
        if self._report_history_manager is not None:
            try:
                diagnostic_counts = getattr(result, "diagnostic_counts", None)
                history_record = self._report_history_manager.save_analysis(
                    source=source.value,
                    session_name=(
                        session.display_name if session is not None else None
                    ),
                    session_id=(
                        session.session_id if session is not None else None
                    ),
                    message_count=result.processed_message_count,
                    analysis_scope=scope.mode.value,
                    scope_start=scope.start_date,
                    scope_end=scope.end_date,
                    report_generated_at=report_generated_at,
                    snapshot_id=snapshot_id,
                    session_type=(
                        session.session_type if session is not None else None
                    ),
                    input_identity_summary=_input_identity_summary(
                        source,
                        session,
                        snapshot_id=snapshot_id,
                        snapshot_reused=snapshot_reused,
                    ),
                    raw_message_count=getattr(
                        diagnostic_counts,
                        "raw_message_count",
                        None,
                    ),
                    imported_message_count=getattr(
                        diagnostic_counts,
                        "imported_message_count",
                        None,
                    ),
                    scope_message_count=getattr(
                        diagnostic_counts,
                        "scope_message_count",
                        None,
                    ),
                    filtered_message_count=getattr(
                        diagnostic_counts,
                        "filtered_message_count",
                        None,
                    ),
                    analyzed_message_count=getattr(
                        diagnostic_counts,
                        "analyzed_message_count",
                        None,
                    ),
                )
            except Exception:
                _LOGGER.exception(
                    "Analysis completed but history metadata could not be saved."
                )
                history_saved = False
            else:
                history_saved = True
                history_record_id = history_record.analysis_id

        outcome = AnalysisOutcome(
            view=view,
            result=result,
            source=source,
            session=session,
            artifact_directory=(
                output_directory if report_path is not None else None
            ),
            report_path=report_path,
            history_saved=history_saved,
            history_record_id=history_record_id,
            snapshot_id=snapshot_id,
            data_acquired_at=data_acquired_at,
            snapshot_reused=snapshot_reused,
        )
        _report_progress(progress, "分析完成")
        return outcome

    def _replace_retained_output(
        self,
        temporary_output: _RetainedReportDirectory | None,
    ) -> None:
        """Keep only the latest successful scratch report alive."""
        previous = self._retained_output_directory
        self._retained_output_directory = temporary_output
        if previous is not None and previous is not temporary_output:
            previous.cleanup()

    def shutdown(self) -> None:
        """Release transient artifacts retained by this facade."""
        self._replace_retained_output(None)

    def _build_view(self, result: AnalysisResultDTO) -> DashboardView:
        """Hand the reports to the presentation layer without touching them."""
        reports = getattr(result, "reports", None)
        top_words = getattr(result, "top_words", ()) or ()

        if self._presentation_builder is not None:
            return self._presentation_builder.build(
                reports,
                top_words=top_words,
            )
        return build_dashboard_view(reports, top_words=top_words)

    def _export_session(
        self,
        source: ChatSource,
        service: Any,
        session_id: str,
        config: AnalysisConfig,
        scratch_directory: Path,
        *,
        raw_session: Any = None,
    ) -> _SessionExport:
        """Ask the matching service for an export file."""
        if source is ChatSource.QQ:
            session_type = _first_string(raw_session, "session_type")
            request = QQExportImportRequest(
                group_code=session_id,
                start_time=None,
                end_time=None,
                chat_type=1 if session_type == "private" else 2,
                peer_uin=_first_string(raw_session, "peer_uin") or None,
                session_name=_first_string(
                    raw_session,
                    "display_name",
                    "group_name",
                ) or None,
                force_refresh=config.force_refresh,
            )
            acquire_export = getattr(service, "acquire_export", None)
            if callable(acquire_export):
                acquisition = acquire_export(request)
                return _SessionExport(
                    payload_path=Path(acquisition.payload_path),
                    snapshot_id=getattr(acquisition, "snapshot_id", None),
                    acquired_at=getattr(acquisition, "acquired_at", None),
                    reused_snapshot=bool(
                        getattr(acquisition, "reused_snapshot", False)
                    ),
                )
            return _SessionExport(
                payload_path=Path(service.export_only(request))
            )

        return _SessionExport(
            payload_path=Path(
                service.export_only(
                    WeChatExportImportRequest(
                        session_id=session_id,
                        output_path=(
                            scratch_directory / "wechat_export.json"
                        ),
                        start_time=None,
                        end_time=None,
                    )
                )
            )
        )

    @staticmethod
    def _resolve_scope(
        config: AnalysisConfig,
        source: ChatSource,
    ) -> AnalysisScope:
        with _translated_errors(source):
            return resolve_scope(
                config.scope_mode,
                start_time=config.start_time,
                end_time=config.end_time,
            )

    def _stopwords_path(self, profile: str) -> Path:
        filename = _PROFILE_STOPWORD_FILES.get(
            profile,
            _PROFILE_STOPWORD_FILES[DEFAULT_PROFILE],
        )
        return self._stopwords_directory / filename

    def _is_available(self, source: ChatSource) -> bool:
        if source is ChatSource.LOCAL_FILE:
            return self._analysis_service is not None
        return (
            self._services.get(source) is not None
            or source in self._source_builders
        )

    def _require_service(self, source: ChatSource) -> Any:
        service = self._services.get(source)
        if service is None:
            bundle = self._source_bundle(source)
            service = getattr(bundle, "service", None)
        if service is None:
            raise SourceUnavailable(source)
        return service

    def _require_connection_service(self, source: ChatSource) -> Any:
        if source is ChatSource.QQ:
            service = self._qq_connection_service
        elif source is ChatSource.WECHAT:
            service = self._wechat_connection_service
        else:
            raise UnknownChatSource(source)
        if service is None:
            bundle = self._source_bundle(source)
            service = getattr(bundle, "connection", None)
        if service is None:
            raise SourceUnavailable(source)
        return service

    def _require_qq_connection_manager(self) -> Any:
        """Return the QQ connection manager, building it on first use.

        The manager is composed from the services this facade already holds,
        so a caller that injected stubs keeps getting those stubs.
        """
        if self._qq_connection_manager is None:
            self._qq_connection_manager = QQConnectionManager(
                setup_service=self._optional_qq_setup_service(),
                connection_service=self._optional_qq_connection_service(),
            )
        return self._qq_connection_manager

    def _require_qq_auth_bridge(self) -> Any:
        """Return the QQ auth bridge, composing it from injected services."""
        if self._qq_auth_bridge is None:
            from .connection import QQAuthBridge
            from .connection.qq_auth_bridge import (
                terminate_bundled_runtime_sessions,
            )

            self._qq_auth_bridge = QQAuthBridge(
                setup_service=self._optional_qq_setup_service(),
                connection_service=self._optional_qq_connection_service(),
                manager=self._require_qq_connection_manager(),
                process_registry=self._require_qq_process_registry(),
                # Temporary manual A/B: keep the cleaner available but skip it.
                runtime_cleaner=None,
            )
        return self._qq_auth_bridge

    def _require_qq_process_registry(self) -> Any:
        """Return the shared QQ process registry for this application."""
        if self._qq_process_registry is None:
            from .qq_process_registry import (
                default_qq_process_registry,
            )

            self._qq_process_registry = default_qq_process_registry()
        return self._qq_process_registry

    def _optional_qq_setup_service(self) -> Any:
        try:
            return self._require_qq_setup_service()
        except SourceUnavailable:
            return None

    def _optional_qq_connection_service(self) -> Any:
        try:
            return self._require_connection_service(ChatSource.QQ)
        except (SourceUnavailable, UnknownChatSource):
            return None

    def _require_qq_setup_service(self) -> Any:
        service = self._qq_setup_service
        if service is None:
            bundle = self._source_bundle(ChatSource.QQ)
            service = getattr(bundle, "setup", None)
        if service is None:
            raise SourceUnavailable(ChatSource.QQ)
        return service

    def _require_setup_service(self) -> Any:
        service = self._wechat_setup_service
        if service is None:
            bundle = self._source_bundle(ChatSource.WECHAT)
            service = getattr(bundle, "setup", None)
        if service is None:
            raise SourceUnavailable(ChatSource.WECHAT)
        return service

    def _source_bundle(self, source: ChatSource) -> Any:
        """Build and cache one source's services on first access."""
        if source not in self._built_sources:
            builder = self._source_builders.get(source)
            if builder is None:
                raise SourceUnavailable(source)
            self._built_sources[source] = builder()
        return self._built_sources[source]

    def _require_analysis_service(self) -> Any:
        if self._analysis_service is None:
            raise SourceUnavailable(ChatSource.LOCAL_FILE)
        return self._analysis_service


# ------------------------------------------------------------------ helpers


def _create_output_directory(
    config: AnalysisConfig,
) -> tuple[Path, _RetainedReportDirectory | None]:
    """Create an artifact directory and transfer scratch ownership upward."""
    if config.output_directory is not None:
        directory = Path(config.output_directory)
        directory.mkdir(parents=True, exist_ok=True)
        return directory, None

    reports_directory = user_data_dir() / "reports"
    reports_directory.mkdir(parents=True, exist_ok=True)
    scratch = _RetainedReportDirectory(reports_directory)
    return Path(scratch.name), scratch


def _generated_echo_report_path(
    result: AnalysisResultDTO,
    output_directory: Path,
) -> Path | None:
    """Resolve the report descriptor produced by this exact analysis run."""
    for artifact in result.artifacts:
        if artifact.kind != "echo_report_html":
            continue
        candidate = (output_directory / artifact.filename).resolve()
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            return None
    return None


@contextmanager
def _translated_errors(source: ChatSource | None) -> Iterator[None]:
    """Convert every known collaborator failure into a :class:`FacadeError`."""
    try:
        yield
    except FacadeError:
        raise
    except ApplicationServiceError as error:
        raise FacadeError(
            code=getattr(error, "code", "application_error"),
            public_message=getattr(
                error,
                "public_message",
                str(error),
            ),
            source=source,
        ) from error
    except Exception as error:
        raise FacadeError(
            code=_provider_error_code(error),
            public_message=_provider_error_message(error),
            source=source,
        ) from error


def _provider_error_code(error: Exception) -> str:
    """Prefer a provider's own stable code, else derive one from its class."""
    code = getattr(error, "code", None)
    if isinstance(code, str) and code.strip():
        return code
    return _snake_case(type(error).__name__)


def _provider_error_message(error: Exception) -> str:
    """Use a provider's user-facing message when it offers one."""
    message = getattr(error, "public_message", None)
    if isinstance(message, str) and message.strip():
        return message
    text = str(error).strip()
    if text:
        return text
    return "\u5206\u6790\u8fc7\u7a0b\u51fa\u73b0\u9519\u8bef\u3002"


def _snake_case(name: str) -> str:
    characters: list[str] = []
    for index, character in enumerate(name):
        if character.isupper() and index > 0:
            characters.append("_")
        characters.append(character.lower())
    return "".join(characters)


def _epoch_millis(epoch_seconds: int | None) -> int | None:
    """Convert epoch seconds to milliseconds for the QCE export API."""
    if epoch_seconds is None:
        return None
    return epoch_seconds * 1000


def _coerce_source(source: Any) -> ChatSource:
    """Accept a :class:`ChatSource` or its string value."""
    if isinstance(source, ChatSource):
        return source
    try:
        return ChatSource(source)
    except (ValueError, TypeError):
        raise UnknownChatSource(source) from None


def _input_identity_summary(
    source: ChatSource,
    session: SessionInfo | None,
    *,
    snapshot_id: str | None,
    snapshot_reused: bool,
) -> InputIdentitySummary | None:
    """Describe acquisition state without repeating input identity."""
    if session is None:
        return None
    if snapshot_id is not None:
        capture_mode = "snapshot"
    elif source is ChatSource.QQ:
        capture_mode = "provider_export"
    elif source is ChatSource.WECHAT:
        capture_mode = "live_database"
    else:
        return None
    return InputIdentitySummary(
        snapshot_reused=snapshot_reused,
        capture_mode=capture_mode,
    )


def _to_session_info(source: ChatSource, raw_session: Any) -> SessionInfo:
    """Normalise one provider session or group into :class:`SessionInfo`.

    QQ groups expose ``group_code``/``group_name``/``member_count`` while
    WeChat sessions expose ``session_id``/``display_name``/``message_count``.
    Both collapse into the same shape here so a caller never branches on the
    source when rendering a list.
    """
    if source is ChatSource.QQ:
        session_id = _first_string(raw_session, "group_code", "session_id")
        display_name = _first_string(
            raw_session,
            "group_name",
            "display_name",
        )
        session_type = _first_string(raw_session, "session_type") or "group"
    else:
        session_id = _first_string(raw_session, "session_id", "group_code")
        display_name = _first_string(
            raw_session,
            "display_name",
            "group_name",
        )
        session_type = _first_string(raw_session, "session_type") or "other"

    return SessionInfo(
        source=source,
        session_id=session_id,
        display_name=(
            display_name
            or ("\u672a\u77e5\u7fa4\u804a" if source is ChatSource.QQ else session_id)
        ),
        session_type=session_type,
        message_count=_first_int(raw_session, "message_count", "member_count"),
        last_message_time=_first_epoch(
            raw_session,
            "last_message_time",
            "last_timestamp",
        ),
        message_available=bool(
            getattr(raw_session, "message_available", True)
        ),
        unavailable_reason=getattr(raw_session, "unavailable_reason", None),
    )


def _first_string(raw_session: Any, *names: str) -> str:
    for name in names:
        value = getattr(raw_session, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_int(raw_session: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(raw_session, name, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _first_epoch(raw_session: Any, *names: str) -> int | None:
    for name in names:
        value = getattr(raw_session, name, None)
        if value is None:
            continue
        epoch = to_epoch_seconds(value)
        if epoch is not None:
            return epoch
    return None
