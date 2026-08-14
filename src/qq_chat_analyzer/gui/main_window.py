"""Main window hosting the home, workspace, processing, dashboard, and local data pages."""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QSizePolicy,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..resources import default_echo_icon_path
from .analysis_page import AnalysisPage
from .dashboard_page import DashboardPage
from .home_page import HomePage
from .local_data_page import LocalDataPage
from .qq_workspace import QQWorkspace
from .theme import WINDOW_TITLE_STYLE
from .wechat_workspace import WeChatWorkspace


WINDOW_TITLE = "\u4f59\u97f3 Echo"
_HOME_LABEL = "\u9996\u9875"
_BACK_LABEL = "\u8fd4\u56de\u9009\u62e9"
_OPEN_ECHO_LABEL = "\u67e5\u770b Echo"
_ERROR_TITLE = "\u5206\u6790\u5931\u8d25"
_PREPARING = "\u6b63\u5728\u51c6\u5907..."
_CANCEL_ANALYSIS = "\u53d6\u6d88\u5206\u6790"

HOME_PAGE_INDEX = 0
QQ_WORKSPACE_INDEX = 1
WECHAT_WORKSPACE_INDEX = 2
PROCESSING_PAGE_INDEX = 3
DASHBOARD_PAGE_INDEX = 4
LOCAL_DATA_PAGE_INDEX = 5
ANALYSIS_PAGE_INDEX = 6  # backward compat


