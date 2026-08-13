"""Main window hosting the analysis and dashboard pages."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..resources import default_echo_icon_path
from .analysis_page import AnalysisPage
from .dashboard_page import DashboardPage


WINDOW_TITLE = "余音 Echo"
_READY = "\u5c31\u7eea"
_BACK_LABEL = "\u8fd4\u56de\u9009\u62e9"
_ERROR_TITLE = "\u5206\u6790\u5931\u8d25"
_PREPARING = "\u6b63\u5728\u51c6\u5907..."
_CANCEL_ANALYSIS = "取消分析"

ANALYSIS_PAGE_INDEX = 0
PROCESSING_PAGE_INDEX = 1
DASHBOARD_PAGE_INDEX = 2


class MainWindow(QMainWindow):
    """Own the two pages and route signals between them."""

    def __init__(
        self,
        facade: Any,
        parent: QWidget | None = None,
        executor: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(QIcon(str(default_echo_icon_path())))
        self._facade = facade

        container = QWidget()
        layout = QVBoxLayout(container)

        header = QLabel(WINDOW_TITLE)
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        self.stack = QStackedWidget()
        self.analysis_page = AnalysisPage(facade, executor=executor)
        self.processing_page = QWidget()
        processing_layout = QVBoxLayout(self.processing_page)
        self.processing_status_label = QLabel(_PREPARING)
        self.processing_status_label.setWordWrap(True)
        processing_layout.addWidget(self.processing_status_label)
        self._cancel_analysis_button = QPushButton(_CANCEL_ANALYSIS)
        self._cancel_analysis_button.clicked.connect(self.cancel_analysis)
        processing_layout.addWidget(self._cancel_analysis_button)
        processing_layout.addStretch(1)
        self.dashboard_page = DashboardPage()
        self.stack.addWidget(self.analysis_page)
        self.stack.addWidget(self.processing_page)
        self.stack.addWidget(self.dashboard_page)
        layout.addWidget(self.stack, stretch=1)

        self._back_button = QPushButton(_BACK_LABEL)
        self._back_button.setVisible(False)
        self._back_button.clicked.connect(self.show_analysis_page)
        layout.addWidget(self._back_button)

        self.setCentralWidget(container)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(_READY)

        self.analysis_page.analysis_started.connect(self.show_processing_page)
        self.analysis_page.analysis_succeeded.connect(self.show_outcome)
        self.analysis_page.analysis_failed.connect(self.show_error)
        self.analysis_page.status_changed.connect(self.show_status)

    def closeEvent(self, event: Any) -> None:
        """Clean up QQ processes LCA started before the window closes."""
        shutdown = getattr(self._facade, "shutdown_qq_runtime", None)
        if callable(shutdown):
            threading.Thread(
                target=_best_effort_shutdown,
                args=(shutdown,),
                name="echo-qq-shutdown",
                daemon=False,
            ).start()
        super().closeEvent(event)

    def show_analysis_page(self) -> None:
        """Return to source and session selection."""
        self.stack.setCurrentIndex(ANALYSIS_PAGE_INDEX)
        self._back_button.setVisible(False)

    def show_processing_page(self) -> None:
        """Isolate one active analysis from all source-selection controls."""
        self.processing_status_label.setText(_PREPARING)
        self.stack.setCurrentIndex(PROCESSING_PAGE_INDEX)
        self._back_button.setVisible(False)
        self._cancel_analysis_button.setVisible(True)

    def cancel_analysis(self) -> None:
        """Cancel the page task and return to the stable selection state."""
        self.analysis_page.cancel_analysis()
        self.show_analysis_page()
        self.statusBar().showMessage("分析已取消。")

    def show_status(self, message: str) -> None:
        """Show status globally and mirror it on the active processing page."""
        self.statusBar().showMessage(message)
        if self.stack.currentIndex() == PROCESSING_PAGE_INDEX:
            self.processing_status_label.setText(message)

    def show_outcome(self, outcome: Any) -> None:
        """Render a finished analysis and switch to the dashboard."""
        view = getattr(outcome, "view", outcome)
        self.dashboard_page.render_view(view)
        self.stack.setCurrentIndex(DASHBOARD_PAGE_INDEX)
        self._back_button.setVisible(True)
        history_saved = getattr(outcome, "history_saved", None)
        if history_saved is True:
            status_message = "\u5206\u6790\u5df2\u4fdd\u5b58"
        elif history_saved is False:
            status_message = (
                "\u5206\u6790\u5b8c\u6210\uff0c\u4f46\u5386\u53f2"
                "\u8bb0\u5f55\u4fdd\u5b58\u5931\u8d25\u3002"
            )
        else:
            status_message = "\u5206\u6790\u5b8c\u6210"
        data_acquired_at = getattr(outcome, "data_acquired_at", None)
        if isinstance(data_acquired_at, datetime):
            status_message += (
                " \u00b7 \u6570\u636e\u83b7\u53d6\u65f6\u95f4\uff1a"
                f"{data_acquired_at.isoformat(sep=' ', timespec='minutes')}"
            )
        self.statusBar().showMessage(status_message)

    def show_error(self, code: str, message: str) -> None:
        """Show a user-safe message. Never a traceback."""
        self.show_analysis_page()
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, _ERROR_TITLE, message)


def _best_effort_shutdown(shutdown: Any) -> None:
    """Run owned-process cleanup away from the Qt GUI thread."""
    try:
        shutdown()
    except Exception:
        pass
