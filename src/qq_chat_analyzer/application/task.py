"""User-facing analysis task domain model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AnalysisTask:
    """Describe one user analysis request."""

    task_id: str
    platform: str
    conversation_type: str | None = None
    conversation_id: str | None = None
    start_time: int | None = None
    end_time: int | None = None
    analysis_mode: str = "default"
    status: str = "pending"
    output_directory: str | None = field(default=None, repr=False)