class MainWindow(QMainWindow):
    """Own the pages and route navigation signals between them."""

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
        self._current_report_path: Path | None = None
        self._report_opener = _open_report_path
        self._active_source: str | None = None

        container = QWidget()
        layout = QVBoxLayout(container)

        # Create pages (order matters for stack indices)
        self.home_page = HomePage()
        self.qq_workspace = QQWorkspace(facade, executor=executor)
        self.wechat_workspace = WeChatWorkspace(facade, executor=executor)
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
        self.local_data_page = LocalDataPage(facade, executor=executor)
        self.analysis_page = AnalysisPage(facade, executor=executor)  # backward compat

        # Header row
        header_layout = QHBoxLayout()
        self._home_button = QPushButton(_HOME_LABEL)
        self._home_button.clicked.connect(self.show_home_page)
        self._home_button.setVisible(False)
        header_layout.addWidget(self._home_button)
        self._title_label = QLabel(WINDOW_TITLE)
        self._title_label.setStyleSheet(WINDOW_TITLE_STYLE)
        header_layout.addWidget(self._title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.analysis_page._status_label)
        layout.addLayout(header_layout)

        # Stacked pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self.home_page)          # 0
        self.stack.addWidget(self.qq_workspace)        # 1
        self.stack.addWidget(self.wechat_workspace)    # 2
        self.stack.addWidget(self.processing_page)     # 3
        self.stack.addWidget(self.dashboard_page)      # 4
        self.stack.addWidget(self.local_data_page)     # 5
        self.stack.addWidget(self.analysis_page)       # 6 (backward compat)
        layout.addWidget(self.stack, stretch=1)

        self._open_echo_button = QPushButton(_OPEN_ECHO_LABEL)
        self._open_echo_button.setEnabled(False)
        self._open_echo_button.setVisible(False)
        self._open_echo_button.clicked.connect(self.open_echo_report)
        layout.addWidget(self._open_echo_button)

        self._back_button = QPushButton(_BACK_LABEL)
        self._back_button.setVisible(False)
        self._back_button.clicked.connect(self._on_back_clicked)
        layout.addWidget(self._back_button)

        self.setCentralWidget(container)

        self.setMinimumSize(800, 600)
        self.stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        # Home navigation
        self.home_page.navigate_requested.connect(self._on_navigate_requested)

        # Connect workspace signals
        self.qq_workspace.analysis_started.connect(self.show_processing_page)
        self.qq_workspace.analysis_succeeded.connect(self.show_outcome)
        self.qq_workspace.analysis_failed.connect(self.show_error)
        self.qq_workspace.status_changed.connect(self.show_status)

        self.wechat_workspace.analysis_started.connect(self.show_processing_page)
        self.wechat_workspace.analysis_succeeded.connect(self.show_outcome)
        self.wechat_workspace.analysis_failed.connect(self.show_error)
        self.wechat_workspace.status_changed.connect(self.show_status)

        # Backward compat: keep analysis_page connected
        self.analysis_page.analysis_started.connect(self.show_processing_page)
        self.analysis_page.analysis_succeeded.connect(self.show_outcome)
        self.analysis_page.analysis_failed.connect(self.show_error)
        self.analysis_page.status_changed.connect(self.show_status)

        # Start at home
        self.show_home_page()

    # ---------------------------------------------------------------- navigation

    def show_home_page(self) -> None:
        """Navigate to the home page."""
        self.stack.setCurrentIndex(HOME_PAGE_INDEX)
        self._home_button.setVisible(False)
        self._back_button.setVisible(False)
        self._clear_echo_report_entry()

    def show_qq_workspace(self) -> None:
        """Navigate to the QQ workspace."""
        self.stack.setCurrentIndex(QQ_WORKSPACE_INDEX)
        self._home_button.setVisible(True)
        self._back_button.setVisible(False)
        self._clear_echo_report_entry()
        self.qq_workspace.refresh_connection_status(load_sessions_on_ready=True)

    def show_wechat_workspace(self) -> None:
        """Navigate to the WeChat workspace."""
        self.stack.setCurrentIndex(WECHAT_WORKSPACE_INDEX)
        self._home_button.setVisible(True)
        self._back_button.setVisible(False)
        self._clear_echo_report_entry()
        self.wechat_workspace.refresh_connection_status(load_sessions_on_ready=True)

    def show_analysis_page(self) -> None:
        """Return to the legacy analysis page (backward compat)."""
        self.stack.setCurrentIndex(ANALYSIS_PAGE_INDEX)
        self._home_button.setVisible(True)
        self._back_button.setVisible(False)
        self._clear_echo_report_entry()

    def show_local_data_page(self) -> None:
        """Navigate to the local data management page."""
        self.stack.setCurrentIndex(LOCAL_DATA_PAGE_INDEX)
        self._home_button.setVisible(True)
        self._back_button.setVisible(False)
        self._clear_echo_report_entry()
        self.local_data_page.refresh()

    def show_processing_page(self) -> None:
        """Isolate one active analysis from all selection controls."""
        self.processing_status_label.setText(_PREPARING)
        self.stack.setCurrentIndex(PROCESSING_PAGE_INDEX)
        self._home_button.setVisible(False)
        self._back_button.setVisible(False)
        self._clear_echo_report_entry()
        self._cancel_analysis_button.setVisible(True)

    def _on_navigate_requested(self, intent: str) -> None:
        """Handle home page navigation signals."""
        if intent == "qq":
            self.navigate_to_qq()
        elif intent == "wechat":
            self.navigate_to_wechat()
        elif intent == "local_data":
            self.show_local_data_page()

    def navigate_to_qq(self) -> None:
        """Navigate to the QQ workspace."""
        self._active_source = "qq"
        self.qq_workspace.select_source(_qq_source())
        self.show_qq_workspace()

    def navigate_to_wechat(self) -> None:
        """Navigate to the WeChat workspace."""
        self._active_source = "wechat"
        self.wechat_workspace.select_source(_wechat_source())
        self.show_wechat_workspace()

    def _on_back_clicked(self) -> None:
        """Return to the workspace the user came from, else the analysis page."""
        self._show_active_workspace_or_analysis_page()

    def _show_active_workspace_or_analysis_page(self) -> None:
        """Return to the active workspace, or the legacy page for old flows."""
        if self._active_source == "qq":
            self.show_qq_workspace()
        elif self._active_source == "wechat":
            self.show_wechat_workspace()
        else:
            self.show_analysis_page()

    # ---------------------------------------------------------------- analysis lifecycle

    def cancel_analysis(self) -> None:
        """Cancel the active analysis."""
        self.qq_workspace.cancel_analysis()
        self.wechat_workspace.cancel_analysis()
        self.analysis_page.cancel_analysis()
        self._show_active_workspace_or_analysis_page()
        self.analysis_page._status_label.setText("分析已取消。")





    def show_status(self, message: str) -> None:
        """Show a compact status in the header row and processing page."""
        self.analysis_page._status_label.setText(message)
        if self.stack.currentIndex() == PROCESSING_PAGE_INDEX:
            self.processing_status_label.setText(message)

    def show_outcome(self, outcome: Any) -> None:
        """Finish one analysis, open Echo, and return to the active workspace."""
        self._set_echo_report_path(getattr(outcome, "report_path", None))
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
        self.analysis_page._status_label.setText(status_message)
        if self._current_report_path is not None:
            self.open_echo_report()
        self._return_to_workspace_after_success()

    def _return_to_workspace_after_success(self) -> None:
        """Return to the active workspace without clearing the Echo entry."""
        self._home_button.setVisible(True)
        self._back_button.setVisible(False)
        if self._active_source == "qq":
            self.stack.setCurrentIndex(QQ_WORKSPACE_INDEX)
        elif self._active_source == "wechat":
            self.stack.setCurrentIndex(WECHAT_WORKSPACE_INDEX)
        else:
            self.stack.setCurrentIndex(ANALYSIS_PAGE_INDEX)

    # ---------------------------------------------------------------- echo report

    def open_echo_report(self) -> None:
        """Open the report from the latest successful outcome."""
        report_path = self._current_report_path
        if report_path is None or not _is_file(report_path):
            self._clear_echo_report_entry()
            return
        try:
            opened = self._report_opener(report_path)
        except Exception:
            opened = False
        if opened is False:
            self.analysis_page._status_label.setText(
                "\u65e0\u6cd5\u6253\u5f00 Echo \u62a5\u544a\u3002"
            )

    def _set_echo_report_path(self, report_path: Any) -> None:
        try:
            candidate = Path(report_path).resolve()
        except (OSError, TypeError, ValueError):
            self._clear_echo_report_entry()
            return
        available = _is_file(candidate)
        self._current_report_path = candidate if available else None
        self._open_echo_button.setEnabled(available)
        self._open_echo_button.setVisible(available)

    def _clear_echo_report_entry(self) -> None:
        self._current_report_path = None
        self._open_echo_button.setEnabled(False)
        self._open_echo_button.setVisible(False)

    # ---------------------------------------------------------------- error handling

    def show_error(self, code: str, message: str) -> None:
        """Show a user-safe message. Never a traceback."""
        self._show_active_workspace_or_analysis_page()
        self.analysis_page._status_label.setText(message)
        QMessageBox.warning(self, _ERROR_TITLE, message)

    # ---------------------------------------------------------------- lifecycle

    def closeEvent(self, event: Any) -> None:
        """Clean up QQ processes and transient artifacts before the window closes."""
        shutdown = getattr(self._facade, "shutdown_qq_runtime", None)
        if callable(shutdown):
            threading.Thread(
                target=_best_effort_shutdown,
                args=(shutdown,),
                name="echo-qq-shutdown",
                daemon=False,
            ).start()
        shutdown = getattr(self._facade, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass
        super().closeEvent(event)


def _best_effort_shutdown(shutdown: Any) -> None:
    """Run owned-process cleanup away from the Qt GUI thread."""
    try:
        shutdown()
    except Exception:
        pass


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _open_report_path(path: Path) -> bool:
    """Open one local HTML file with the operating system browser."""
    resolved_path = path.resolve()
    if os.name == "nt":
        os.startfile(str(resolved_path))
        return True
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved_path)))


def _qq_source() -> Any:
    """Return the ChatSource.QQ value without importing the facade module."""
    from ..application.facade import ChatSource

    return ChatSource.QQ


def _wechat_source() -> Any:
    """Return the ChatSource.WECHAT value without importing the facade module."""
    from ..application.facade import ChatSource

    return ChatSource.WECHAT
