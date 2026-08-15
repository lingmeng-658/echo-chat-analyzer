"""Detect high-confidence repetitive message noise without filtering it."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..analysis.timestamps import to_epoch_seconds
from ..candidates import Candidate
from ..message import ChatMessage


MIN_SINGLE_CHARACTER_REPETITIONS = 6
MIN_FRAGMENT_REPETITIONS = 3
MIN_REPEATED_FRAGMENT_TEXT_LENGTH = 8
MAX_REPEATED_FRAGMENT_LENGTH = 12
MIN_BURST_REPETITIONS = 3
BURST_WINDOW_SECONDS = 60
MAX_EXAMPLES = 3


@dataclass(slots=True)
class _BurstRun:
    sender: str
    text: str
    start_timestamp: int
    last_timestamp: int
    messages: list[ChatMessage]


def detect_noise_candidates(
    messages: Iterable[ChatMessage],
) -> list[Candidate]:
    """Return high-confidence repetition candidates without filtering input."""
    message_list = list(messages)
    candidates = [
        *_detect_message_internal_noise(message_list),
        *_detect_sender_burst_noise(message_list),
    ]
    return candidates


def _detect_message_internal_noise(
    messages: list[ChatMessage],
) -> list[Candidate]:
    groups: dict[tuple[str, str], list[ChatMessage]] = {}

    for message in messages:
        text = _normalize_text(message.text)
        if not text:
            continue

        if _is_single_character_repeat(text):
            key = ("noise_single_character_repeat", text)
        else:
            fragment = _repeated_fragment(text)
            if fragment is None:
                continue
            key = ("noise_repeated_fragment", text)
        groups.setdefault(key, []).append(message)

    candidates: list[Candidate] = []
    for (candidate_type, text), matched_messages in groups.items():
        if candidate_type == "noise_single_character_repeat":
            reasons = ["single_character_repeated"]
            metadata: dict[str, object] = {
                "rule": "single_character_repeat",
                "character": text[0],
                "repeat_count": len(text),
            }
        else:
            fragment = _repeated_fragment(text)
            if fragment is None:
                continue
            reasons = ["message_fragment_repeated"]
            metadata = {
                "rule": "repeated_fragment",
                "fragment": fragment,
                "repeat_count": len(text) // len(fragment),
            }
        metadata.update(
            {
                "matched_message_count": len(matched_messages),
                "examples": [
                    message.text for message in matched_messages[:MAX_EXAMPLES]
                ],
            }
        )
        candidates.append(
            Candidate(
                target=text,
                candidate_type=candidate_type,
                score=1.0,
                reasons=reasons,
                metadata=metadata,
            )
        )
    return candidates


def _detect_sender_burst_noise(
    messages: list[ChatMessage],
) -> list[Candidate]:
    completed_runs: list[_BurstRun] = []
    current_run: _BurstRun | None = None

    for message in messages:
        text = _normalize_text(message.text)
        timestamp = to_epoch_seconds(message.timestamp)
        if not text or timestamp is None:
            current_run = _finish_run(current_run, completed_runs)
            continue

        continues_run = (
            current_run is not None
            and current_run.sender == message.sender
            and current_run.text == text
            and 0 <= timestamp - current_run.last_timestamp <= BURST_WINDOW_SECONDS
            and timestamp - current_run.start_timestamp <= BURST_WINDOW_SECONDS
        )
        if continues_run:
            current_run.last_timestamp = timestamp
            current_run.messages.append(message)
            continue

        current_run = _finish_run(current_run, completed_runs)
        current_run = _BurstRun(
            sender=message.sender,
            text=text,
            start_timestamp=timestamp,
            last_timestamp=timestamp,
            messages=[message],
        )

    _finish_run(current_run, completed_runs)

    candidates: list[Candidate] = []
    for run in completed_runs:
        candidates.append(
            Candidate(
                target=run.text,
                candidate_type="noise_sender_burst_repeat",
                score=1.0,
                reasons=["same_sender_short_interval_repeat"],
                metadata={
                    "rule": "sender_burst_repeat",
                    "sender": run.sender,
                    "repeat_count": len(run.messages),
                    "window_seconds": run.last_timestamp - run.start_timestamp,
                    "examples": [
                        message.text for message in run.messages[:MAX_EXAMPLES]
                    ],
                },
            )
        )
    return candidates


def _finish_run(
    run: _BurstRun | None,
    completed_runs: list[_BurstRun],
) -> None:
    if run is not None and len(run.messages) >= MIN_BURST_REPETITIONS:
        completed_runs.append(run)
    return None


def _normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(text.split()).strip()


def _is_single_character_repeat(text: str) -> bool:
    return (
        len(text) >= MIN_SINGLE_CHARACTER_REPETITIONS
        and len(set(text)) == 1
    )


def _repeated_fragment(text: str) -> str | None:
    if len(text) < MIN_REPEATED_FRAGMENT_TEXT_LENGTH:
        return None

    upper_bound = min(MAX_REPEATED_FRAGMENT_LENGTH, len(text) // 3)
    for fragment_length in range(2, upper_bound + 1):
        if len(text) % fragment_length != 0:
            continue
        fragment = text[:fragment_length]
        repeat_count = len(text) // fragment_length
        if (
            repeat_count >= MIN_FRAGMENT_REPETITIONS
            and fragment * repeat_count == text
        ):
            return fragment
    return None
