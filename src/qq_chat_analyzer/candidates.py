"""Data models for Smart Profile candidate discovery."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Candidate:
    """A suspected low-value target discovered by statistical analysis."""

    target: str
    candidate_type: str
    score: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
