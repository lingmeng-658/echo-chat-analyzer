"""Frequency and composition analysis for source-neutral expressions."""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Sequence

from ...message import ChatMessage
from ...rich_message import ExpressionContent, RichMessage, TextContent
from ..identity import stable_sender_key
from ..models import (
    ExpressionReport,
    ExpressionUsage,
    MemberExpressionUsage,
)


EXPRESSION_KIND_UNICODE = "unicode"
EXPRESSION_KIND_PLATFORM_FACE = "platform_face"

EXPRESSION_GLOBAL_TOP_LIMIT = 10
EXPRESSION_MEMBER_TOP_LIMIT = 3


class ExpressionAnalyzer:
    """Count expression occurrences without interpreting emotion."""

    def analyze(
        self,
        messages: Sequence[ChatMessage],
        rich_messages: Sequence[RichMessage] = (),
    ) -> ExpressionReport:
        rich_by_id = {
            message.message_id: message
            for message in rich_messages
            if message.message_id is not None
        }
        occurrences: Counter[str] = Counter()
        display_by_key: dict[str, str] = {}
        kind_by_key: dict[str, str] = {}
        member_occurrences: dict[str, Counter[str]] = {}
        member_message_counts: dict[str, int] = {}
        member_only_counts: dict[str, int] = {}
        expression_message_count = 0
        expression_only_message_count = 0
        total_message_count = len(messages)

        for message in messages:
            rich_message = (
                rich_by_id.get(message.message_id)
                if message.message_id is not None
                else None
            )
            text, face_expressions = self._message_expression_sources(
                message,
                rich_message,
            )
            unicode_items = list(iter_emoji_clusters(text))
            items = [
                (EXPRESSION_KIND_UNICODE, item, item)
                for item in unicode_items
            ]
            items.extend(
                (
                    expression.expression_kind,
                    expression.expression_key,
                    expression.display_text
                    or f"[表情 {expression.expression_key}]",
                )
                for expression in face_expressions
            )
            if not items:
                continue

            expression_message_count += 1
            expression_only = self._is_expression_only_message(
                text,
                unicode_items,
                face_expressions,
            )
            if expression_only:
                expression_only_message_count += 1

            speaker_key = stable_sender_key(message)
            speaker_counts = member_occurrences.setdefault(
                speaker_key,
                Counter(),
            )
            for kind, expression_key, display_text in items:
                occurrences[expression_key] += 1
                speaker_counts[expression_key] += 1
                display_by_key.setdefault(expression_key, display_text)
                kind_by_key.setdefault(expression_key, kind)
            member_message_counts[speaker_key] = (
                member_message_counts.get(speaker_key, 0) + 1
            )
            if expression_only:
                member_only_counts[speaker_key] = (
                    member_only_counts.get(speaker_key, 0) + 1
                )

        total_occurrences = sum(occurrences.values())
        top_expressions = tuple(
            ExpressionUsage(
                expression_key=key,
                display_text=display_by_key[key],
                count=count,
                kind=kind_by_key[key],
            )
            for key, count in _sorted_counts(occurrences)[
                :EXPRESSION_GLOBAL_TOP_LIMIT
            ]
        )
        members = tuple(
            MemberExpressionUsage(
                speaker_key=speaker_key,
                expression_occurrence_count=sum(counts.values()),
                expression_message_count=member_message_counts[speaker_key],
                expression_share_percent=_percent(
                    sum(counts.values()),
                    total_occurrences,
                ),
                expression_only_message_count=member_only_counts.get(
                    speaker_key,
                    0,
                ),
                top_expressions=tuple(
                    ExpressionUsage(
                        expression_key=key,
                        display_text=display_by_key[key],
                        count=count,
                        kind=kind_by_key[key],
                    )
                    for key, count in _sorted_counts(counts)[
                        :EXPRESSION_MEMBER_TOP_LIMIT
                    ]
                ),
            )
            for speaker_key, counts in member_occurrences.items()
        )
        members = tuple(
            sorted(
                members,
                key=lambda member: (
                    -member.expression_occurrence_count,
                    member.speaker_key,
                ),
            )
        )

        return ExpressionReport(
            expression_message_count=expression_message_count,
            expression_only_message_count=expression_only_message_count,
            expression_only_rate=_rate(
                expression_only_message_count,
                total_message_count,
            ),
            unique_expression_count=len(occurrences),
            expression_occurrence_count=total_occurrences,
            total_message_count=total_message_count,
            top_expressions=top_expressions,
            members=members,
        )

    @staticmethod
    def _message_expression_sources(
        message: ChatMessage,
        rich_message: RichMessage | None,
    ) -> tuple[str, tuple[ExpressionContent, ...]]:
        if rich_message is None:
            return message.text, ()
        text = "".join(
            content.text
            for content in rich_message.contents
            if isinstance(content, TextContent)
        )
        expressions = tuple(
            content
            for content in rich_message.contents
            if isinstance(content, ExpressionContent)
        )
        return text, expressions

    @staticmethod
    def _is_expression_only_message(
        text: str,
        unicode_items: list[str],
        face_expressions: tuple[ExpressionContent, ...],
    ) -> bool:
        if face_expressions:
            return not text.strip()
        if not unicode_items:
            return False
        compact = "".join(text.split())
        return bool(compact) and "".join(unicode_items) == compact


def _sorted_counts(counts: Counter[str]) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _percent(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part * 100.0 / total, 2)


def _rate(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total, 4)


def iter_emoji_clusters(text: str):
    """Yield stable common Unicode emoji clusters without full CLDR coverage."""
    normalized = unicodedata.normalize("NFC", text)
    index = 0
    length = len(normalized)
    while index < length:
        char = normalized[index]
        if (
            _is_regional_indicator(char)
            and index + 1 < length
            and _is_regional_indicator(normalized[index + 1])
        ):
            yield normalized[index : index + 2]
            index += 2
            continue
        if not _is_emoji_base(char):
            index += 1
            continue

        end = index + 1
        while end < length:
            current = normalized[end]
            if _is_emoji_modifier(current) or _is_variation_selector(current):
                end += 1
                continue
            if (
                current == "\u200d"
                and end + 1 < length
                and _is_emoji_base(normalized[end + 1])
            ):
                end += 2
                while end < length and (
                    _is_variation_selector(normalized[end])
                    or _is_emoji_modifier(normalized[end])
                ):
                    end += 1
                continue
            break
        yield normalized[index:end]
        index = end


def _is_emoji_base(char: str) -> bool:
    code = ord(char)
    return (
        0x1F000 <= code <= 0x1FAFF
        or 0x2600 <= code <= 0x27BF
        or 0x2B00 <= code <= 0x2BFF
    )


def _is_emoji_modifier(char: str) -> bool:
    return 0x1F3FB <= ord(char) <= 0x1F3FF


def _is_variation_selector(char: str) -> bool:
    return ord(char) in (0xFE0E, 0xFE0F)


def _is_regional_indicator(char: str) -> bool:
    return 0x1F1E6 <= ord(char) <= 0x1F1FF
