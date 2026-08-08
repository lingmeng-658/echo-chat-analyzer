"""PySide6 desktop layer for the local chat analyzer.

The GUI is a pure consumer of
:class:`~qq_chat_analyzer.application.facade.ChatAnalyzerFacade`. It performs
no parsing, no database access, and no statistics of its own.
"""

from __future__ import annotations


__all__ = [
    "AnalysisPage",
    "DashboardPage",
    "MainWindow",
    "build_facade",
    "main",
]


def __getattr__(name: str):
    """Import widgets lazily so PySide6 is only needed when the GUI is used."""
    if name in {"build_facade", "main"}:
        from . import app

        return getattr(app, name)
    if name == "MainWindow":
        from .main_window import MainWindow

        return MainWindow
    if name == "AnalysisPage":
        from .analysis_page import AnalysisPage

        return AnalysisPage
    if name == "DashboardPage":
        from .dashboard_page import DashboardPage

        return DashboardPage
    raise AttributeError(name)