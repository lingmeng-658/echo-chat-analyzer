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

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator, Protocol, runtime_checkable

from ..presentation import DashboardView, build_dashboard_view
from .dto import AnalysisRequestDTO, AnalysisResultDTO
from .errors import ApplicationServiceError
from .qq_export_import_service import QQExportImportRequest
from .wechat_export_import_service import WeChatExportImportRequest


DEFAULT_TOP = 50
DEFAULT_PROFILE = "default"

_PROFILE_STOPWORD_FILES = {
    "default": "stopwords.txt",
    "topic": "stopwords_topic.txt",
    "culture": "stopwords_culture.txt",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
        "QQ \u6570\u636e\u6e90\u5c1a\u672a\u914d\u7f6e\u3002"
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
        wechat_service: Any = None,
        analysis_service: Any = None,
        presentation_builder: Any = None,
        stopwords_directory: Path | None = None,
    ) -> None:
        self._services: dict[ChatSource, Any] = {
            ChatSource.QQ: qq_service,
            ChatSource.WECHAT: wechat_service,
        }
        self._analysis_service = analysis_service
        self._presentation_builder = presentation_builder
        self._stopwords_directory = stopwords_directory or _PROJECT_ROOT

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
        session = SessionInfo(
            source=chat_source,
            session_id=session_id,
            display_name=session_id,
        )

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
            )

    # ------------------------------------------------------------- internals

    def _analyze_path(
        self,
        input_path: Path,
        config: AnalysisConfig,
        *,
        source: ChatSource,
        session: SessionInfo | None,
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
        if source is ChatSource.QQ:
            return service.export_only(
                QQExportImportRequest(
                    group_code=session_id,
                    start_time=config.start_time,
                    end_time=config.end_time,
                )
            )

        return service.export_only(
            WeChatExportImportRequest(
                session_id=session_id,
                output_path=scratch_directory / "wechat_export.json",
                start_time=config.start_time,
                end_time=config.end_time,
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
        return self._services.get(source) is not None

    def _require_service(self, source: ChatSource) -> Any:
        service = self._services.get(source)
        if service is None:
            raise SourceUnavailable(source)
        return service

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
        display_name=display_name or session_id,
        session_type=session_type,
        message_count=_first_int(raw_session, "message_count", "member_count"),
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