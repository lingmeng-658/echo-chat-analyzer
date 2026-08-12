"""Behavior tests for message composition analysis."""

from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _models():
    return importlib.import_module("qq_chat_analyzer.analysis.models")


def _analyzers():
    return importlib.import_module("qq_chat_analyzer.analysis.analyzers")


def _chat_message():
    return importlib.import_module("qq_chat_analyzer.message").ChatMessage


def _message(message_type: str, *, is_system: bool = False):
    return _chat_message()(
        timestamp=1,
        sender="Fictional-Alice",
        message_type=message_type,
        text="fictional text",
        is_system=is_system,
    )


def _counts(report) -> dict[str, int]:
    return {item.category: item.count for item in report.categories}


def test_message_composition_models_are_immutable_dataclasses() -> None:
    models = _models()

    assert dataclasses.is_dataclass(models.MessageCompositionCategory)
    assert dataclasses.is_dataclass(models.MessageCompositionReport)


def test_analyzer_is_exported() -> None:
    assert hasattr(_analyzers(), "MessageCompositionAnalyzer")


def test_maps_message_types_to_display_categories() -> None:
    report = _analyzers().MessageCompositionAnalyzer().analyze(
        [
            _message("text"),
            _message("reply"),
            _message("image"),
            _message("video"),
            _message("file"),
        ]
    )

    assert report.total_count == 5
    assert _counts(report) == {
        "文本": 2,
        "图片": 1,
        "视频": 1,
        "文件": 1,
        "其他": 0,
    }


def test_empty_input_returns_zero_counts() -> None:
    report = _analyzers().MessageCompositionAnalyzer().analyze([])

    assert report.total_count == 0
    assert _counts(report) == {
        "文本": 0,
        "图片": 0,
        "视频": 0,
        "文件": 0,
        "其他": 0,
    }


def test_unknown_message_types_count_as_other() -> None:
    report = _analyzers().MessageCompositionAnalyzer().analyze(
        [_message("voice"), _message("location")]
    )

    assert report.total_count == 2
    assert _counts(report) == {
        "文本": 0,
        "图片": 0,
        "视频": 0,
        "文件": 0,
        "其他": 2,
    }


def test_system_messages_are_not_counted() -> None:
    report = _analyzers().MessageCompositionAnalyzer().analyze(
        [
            _message("text"),
            _message("system"),
            _message("text", is_system=True),
        ]
    )

    assert report.total_count == 1
    assert _counts(report)["文本"] == 1


def test_counts_are_correct_for_mixed_input() -> None:
    report = _analyzers().MessageCompositionAnalyzer().analyze(
        [
            _message("text"),
            _message("image"),
            _message("image"),
            _message("video"),
            _message("file"),
            _message("unknown-xyz"),
        ]
    )

    assert report.total_count == 6
    assert _counts(report) == {
        "文本": 1,
        "图片": 2,
        "视频": 1,
        "文件": 1,
        "其他": 1,
    }


def test_type_matching_is_case_insensitive() -> None:
    report = _analyzers().MessageCompositionAnalyzer().analyze(
        [_message("Image"), _message("TEXT"), _message("Reply")]
    )

    assert report.total_count == 3
    assert _counts(report) == {
        "文本": 2,
        "图片": 1,
        "视频": 0,
        "文件": 0,
        "其他": 0,
    }
