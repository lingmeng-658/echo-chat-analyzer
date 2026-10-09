"""Structured analysis phases published by the facade during one run.

A presentation caller needs to know *what* an analysis run is doing, not which
Chinese status sentence was emitted at which moment.  These phases are that
stable, text-independent signal: a caller animates on an enum member instead of
inferring a stage from progress wording or elapsed time.

The module is deliberately tiny and dependency-free so a PySide6 caller can
import it without pulling in providers, the analysis core or the GUI.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum


class AnalysisPhase(str, Enum):
    """One structured stage of a single ``analyze_session`` run.

    Both phases are published at most once per run, in this order, and the
    second one is only published after the source acquisition succeeded.
    """

    #: The run is about to read chat messages from the selected source.
    READING = "reading"
    #: Acquisition succeeded; import, filtering, analysis and HTML report follow.
    ANALYZING_REPORT = "analyzing_report"


#: Receiver a caller may inject to observe :class:`AnalysisPhase` transitions.
PhaseCallback = Callable[[AnalysisPhase], None]


__all__ = ["AnalysisPhase", "PhaseCallback"]
