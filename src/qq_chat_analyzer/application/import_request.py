"""Import command for one local chat data source."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ImportRequest:
    """Describe one import operation without task-level concerns."""

    input_path: Path = field(repr=False)
    platform: str | None = None
