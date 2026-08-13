"""Main window hosting the analysis and dashboard pages."""

from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
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


WINDOW_TITLE = "余音 Echo"
_BACK_LABEL = "\u8fd4\u56de\u9009\u62e9"
_OPEN_ECHO_LABEL = "\u67e5\u770b Echo"
_ERROR_TITLE = "\u5206\u6790\u5931\u8d25"
_PREPARING = "\u6b63\u5728\u51c6\u5907..."
_CANCEL_ANALYSIS = "取消分析"

ANALYSIS_PAGE_INDEX = 0
PROCESSING_PAGE_INDEX = 1
DASHBOARD_PAGE_INDEX = 2

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.main_window")


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
        self._current_report_path: Path | None = None
        self._report_opener = _open_report_path

        container = QWidget()
        layout = QVBoxLayout(container)

        self.analysis_page = AnalysisPage(facade, executor=executor)
        header_layout = QHBoxLayout()
        self._title_label = QLabel(WINDOW_TITLE)
        self._title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(self._title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.analysis_page._status_label)
        layout.addLayout(header_layout)

        self.stack = QStackedWidget()
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

        self._open_echo_button = QPushButton(_OPEN_ECHO_LABEL)
        self._open_echo_button.setEnabled(False)
        self._open_echo_button.setVisible(False)
        self._open_echo_button.clicked.connect(self.open_echo_report)
        layout.addWidget(self._open_echo_button)

        self._back_button = QPushButton(_BACK_LABEL)
        self._back_button.setVisible(False)
        self._back_button.clicked.connect(self.show_analysis_page)
        layout.addWidget(self._back_button)

        self.setCentralWidget(container)

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
        self._clear_echo_report_entry()

    def show_processing_page(self) -> None:
        """Isolate one active analysis from all source-selection controls."""
        self.processing_status_label.setText(_PREPARING)
        self.stack.setCurrentIndex(PROCESSING_PAGE_INDEX)
        self._back_button.setVisible(False)
        self._clear_echo_report_entry()
        self._cancel_analysis_button.setVisible(True)

    def cancel_analysis(self) -> None:
        """Cancel the page task and return to the stable selection state."""
        self.analysis_page.cancel_analysis()
        self.show_analysis_page()
        self.analysis_page._status_label.setText("分析已取消。")

    def show_status(self, message: str) -> None:
        """Show a compact status in the title row and processing page."""
        self.analysis_page._status_label.setText(message)
        if self.stack.currentIndex() == PROCESSING_PAGE_INDEX:
            self.processing_status_label.setText(message)

    def show_outcome(self, outcome: Any) -> None:
        """Render a finished analysis and switch to the dashboard."""
        view = getattr(outcome, "view", outcome)
        self.dashboard_page.render_view(view)
        self.stack.setCurrentIndex(DASHBOARD_PAGE_INDEX)
        self._back_button.setVisible(True)
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

    def open_echo_report(self) -> None:
        """Open the report from the latest successful outcome."""
        report_path = self._current_report_path
        if report_path is None or not _is_file(report_path):
            self._clear_echo_report_entry()
            return
        package_module = sys.modules.get("qq_chat_analyzer")
        facade_module = sys.modules.get(
            "qq_chat_analyzer.application.facade"
        )
        main_window_module = sys.modules.get(__name__)
        _LOGGER.info(
            "[echo-open diagnostic] runtime sys.executable=%s "
            "qq_chat_analyzer.__file__=%s facade.__file__=%s "
            "main_window.__file__=%s",
            sys.executable,
            getattr(package_module, "__file__", None),
            getattr(facade_module, "__file__", None),
            getattr(main_window_module, "__file__", None),
        )
        resolved_path = Path(report_path).resolve()
        reference_url = QUrl.fromLocalFile(str(resolved_path))
        _LOGGER.info(
            "[echo-open diagnostic] report_path_raw=%s "
            "report_path_resolved=%s report_path_as_posix=%s",
            report_path,
            resolved_path,
            resolved_path.as_posix(),
        )
        _LOGGER.info(
            "[echo-open diagnostic] reference_qurl_toString=%s "
            "reference_qurl_toLocalFile=%s reference_qurl_scheme=%s "
            "reference_qurl_isLocalFile=%s",
            reference_url.toString(),
            reference_url.toLocalFile(),
            reference_url.scheme(),
            reference_url.isLocalFile(),
        )
        _log_report_path_state("before_open", report_path)
        try:
            opened = self._report_opener(report_path)
        except Exception:
            opened = False
        _LOGGER.info("[echo-open diagnostic] openUrl_return=%s", opened)
        _log_report_path_state("after_open", report_path)
        for delay_ms, stage in (
            (1000, "after_1s"),
            (3000, "after_3s"),
            (5000, "after_5s"),
            (10000, "after_10s"),
        ):
            QTimer.singleShot(
                delay_ms,
                lambda path=report_path, label=stage: (
                    _log_report_path_state(label, path)
                ),
            )
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

    def show_error(self, code: str, message: str) -> None:
        """Show a user-safe message. Never a traceback."""
        self.show_analysis_page()
        self.analysis_page._status_label.setText(message)
        QMessageBox.warning(self, _ERROR_TITLE, message)


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


def _log_report_path_state(stage: str, path: Path) -> None:
    """Write report-lifecycle diagnostics without changing GUI behavior."""
    try:
        path_exists = path.exists()
    except OSError:
        path_exists = False
    try:
        parent_exists = path.parent.exists()
    except OSError:
        parent_exists = False
    try:
        resolved_is_file = path.resolve().is_file()
    except OSError:
        resolved_is_file = False
    try:
        file_size = path.stat().st_size if path_exists else None
    except OSError:
        file_size = None
    _LOGGER.info(
        "[echo-open diagnostic] %s path_exists=%s is_file=%s "
        "resolved_is_file=%s parent_exists=%s file_size=%s "
        "file_suffix=%s",
        stage,
        path_exists,
        _is_file(path),
        resolved_is_file,
        parent_exists,
        file_size,
        path.suffix,
    )


def _open_report_path(path: Path) -> bool:
    """Open one local HTML file with the operating system browser."""
    actual_url = QUrl.fromLocalFile(str(path))
    _LOGGER.info(
        "[echo-open diagnostic] actual_qurl_variable=actual_url "
        "actual_qurl_toString=%s actual_qurl_toLocalFile=%s "
        "actual_qurl_scheme=%s actual_qurl_isLocalFile=%s",
        actual_url.toString(),
        actual_url.toLocalFile(),
        actual_url.scheme(),
        actual_url.isLocalFile(),
    )
    return QDesktopServices.openUrl(actual_url)
