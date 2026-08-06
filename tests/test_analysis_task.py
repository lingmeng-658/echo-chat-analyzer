"""Contract tests for the AnalysisTask domain model."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import AnalysisTask


def test_analysis_task_has_defaults() -> None:
    task = AnalysisTask(task_id="task-001", platform="wechat")

    assert task.conversation_type is None
    assert task.conversation_id is None
    assert task.start_time is None
    assert task.end_time is None
    assert task.analysis_mode == "default"
    assert task.status == "pending"
    assert task.output_directory is None


def test_analysis_task_preserves_fields() -> None:
    task = AnalysisTask(
        task_id="task-002",
        platform="qq",
        conversation_type="group",
        conversation_id="900000000",
        start_time=1767315600,
        end_time=1767402000,
        analysis_mode="topic",
        status="completed",
        output_directory="output/group",
    )

    assert task.task_id == "task-002"
    assert task.platform == "qq"
    assert task.conversation_type == "group"
    assert task.conversation_id == "900000000"
    assert task.start_time == 1767315600
    assert task.end_time == 1767402000
    assert task.analysis_mode == "topic"
    assert task.status == "completed"
    assert task.output_directory == "output/group"


def test_analysis_task_is_frozen_and_uses_slots() -> None:
    task = AnalysisTask(task_id="task-003", platform="qq")

    assert not hasattr(task, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.status = "failed"
