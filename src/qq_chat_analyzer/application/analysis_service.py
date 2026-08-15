"""Application orchestration for one local chat analysis run."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from ..analysis.identity import stable_sender_key
from ..analysis.conversation_sessions import analyze_conversation_sessions
from ..analysis.analyzers import (
    ActivityAnalyzer,
    ConversationAnalyzer,
    DistinctiveWordAnalyzer,
    ExpressionAnalyzer,
    MessageCompositionAnalyzer,
    MessageLengthAnalyzer,
    PrivateLanguageAnalyzer,
    UserProfileAnalyzer,
)
from ..analysis.analyzers.expression_analyzer import iter_emoji_clusters
from ..analysis.models import AnalysisReports
from ..analyzer import (
    WordSpeakerSummary,
    count_word_speakers,
    top_word_speaker_summary,
    top_words,
)
from ..cleaner import clean_text
from ..exporters import (
    export_word_frequency_csv,
    export_word_speaker_frequency_csv,
    export_word_speaker_summary_csv,
    generate_word_top_speakers_chart,
    generate_wordcloud,
)
from ..message import ChatMessage
from ..message_quality_filter import apply_message_quality_filter
from ..rich_message import ExpressionContent, RichMessage
from ..presentation import (
    EchoReportView,
    build_echo_report_view,
    export_echo_report_html,
    export_echo_report_json,
)
from ..smart_profile import run_smart_profile
from ..tokenizer import tokenize
from .dto import (
    AnalysisDiagnosticCounts,
    AnalysisRequestDTO,
    AnalysisResultDTO,
    AnalysisStatus,
    ArtifactDTO,
    WordFrequencyDTO,
)
from .errors import (
    ArtifactGenerationFailed,
    InputPathNotFound,
    InvalidAnalysisRequest,
    NoMessagesInScope,
)
from .import_request import ImportRequest
from .import_service import ImportService
from .scope_filter import AnalysisScopeMode, filter_messages


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.identity")

_ARTIFACT_FILENAMES = {
    "word_frequency_csv": "word_frequency.csv",
    "wordcloud": "wordcloud.png",
    "word_speaker_summary_csv": "word_speaker_summary.csv",
    "word_speaker_frequency_csv": "word_speaker_frequency.csv",
    "word_top_speakers_chart": "word_top_speakers.png",
    "echo_report_json": "echo-report.json",
    "echo_report_html": "echo-report.html",
}
_ECHO_ARTIFACTS = (
    ArtifactDTO(kind="echo_report_json", filename="echo-report.json"),
    ArtifactDTO(kind="echo_report_html", filename="echo-report.html"),
)


@dataclass(slots=True)
class _AnalyzedMessages:
    valid_text_count: int
    tokens: list[str]
    sender_tokens: list[tuple[str, list[str]]]


class AnalysisApplicationService:
    """Coordinate one complete analysis use case without CLI behavior."""

    def execute(self, request: AnalysisRequestDTO) -> AnalysisResultDTO:
        """Analyze supported local exports and return a privacy-safe result."""
        _validate_request(request)
        outcome = ImportService().execute(
            ImportRequest(input_path=request.input_path)
        )
        _log_identity_diagnostics(outcome.messages)
        processed_message_count = outcome.processed_message_count
        parsed_messages = list(outcome.messages)
        scoped_messages = filter_messages(parsed_messages, request.scope)
        if (
            request.scope.mode is not AnalysisScopeMode.ALL
            and not scoped_messages
        ):
            raise NoMessagesInScope()
        if request.scope.mode is not AnalysisScopeMode.ALL:
            processed_message_count = len(scoped_messages)
        filtering_result = run_smart_profile(scoped_messages)
        quality_result = apply_message_quality_filter(
            filtering_result.kept_messages
        )
        kept_messages = quality_result.kept_messages
        diagnostic_counts = AnalysisDiagnosticCounts(
            raw_message_count=outcome.processed_message_count,
            imported_message_count=len(parsed_messages),
            scope_message_count=len(scoped_messages),
            filtered_message_count=len(kept_messages),
            analyzed_message_count=len(kept_messages),
        )
        analyzed = _analyze_kept_messages(
            kept_messages,
            request.stopwords_path,
            outcome.rich_messages,
        )
        expression_report = ExpressionAnalyzer().analyze(
            kept_messages,
            rich_messages=outcome.rich_messages,
        )
        has_expression_report = expression_report.expression_message_count > 0

        if analyzed.valid_text_count == 0 and not has_expression_report:
            return AnalysisResultDTO(
                status=AnalysisStatus.NO_VALID_TEXT,
                processed_message_count=processed_message_count,
                valid_text_count=0,
                diagnostic_counts=diagnostic_counts,
            )
        if not analyzed.tokens and not has_expression_report:
            return AnalysisResultDTO(
                status=AnalysisStatus.NO_TOKENS,
                processed_message_count=processed_message_count,
                valid_text_count=analyzed.valid_text_count,
                diagnostic_counts=diagnostic_counts,
            )
        conversation_type = _resolve_conversation_type(
            kept_messages,
            request.conversation_kind,
        )
        if not analyzed.tokens and has_expression_report:
            return _expression_only_result(
                request=request,
                kept_messages=kept_messages,
                analyzed=analyzed,
                diagnostic_counts=diagnostic_counts,
                processed_message_count=processed_message_count,
                rich_messages=outcome.rich_messages,
                conversation_type=conversation_type,
            )

        ranked_words = top_words(analyzed.tokens, request.top)
        if not ranked_words and has_expression_report:
            return _expression_only_result(
                request=request,
                kept_messages=kept_messages,
                analyzed=analyzed,
                diagnostic_counts=diagnostic_counts,
                processed_message_count=processed_message_count,
                rich_messages=outcome.rich_messages,
                conversation_type=conversation_type,
            )
        if not ranked_words:
            return AnalysisResultDTO(
                status=AnalysisStatus.NO_TOKENS,
                processed_message_count=processed_message_count,
                valid_text_count=analyzed.valid_text_count,
                diagnostic_counts=diagnostic_counts,
            )

        reports = _build_reports(
            kept_messages,
            analyzed.sender_tokens,
            speaker_names=request.speaker_names,
            conversation_names=request.conversation_names,
            conversation_type=conversation_type,
            rich_messages=outcome.rich_messages,
        )
        speaker_display_names = _speaker_display_names(reports)
        word_sender_counts = count_word_speakers(
            _text_sender_tokens(analyzed.sender_tokens)
        )
        speaker_summaries = _display_speaker_summaries(
            top_word_speaker_summary(word_sender_counts),
            speaker_display_names,
        )
        speaker_frequency_rows = [
            (
                summary.word,
                speaker_display_names.get(sender, sender),
                count,
            )
            for summary in speaker_summaries
            for sender, count in sorted(
                word_sender_counts[summary.word].items(),
                key=lambda item: -item[1],
            )
        ]
        viewer_speaker_key = _viewer_speaker_key(
            kept_messages,
            request.viewer_speaker_key,
        )

        try:
            echo_report_view = _export_artifacts(
                request,
                ranked_words,
                speaker_summaries,
                speaker_frequency_rows,
                reports,
                viewer_speaker_key=viewer_speaker_key,
                conversation_kind=conversation_type,
            )
        except (OSError, ValueError):
            raise ArtifactGenerationFailed() from None

        _LOGGER.info(
            "[analysis] echo artifacts exported echo_view=%s "
            "conversation_type=%s",
            echo_report_view is not None,
            conversation_type,
        )
        return AnalysisResultDTO(
            status=AnalysisStatus.COMPLETED,
            processed_message_count=processed_message_count,
            valid_text_count=analyzed.valid_text_count,
            diagnostic_counts=diagnostic_counts,
            top_words=tuple(
                WordFrequencyDTO(word=word, count=count)
                for word, count in ranked_words
            ),
            artifacts=tuple(
                ArtifactDTO(kind=kind, filename=filename)
                for kind, filename in _ARTIFACT_FILENAMES.items()
            ),
            reports=reports,
            echo_report_view=echo_report_view,
        )


def _build_reports(
    messages: list[ChatMessage],
    sender_tokens: list[tuple[str, list[str]]],
    speaker_names: Mapping[str, str] | None = None,
    conversation_names: Mapping[str, str] | None = None,
    conversation_type: str = "unknown",
    rich_messages: tuple[RichMessage, ...] = (),
) -> AnalysisReports:
    """Run every extended analyzer over the messages kept for analysis.

    Display names are supplied by the caller and simply forwarded. The
    analysis core therefore stays unaware of QQ or WeChat naming rules, and
    omitting the mappings keeps the previous raw-identifier behavior.
    """
    return AnalysisReports(
        activity=ActivityAnalyzer().analyze(messages),
        message_length=MessageLengthAnalyzer().analyze(messages),
        user_profiles=UserProfileAnalyzer().analyze(
            messages,
            sender_tokens=sender_tokens,
            speaker_names=speaker_names,
        ),
        conversations=ConversationAnalyzer().analyze(
            messages,
            conversation_names=conversation_names,
        ),
        message_composition=MessageCompositionAnalyzer().analyze(messages),
        conversation_sessions=analyze_conversation_sessions(messages),
        distinctive_words=DistinctiveWordAnalyzer().analyze(
            sender_tokens,
            conversation_type=conversation_type,
        ),
        private_language=PrivateLanguageAnalyzer().analyze(
            sender_tokens,
            conversation_type=conversation_type,
        ),
        expression=ExpressionAnalyzer().analyze(
            messages,
            rich_messages=rich_messages,
        ),
    )


def _expression_only_result(
    *,
    request: AnalysisRequestDTO,
    kept_messages: list[ChatMessage],
    analyzed: _AnalyzedMessages,
    diagnostic_counts: AnalysisDiagnosticCounts,
    processed_message_count: int,
    rich_messages: tuple[RichMessage, ...],
    conversation_type: str,
) -> AnalysisResultDTO:
    """Build the guarded expression-only result with graceful fallback."""
    try:
        reports = _build_reports(
            kept_messages,
            analyzed.sender_tokens,
            speaker_names=request.speaker_names,
            conversation_names=request.conversation_names,
            conversation_type=conversation_type,
            rich_messages=rich_messages,
        )
        echo_report_view = _export_echo_artifacts(
            request,
            reports,
            viewer_speaker_key=_viewer_speaker_key(
                kept_messages,
                request.viewer_speaker_key,
            ),
            conversation_kind=conversation_type,
        )
    except Exception:
        _LOGGER.warning(
            "expression-only report generation failed; falling back",
            exc_info=True,
        )
        for filename in (
            _ARTIFACT_FILENAMES["echo_report_json"],
            _ARTIFACT_FILENAMES["echo_report_html"],
        ):
            try:
                (request.output_directory / filename).unlink(missing_ok=True)
            except OSError:
                pass
        return AnalysisResultDTO(
            status=AnalysisStatus.NO_TOKENS,
            processed_message_count=processed_message_count,
            valid_text_count=analyzed.valid_text_count,
            diagnostic_counts=diagnostic_counts,
        )
    return AnalysisResultDTO(
        status=AnalysisStatus.EXPRESSION_ONLY,
        processed_message_count=processed_message_count,
        valid_text_count=analyzed.valid_text_count,
        diagnostic_counts=diagnostic_counts,
        artifacts=_ECHO_ARTIFACTS,
        reports=reports,
        echo_report_view=echo_report_view,
    )


def _validate_request(request: AnalysisRequestDTO) -> None:
    if (
        not isinstance(request.top, int)
        or isinstance(request.top, bool)
        or request.top <= 0
    ):
        raise InvalidAnalysisRequest()
    if not request.input_path.exists():
        raise InputPathNotFound()


def _resolve_conversation_type(
    messages: list[ChatMessage],
    requested_type: str,
) -> str:
    """Use explicit application context, then unanimous message semantics."""
    if requested_type in {"group", "private"}:
        return requested_type
    message_types = {message.conversation_type for message in messages}
    if message_types == {"group"}:
        return "group"
    if message_types == {"private"}:
        return "private"
    return "unknown"


def _analyze_kept_messages(
    messages: list[ChatMessage],
    stopwords_path: Path,
    rich_messages: tuple[RichMessage, ...] = (),
) -> _AnalyzedMessages:
    valid_text_count = 0
    tokens: list[str] = []
    sender_tokens: list[tuple[str, list[str]]] = []
    rich_by_id = {
        message.message_id: message
        for message in rich_messages
        if message.message_id is not None
    }

    for message in messages:
        cleaned_text = clean_text(message.text, platform=message.platform)
        message_tokens = (
            tokenize(cleaned_text, str(stopwords_path))
            if cleaned_text
            else []
        )
        if cleaned_text:
            valid_text_count += 1
        tokens.extend(message_tokens)
        expression_tokens = _expression_tokens(
            message,
            rich_by_id,
        )
        combined_tokens = [*message_tokens, *expression_tokens]
        if combined_tokens:
            sender_tokens.append(
                (stable_sender_key(message), combined_tokens)
            )

    return _AnalyzedMessages(
        valid_text_count=valid_text_count,
        tokens=tokens,
        sender_tokens=sender_tokens,
    )


def _expression_tokens(
    message: ChatMessage,
    rich_by_id: Mapping[str, RichMessage],
) -> list[str]:
    """Return source-neutral expression tokens for the Voices pipeline."""
    tokens = [
        f"expression:{emoji}"
        for emoji in iter_emoji_clusters(message.text)
    ]
    rich_message = (
        rich_by_id.get(message.message_id)
        if message.message_id is not None
        else None
    )
    if rich_message is not None:
        tokens.extend(
            f"expression:{content.expression_key}"
            for content in rich_message.contents
            if isinstance(content, ExpressionContent)
        )
    return tokens


def _text_sender_tokens(
    sender_tokens: list[tuple[str, list[str]]],
) -> list[tuple[str, list[str]]]:
    return [
        (
            speaker_key,
            [
                token
                for token in message_tokens
                if not token.startswith("expression:")
            ],
        )
        for speaker_key, message_tokens in sender_tokens
    ]


def _speaker_display_names(reports: AnalysisReports) -> dict[str, str]:
    """Map stable speaker keys to resolved display names for artifacts."""
    if reports.user_profiles is None:
        return {}
    return {
        profile.speaker_key or profile.speaker: profile.resolved_display_name
        for profile in reports.user_profiles.profiles
    }


def _display_speaker_summaries(
    summaries: list[WordSpeakerSummary],
    speaker_display_names: Mapping[str, str],
) -> list[WordSpeakerSummary]:
    """Translate stable speaker keys into display names in summaries."""
    if not speaker_display_names:
        return summaries
    return [
        replace(
            summary,
            top_speaker=speaker_display_names.get(
                summary.top_speaker,
                summary.top_speaker,
            ),
        )
        for summary in summaries
    ]


def _viewer_speaker_key(
    messages: list[ChatMessage],
    explicit: str | None,
) -> str | None:
    """Resolve the Echo viewer key only from reliable self markers."""
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    for message in messages:
        if message.is_self is True:
            return stable_sender_key(message)
    return None


def _log_identity_diagnostics(messages: list[ChatMessage]) -> None:
    """Log anonymized identity acceptance state for one imported source."""
    if not messages:
        return
    source = messages[0].platform or "unknown"
    conversation_type = next(
        (
            message.conversation_type
            for message in messages
            if message.conversation_type in ("private", "group")
        ),
        "unknown",
    )
    self_resolved = any(
        message.is_self is True or message.is_self is False
        for message in messages
    )
    resolved_senders = sum(
        1
        for message in messages
        if isinstance(message.sender_id, str) and message.sender_id.strip()
    )
    if resolved_senders == len(messages):
        sender_coverage = "resolved"
    elif resolved_senders:
        sender_coverage = "partial"
    else:
        sender_coverage = "unknown"
    _LOGGER.info(
        "[identity] source=%s conversation_type=%s "
        "self_identity=%s sender_identity_coverage=%s",
        source,
        conversation_type,
        "resolved" if self_resolved else "unknown",
        sender_coverage,
    )


def _export_artifacts(
    request: AnalysisRequestDTO,
    ranked_words: list[tuple[str, int]],
    speaker_summaries: list[WordSpeakerSummary],
    speaker_frequency_rows: list[tuple[str, str, int]],
    reports: AnalysisReports,
    *,
    viewer_speaker_key: str | None,
    conversation_kind: str,
) -> EchoReportView:
    output_directory = request.output_directory
    export_word_frequency_csv(
        ranked_words,
        str(output_directory / _ARTIFACT_FILENAMES["word_frequency_csv"]),
    )
    export_word_speaker_summary_csv(
        speaker_summaries,
        str(
            output_directory
            / _ARTIFACT_FILENAMES["word_speaker_summary_csv"]
        ),
    )
    export_word_speaker_frequency_csv(
        speaker_frequency_rows,
        str(
            output_directory
            / _ARTIFACT_FILENAMES["word_speaker_frequency_csv"]
        ),
    )
    generate_word_top_speakers_chart(
        speaker_summaries,
        str(
            output_directory
            / _ARTIFACT_FILENAMES["word_top_speakers_chart"]
        ),
        request.font_path,
    )
    generate_wordcloud(
        ranked_words,
        str(output_directory / _ARTIFACT_FILENAMES["wordcloud"]),
        request.font_path,
    )
    return _export_echo_artifacts(
        request,
        reports,
        viewer_speaker_key=viewer_speaker_key,
        conversation_kind=conversation_kind,
    )


def _export_echo_artifacts(
    request: AnalysisRequestDTO,
    reports: AnalysisReports,
    *,
    viewer_speaker_key: str | None,
    conversation_kind: str,
) -> EchoReportView:
    """Write the Echo JSON and self-contained HTML report artifacts."""
    output_directory = request.output_directory
    view = build_echo_report_view(
        reports,
        viewer_speaker_key=viewer_speaker_key,
        conversation_kind=conversation_kind,
    )
    export_echo_report_json(
        view,
        str(output_directory / _ARTIFACT_FILENAMES["echo_report_json"]),
    )
    export_echo_report_html(
        view,
        str(output_directory / _ARTIFACT_FILENAMES["echo_report_html"]),
    )
    return view
