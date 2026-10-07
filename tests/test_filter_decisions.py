"""Tests for Smart Profile filter decision data models."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.filter_decisions import FilterDecision


def test_filter_decision_metadata_is_not_shared_between_instances() -> None:
    first = FilterDecision(
        target="虚构模板甲",
        target_type="template",
        action="review",
        confidence=0.75,
        reason="template_candidate",
        source="auto",
    )
    second = FilterDecision(
        target="虚构模板乙",
        target_type="template",
        action="review",
        confidence=0.72,
        reason="template_candidate",
        source="auto",
    )

    first.metadata["matched_message_count"] = 8

    assert first.metadata == {"matched_message_count": 8}
    assert second.metadata == {}
