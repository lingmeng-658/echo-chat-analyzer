"""Application orchestration for one local chat analysis run."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..analysis.analyzers import (
    ActivityAnalyzer,
    ConversationAnalyzer,
    MessageCompositionAnalyzer,
    MessageLengthAnalyzer,
    UserProfileAnalyzer,
)
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


_ARTIFACT_FILENAMES = {
    "word_frequency_csv": "word_frequency.csv",
    "wordcloud": "wordcloud.png",
    "word_speaker_summary_csv": "word_speaker_summary.csv",
    "word_speaker_frequency_csv": "word_speaker_frequency.csv",
    "word_top_speakers_chart": "word_top_speakers.png",
}


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
        kept_messages = filtering_result.kept_messages
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
        )

        if analyzed.valid_text_count == 0:
            return AnalysisResultDTO(
                status=AnalysisStatus.NO_VALID_TEXT,
                processed_message_count=processed_message_count,
                valid_text_count=0,
                diagnostic_counts=diagnostic_counts,
            )
        if not analyzed.tokens:
            return AnalysisResultDTO(
                status=AnalysisStatus.NO_TOKENS,
                processed_message_count=processed_message_count,
                valid_text_count=analyzed.valid_text_count,
                diagnostic_counts=diagnostic_counts,
            )

        ranked_words = top_words(analyzed.tokens, request.top)
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
        )
        word_sender_counts = count_word_speakers(analyzed.sender_tokens)
        speaker_summaries = top_word_speaker_summary(word_sender_counts)
        speaker_frequency_rows = [
            (summary.word, sender, count)
            for summary in speaker_summaries
            for sender, count in sorted(
                word_sender_counts[summary.word].items(),
                key=lambda item: -item[1],
            )
        ]

        try:
            _export_artifacts(
                request,
                ranked_words,
                speaker_summaries,
                speaker_frequency_rows,
            )
        except (OSError, ValueError):
            raise ArtifactGenerationFailed() from None

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
        )


def _build_reports(
    messages: list[ChatMessage],
    sender_tokens: list[tuple[str, list[str]]],
    speaker_names: Mapping[str, str] | None = None,
    conversation_names: Mapping[str, str] | None = None,
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


def _analyze_kept_messages(
    messages: list[ChatMessage],
    stopwords_path: Path,
) -> _AnalyzedMessages:
    valid_text_count = 0
    tokens: list[str] = []
    sender_tokens: list[tuple[str, list[str]]] = []

    for message in messages:
        cleaned_text = clean_text(message.text, platform=message.platform)
        if not cleaned_text:
            continue
        valid_text_count += 1
        message_tokens = tokenize(cleaned_text, str(stopwords_path))
        tokens.extend(message_tokens)
        if message_tokens:
            sender_tokens.append((message.sender, message_tokens))

    return _AnalyzedMessages(
        valid_text_count=valid_text_count,
        tokens=tokens,
        sender_tokens=sender_tokens,
    )


def _export_artifacts(
    request: AnalysisRequestDTO,
    ranked_words: list[tuple[str, int]],
    speaker_summaries: list[WordSpeakerSummary],
    speaker_frequency_rows: list[tuple[str, str, int]],
) -> None:
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
