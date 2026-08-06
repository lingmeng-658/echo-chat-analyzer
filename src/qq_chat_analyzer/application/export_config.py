"""Privacy-first export selection domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExportConfig:
    """Describe what an export phase should include."""

    include_text: bool = True
    include_avatar: bool = False
    include_image: bool = False
    include_file: bool = False
    include_media: bool = False
