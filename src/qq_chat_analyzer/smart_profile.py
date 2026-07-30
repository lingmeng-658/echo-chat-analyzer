"""Orchestrate Smart Profile candidate detection and filtering."""

from __future__ import annotations

from collections.abc import Iterable

from .decision_engine import create_filter_decisions
from .detectors import (
    detect_interactive_bot_candidates,
    detect_robot_candidates,
    detect_template_candidates,
)
from .filter_pipeline import FilterPipeline, FilteringResult
from .parser import ParsedMessage


def run_smart_profile(
    messages: Iterable[ParsedMessage],
) -> FilteringResult:
    """Detect candidates, create decisions, and apply explicit filters."""
    message_list = list(messages)
    candidates = [
        *detect_robot_candidates(message_list),
        *detect_template_candidates(message_list),
        *detect_interactive_bot_candidates(message_list),
    ]
    decisions = create_filter_decisions(candidates)
    return FilterPipeline().apply_filter_decisions(
        message_list,
        decisions,
    )
