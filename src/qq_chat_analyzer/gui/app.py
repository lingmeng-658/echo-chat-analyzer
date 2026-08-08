"""Compose the desktop application and its facade.

This is the only place that knows how to build a real facade with real
providers. Keeping it separate means the widgets stay injectable and testable
with stubs.
"""

from __future__ import annotations

import sys
from typing import Any

from ..application.facade import ChatAnalyzerFacade


def build_facade() -> ChatAnalyzerFacade:
    """Create a facade with whatever providers this machine can offer.

    Provider construction is optional by design: a machine without QQ or
    WeChat tooling still gets a working window with those sources disabled.
    """
    from ..application.analysis_service import AnalysisApplicationService

    return ChatAnalyzerFacade(
        qq_service=_optional_qq_service(),
        wechat_service=_optional_wechat_service(),
        analysis_service=AnalysisApplicationService(),
    )


def _optional_qq_service() -> Any:
    try:
        from ..application.qq_export_import_service import (
            QQExportImportService,
        )
        from ..providers import QQChatExporterProvider

        return QQExportImportService(QQChatExporterProvider())
    except Exception:
        return None


def _optional_wechat_service() -> Any:
    try:
        from ..application.wechat_export_import_service import (
            WeChatExportImportService,
        )
        from ..providers import WeChatDatabaseProvider

        return WeChatExportImportService(WeChatDatabaseProvider())
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    """Start the Qt event loop with the main window."""
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication(argv if argv is not None else sys.argv)
    window = MainWindow(build_facade())
    window.resize(960, 720)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())