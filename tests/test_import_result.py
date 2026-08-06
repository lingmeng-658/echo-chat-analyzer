"""Contract tests for the ImportResult domain model."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import ImportResult


def test_import_result_preserves_fields() -> None:
    result = ImportResult(
        platform="wechat",
        message_count=120,
        valid_text_count=98,
        warnings=("one file skipped",),
        format="detailed-json",
    )

    assert result.platform == "wechat"
    assert result.message_count == 120
    assert result.valid_text_count == 98
    assert result.warnings == ("one file skipped",)
    assert result.format == "detailed-json"


def test_import_result_warnings_default_to_empty_tuple() -> None:
    result = ImportResult(
        platform="qq",
        message_count=0,
        valid_text_count=0,
    )

    assert result.warnings == ()
    assert result.format is None
