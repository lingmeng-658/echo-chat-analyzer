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
* Intermediate export files are an implementation detail. They are created in
  a temporary directory, consumed, and never surfaced to the caller.

Everything that escapes this layer is either a plain view model or a
:class:`FacadeError` carrying a stable ``code`` and a user-safe message.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterator, Protocol, runtime_checkable

from ..resources import resources_dir
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
from .wechat_connection_service import WeChatConnectionStatus
from .wechat_environment_config import WeChatEnvironmentConfig
from .wechat_export_import_service import WeChatExportImportRequest
from .wechat_setup_service import WeChatSetupStatus


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.facade")


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

    ``start_time`` and ``end_time`` bound which messages are exported. They
    describe the analysis window only; no relationship or acquaintance
    duration is inferred from them.
    """

    start_time: Any = None
    end_time: Any = None
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
        self._stopwords_directory = stopwords_directory or resources_dir()

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
                raw_sessions = service.list_groups()
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
        """Connect QQ without any technical input from the user.

        Runtime detection, startup, and connection probing stay inside the
        connection manager; the GUI only receives the resulting lifecycle
        snapshot.
        """
        return self._require_qq_connection_manager().connect()

    def start_qq_auth_flow(self) -> ConnectionSnapshot:
        """Start QQ authorization and return the resulting lifecycle state.

        The GUI calls this instead of a raw connect: the auth bridge starts
        the runtime's own login flow and the caller keeps polling
        :meth:`get_qq_connection_snapshot` until it reports ``CONNECTED``.
        """
        return self._require_qq_auth_bridge().start_auth_flow()

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

    # -------------------------------------------------------------- analysis

    def analyze_file(
        self,
        path: str | Path,
        config: AnalysisConfig | None = None,
    ) -> AnalysisOutcome:
        """Analyze one already-exported local file or directory."""
        resolved_config = config or AnalysisConfig()
        input_path = Path(path)

        return self._analyze_path(
            input_path,
            resolved_config,
            source=ChatSource.LOCAL_FILE,
            session=None,
        )

    def analyze_session(
        self,
        source: ChatSource,
        session_id: str,
        config: AnalysisConfig | None = None,
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
        service = self._require_service(chat_source)
        if chat_source is ChatSource.WECHAT:
            raw_session = next(
                (
                    candidate
                    for candidate in (service.list_sessions() or ())
                    if getattr(candidate, "session_id", None) == session_id
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
        else:
            session = SessionInfo(
                source=chat_source,
                session_id=session_id,
                display_name=session_id,
            )
            conversation_names = None

        with TemporaryDirectory(prefix="chat-analyzer-export-") as scratch:
            scratch_directory = Path(scratch)
            with _translated_errors(chat_source):
                export_path = self._export_session(
                    chat_source,
                    service,
                    session_id,
                    resolved_config,
                    scratch_directory,
                )

            return self._analyze_path(
                Path(export_path),
                resolved_config,
                source=chat_source,
                session=session,
                conversation_names=conversation_names,
            )

    # ------------------------------------------------------------- internals

    def _analyze_path(
        self,
        input_path: Path,
        config: AnalysisConfig,
        *,
        source: ChatSource,
        session: SessionInfo | None,
        speaker_names: Mapping[str, str] | None = None,
        conversation_names: Mapping[str, str] | None = None,
    ) -> AnalysisOutcome:
        """Run analysis then presentation for one local path."""
        analysis_service = self._require_analysis_service()

        with _output_directory(config) as output_directory:
            request = AnalysisRequestDTO(
                input_path=input_path,
                output_directory=output_directory,
                stopwords_path=self._stopwords_path(config.profile),
                font_path=config.font_path,
                top=config.top,
                speaker_names=speaker_names or {},
                conversation_names=conversation_names or {},
            )
            with _translated_errors(source):
                result = analysis_service.execute(request)

            view = self._build_view(result)

        return AnalysisOutcome(
            view=view,
            result=result,
            source=source,
            session=session,
            artifact_directory=config.output_directory,
        )

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
    ) -> Path:
        """Ask the matching service for an export file."""
        start_epoch = to_epoch_seconds(config.start_time)
        end_epoch = to_epoch_seconds(config.end_time)
        if source is ChatSource.QQ:
            return service.export_only(
                QQExportImportRequest(
                    group_code=session_id,
                    start_time=_epoch_millis(start_epoch),
                    end_time=_epoch_millis(end_epoch),
                )
            )

        return service.export_only(
            WeChatExportImportRequest(
                session_id=session_id,
                output_path=scratch_directory / "wechat_export.json",
                start_time=start_epoch,
                end_time=end_epoch,
            )
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

            self._qq_auth_bridge = QQAuthBridge(
                setup_service=self._optional_qq_setup_service(),
                connection_service=self._optional_qq_connection_service(),
                manager=self._require_qq_connection_manager(),
                process_registry=self._require_qq_process_registry(),
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


@contextmanager
def _output_directory(config: AnalysisConfig) -> Iterator[Path]:
    """Yield a directory for artifacts, scratch if the caller gave none."""
    if config.output_directory is not None:
        directory = Path(config.output_directory)
        directory.mkdir(parents=True, exist_ok=True)
        yield directory
        return

    with TemporaryDirectory(prefix="chat-analyzer-output-") as scratch:
        yield Path(scratch)


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
