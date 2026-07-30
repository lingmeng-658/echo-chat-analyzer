"""Data models for Smart Profile filtering decisions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FilterDecision:
    """A decision describing how a candidate target should be handled."""

    target: str
    target_type: str
    action: str
    confidence: float
    reason: str
    source: str
    metadata: dict[str, object] = field(default_factory=dict)
