"""Main window hosting the home, workspace, processing, dashboard, and local data pages."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
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
from .workers import shutdown as shutdown_workers
from .workers import submit


WINDOW_TITLE = "\u4f59\u97f3 Echo"
_HOME_LABEL = "\u9996\u9875"
_BACK_LABEL = "\u8fd4\u56de\u9009\u62e9"
_OPEN_ECHO_LABEL = "\u67e5\u770b Echo"
_OPEN_REPORT_DIRECTORY_LABEL = "\u6253\u5f00\u62a5\u544a\u6240\u5728\u76ee\u5f55"
_GENERATE_SHARE_LABEL = "\u751f\u6210\u5206\u4eab\u56fe\u7247"
_ERROR_TITLE = "\u5206\u6790\u5931\u8d25"
_PREPARING = "\u6b63\u5728\u51c6\u5907..."
_CANCEL_ANALYSIS = "\u53d6\u6d88\u5206\u6790"
_REPORT_DIRECTORY_OPEN_FAILED = "\u65e0\u6cd5\u6253\u5f00\u62a5\u544a\u76ee\u5f55\u3002"
_SHARE_GENERATING = "\u6b63\u5728\u751f\u6210\u5206\u4eab\u56fe\u7247..."
_SHARE_READY = "\u5206\u4eab\u56fe\u7247\u5df2\u751f\u6210"
_SHARE_UNAVAILABLE = "\u6682\u65f6\u6ca1\u6709\u53ef\u751f\u6210\u5206\u4eab\u56fe\u7247\u7684\u5206\u6790\u7ed3\u679c\u3002"
_SHARE_SUBMIT_FAILED = "\u5206\u4eab\u56fe\u7247\u751f\u6210\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.main_window")

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
        directory_opener: Any = None,
        image_opener: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(QIcon(str(default_echo_icon_path())))
        self._facade = facade
        self._executor = executor or submit
        self._current_report_path: Path | None = None
        self._current_report_directory: Path | None = None
        self._current_outcome: Any = None
        self._current_share_image_path: Path | None = None
        self._auto_opened_outcome_key: tuple[int, str] | None = None
        self._report_opener = _open_report_path
        self._directory_opener = directory_opener or _open_directory_path
        self._image_opener = image_opener or _open_image_path
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
        self._open_report_directory_button = QPushButton(
            _OPEN_REPORT_DIRECTORY_LABEL
        )
        self._open_report_directory_button.setEnabled(False)
        self._open_report_directory_button.setVisible(False)
        self._open_report_directory_button.clicked.connect(
            self.open_echo_report_directory
        )
        self._generate_share_button = QPushButton(_GENERATE_SHARE_LABEL)
        self._generate_share_button.setEnabled(False)
        self._generate_share_button.setVisible(False)
        self._generate_share_button.clicked.connect(self.generate_share_image)
        report_actions_layout = QHBoxLayout()
        report_actions_layout.addWidget(self._open_echo_button)
        report_actions_layout.addWidget(self._open_report_directory_button)
        report_actions_layout.addWidget(self._generate_share_button)
        report_actions_layout.addStretch(1)
        layout.addLayout(report_actions_layout)

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
        self._current_outcome = outcome
        _LOGGER.info(
            "[gui] show_outcome report_path=%s report_directory=%s",
            getattr(outcome, "report_path", None),
            getattr(outcome, "report_directory", None),
        )
        self._set_echo_report_path(
            getattr(outcome, "report_path", None),
            getattr(outcome, "report_directory", None),
        )
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
        outcome_key = (
            id(outcome),
            str(getattr(outcome, "report_path", "")),
        )
        if (
            self._current_report_path is not None
            and self._auto_opened_outcome_key != outcome_key
        ):
            _LOGGER.info("[gui] show_outcome opening echo report once")
            self._auto_opened_outcome_key = outcome_key
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
        _LOGGER.info("[gui] open_echo_report path=%s", report_path)
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

    def open_echo_report_directory(self) -> None:
        """Open the directory containing the latest successful report."""
        directory = self._current_report_directory
        if directory is None or not _is_directory(directory):
            self._clear_echo_report_entry()
            return
        try:
            opened = self._directory_opener(directory)
        except Exception:
            opened = False
        if opened is False:
            self.analysis_page._status_label.setText(
                _REPORT_DIRECTORY_OPEN_FAILED
            )

    def generate_share_image(self) -> None:
        """Generate a shareable Echo overview card for the latest outcome."""
        _LOGGER.info("[gui] share button clicked")
        outcome = self._current_outcome
        _LOGGER.info("[gui] outcome exists=%s", outcome is not None)
        generate = getattr(self._facade, "generate_share_image", None)
        if outcome is None or not callable(generate):
            _LOGGER.warning(
                "[gui] Share image requested without a usable outcome or facade "
                "method (outcome=%s, facade_method=%s).",
                outcome is not None,
                callable(generate),
            )
            self.analysis_page._status_label.setText(_SHARE_UNAVAILABLE)
            return
        _LOGGER.info(
            "[gui] Share image generation started for outcome report_directory=%s "
            "echo_view=%s.",
            getattr(outcome, "report_directory", None),
            getattr(outcome, "echo_report_view", None) is not None,
        )
        self.analysis_page._status_label.setText(_SHARE_GENERATING)
        self._generate_share_button.setEnabled(False)
        try:
            self._executor(
                lambda: generate(outcome),
                on_success=self._on_share_image_generated,
                on_error=self._on_share_image_failed,
                on_finished=lambda: self._generate_share_button.setEnabled(True),
            )
        except Exception:
            _LOGGER.exception(
                "Share image worker could not be submitted."
            )
            self._generate_share_button.setEnabled(True)
            self.analysis_page._status_label.setText(_SHARE_SUBMIT_FAILED)

    def _on_share_image_generated(self, image_path: Any) -> None:
        try:
            self._current_share_image_path = Path(image_path).resolve()
        except (OSError, TypeError, ValueError):
            self._current_share_image_path = None
        _LOGGER.info(
            "[gui] success image input=%s resolved=%s",
            image_path,
            self._current_share_image_path,
        )
        self.analysis_page._status_label.setText(_SHARE_READY)
        share_image_exists = (
            self._current_share_image_path is not None
            and _is_file(self._current_share_image_path)
        )
        print(f"[share-open] path={self._current_share_image_path}")
        print(f"[share-open] exists={share_image_exists}")
        if self._current_share_image_path is None:
            return
        if not _is_file(self._current_share_image_path):
            _LOGGER.error(
                "[gui] Share image path does not exist or is not a file: %s.",
                self._current_share_image_path,
            )
            return

        try:
            opened = self._image_opener(self._current_share_image_path)
        except Exception:
            _LOGGER.exception(
                "[gui] Share image was generated but could not be opened: %s.",
                self._current_share_image_path,
            )
        else:
            if opened is False:
                _LOGGER.error(
                    "[gui] Share image opener rejected path: %s.",
                    self._current_share_image_path,
                )

    def _on_share_image_failed(self, code: str, message: str) -> None:
        _LOGGER.warning(
            "[gui] Share image generation failed code=%s message=%s",
            code,
            message,
        )
        self.analysis_page._status_label.setText(message)

    def _set_echo_report_path(
        self,
        report_path: Any,
        report_directory: Any = None,
    ) -> None:
        try:
            candidate = Path(report_path).resolve()
        except (OSError, TypeError, ValueError):
            self._clear_echo_report_entry()
            return
        available = _is_file(candidate)
        self._current_report_path = candidate if available else None
        directory = None
        if available:
            if report_directory is not None:
                try:
                    directory = Path(report_directory).resolve()
                except (OSError, TypeError, ValueError):
                    directory = None
                if directory is not None and not _is_directory(directory):
                    directory = None
            if directory is None:
                directory = candidate.parent
        self._current_report_directory = directory
        self._open_echo_button.setEnabled(available)
        self._open_echo_button.setVisible(available)
        directory_available = directory is not None
        self._open_report_directory_button.setEnabled(directory_available)
        self._open_report_directory_button.setVisible(directory_available)
        self._generate_share_button.setEnabled(available)
        self._generate_share_button.setVisible(False)

    def _clear_echo_report_entry(self) -> None:
        self._current_report_path = None
        self._current_report_directory = None
        self._current_outcome = None
        self._current_share_image_path = None
        self._auto_opened_outcome_key = None
        self._open_echo_button.setEnabled(False)
        self._open_echo_button.setVisible(False)
        self._open_report_directory_button.setEnabled(False)
        self._open_report_directory_button.setVisible(False)
        self._generate_share_button.setEnabled(False)
        self._generate_share_button.setVisible(False)

    # ---------------------------------------------------------------- error handling

    def show_error(self, code: str, message: str) -> None:
        """Show a user-safe message. Never a traceback."""
        self._show_active_workspace_or_analysis_page()
        self.analysis_page._status_label.setText(message)
        QMessageBox.warning(self, _ERROR_TITLE, message)

    # ---------------------------------------------------------------- lifecycle

    def closeEvent(self, event: Any) -> None:
        """Close quickly, cancelling background work without blocking."""
        shutdown_workers()
        shutdown = getattr(self._facade, "shutdown_qq_runtime", None)
        if callable(shutdown):
            threading.Thread(
                target=_best_effort_shutdown,
                args=(shutdown,),
                name="echo-qq-shutdown",
                daemon=True,
            ).start()
        shutdown = getattr(self._facade, "shutdown", None)
        if callable(shutdown):
            threading.Thread(
                target=_best_effort_shutdown,
                args=(shutdown,),
                name="echo-facade-shutdown",
                daemon=True,
            ).start()
        super().closeEvent(event)
        _quit_application()


def _best_effort_shutdown(shutdown: Any) -> None:
    """Run owned-process cleanup away from the Qt GUI thread."""
    try:
        shutdown()
    except Exception:
        pass


def _quit_application() -> None:
    """End the Qt event loop deterministically after the main window closes."""
    app = QApplication.instance()
    if app is not None:
        app.quit()


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _open_local_path(path: Path) -> bool:
    """Open one local file or directory with the operating system."""
    resolved_path = path.resolve()
    if os.name == "nt":
        os.startfile(str(resolved_path))
        return True
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved_path)))


def _open_image_path(path: Path) -> bool:
    """Open one resolved local image with the operating system."""
    resolved_path = path.resolve()
    if not _is_file(resolved_path):
        _LOGGER.error(
            "[gui] Refusing to open missing share image: %s.",
            resolved_path,
        )
        return False
    print(f"[share-open] opening={resolved_path}")
    if os.name == "nt":
        os.startfile(str(resolved_path))
        return True
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved_path)))


def _open_report_path(path: Path) -> bool:
    """Open one local HTML file with the operating system browser."""
    return _open_local_path(path)


def _open_directory_path(path: Path) -> bool:
    """Open one local directory in the operating system file manager."""
    return _open_local_path(path)


def _qq_source() -> Any:
    """Return the ChatSource.QQ value without importing the facade module."""
    from ..application.facade import ChatSource

    return ChatSource.QQ


def _wechat_source() -> Any:
    """Return the ChatSource.WECHAT value without importing the facade module."""
    from ..application.facade import ChatSource

    return ChatSource.WECHAT
