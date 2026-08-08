"""Source, session, and time-range selection page.

This page owns no business logic. It renders whatever
:class:`~qq_chat_analyzer.application.facade.ChatAnalyzerFacade` reports and
turns user gestures into facade calls. It never touches a provider, a parser,
or a database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..application.facade import AnalysisConfig, ChatSource
from .workers import submit


SESSION_ID_ROLE = Qt.ItemDataRole.UserRole
SOURCE_ROLE = Qt.ItemDataRole.UserRole + 1

_SELECT_SOURCE_HINT = "\u8bf7\u5148\u9009\u62e9\u6570\u636e\u6765\u6e90\u3002"
_LOADING_SESSIONS = "\u6b63\u5728\u52a0\u8f7d\u4f1a\u8bdd\u5217\u8868..."
_NO_SESSIONS = "\u8be5\u6765\u6e90\u6ca1\u6709\u53ef\u5206\u6790\u7684\u4f1a\u8bdd\u3002"
_LOCAL_FILE_HINT = (
    "\u672c\u5730\u6587\u4ef6\u6a21\u5f0f\uff1a\u8bf7\u9009\u62e9\u4e00\u4e2a"
    "\u5bfc\u51fa\u6587\u4ef6\u3002"
)
_ANALYZING = "\u6b63\u5728\u5206\u6790\uff0c\u8bf7\u7a0d\u5019..."


class AnalysisPage(QWidget):
    """Let the user pick a source, a session, and a time range."""

    analysis_started = Signal()
    analysis_succeeded = Signal(object)
    analysis_failed = Signal(str, str)
    status_changed = Signal(str)

    def __init__(
        self,
        facade: Any,
        parent: QWidget | None = None,
        executor: Any = None,
    ) -> None:
        super().__init__(parent)
        self._facade = facade
        self._executor = executor or submit
        self._selected_source: ChatSource | None = None
        self._selected_file: Path | None = None
        self._source_buttons: dict[ChatSource, QPushButton] = {}

        self._build_ui()
        self.refresh_sources()

    # ------------------------------------------------------------------ setup

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._source_box = QGroupBox("\u6570\u636e\u6765\u6e90")
        self._source_layout = QHBoxLayout(self._source_box)
        layout.addWidget(self._source_box)

        self._file_button = QPushButton("\u9009\u62e9\u6587\u4ef6...")
        self._file_button.setVisible(False)
        self._file_button.clicked.connect(self._choose_file)
        self._file_label = QLabel("")
        self._file_label.setVisible(False)
        file_row = QHBoxLayout()
        file_row.addWidget(self._file_button)
        file_row.addWidget(self._file_label, stretch=1)
        layout.addLayout(file_row)

        session_box = QGroupBox("\u4f1a\u8bdd")
        session_layout = QVBoxLayout(session_box)
        self._session_list = QListWidget()
        self._session_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._session_list.itemSelectionChanged.connect(
            self._update_analyze_enabled
        )
        session_layout.addWidget(self._session_list)
        layout.addWidget(session_box, stretch=1)

        range_box = QGroupBox("\u65f6\u95f4\u8303\u56f4")
        range_layout = QFormLayout(range_box)
        self._start_enabled = QCheckBox("\u542f\u7528\u5f00\u59cb\u65f6\u95f4")
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setEnabled(False)
        self._start_enabled.toggled.connect(self._start_date.setEnabled)
        self._end_enabled = QCheckBox("\u542f\u7528\u7ed3\u675f\u65f6\u95f4")
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setEnabled(False)
        self._end_enabled.toggled.connect(self._end_date.setEnabled)
        range_layout.addRow(self._start_enabled, self._start_date)
        range_layout.addRow(self._end_enabled, self._end_date)
        layout.addWidget(range_box)

        self._analyze_button = QPushButton("\u5f00\u59cb\u5206\u6790")
        self._analyze_button.setEnabled(False)
        self._analyze_button.clicked.connect(self.start_analysis)
        layout.addWidget(self._analyze_button)

        self._hint_label = QLabel(_SELECT_SOURCE_HINT)
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)

    # ----------------------------------------------------------- source logic

    def refresh_sources(self) -> None:
        """Rebuild the source buttons from what the facade reports."""
        for button in self._source_buttons.values():
            self._source_layout.removeWidget(button)
            button.deleteLater()
        self._source_buttons.clear()

        for info in self._facade.list_sources():
            button = QPushButton(info.display_name)
            button.setCheckable(True)
            button.setEnabled(bool(info.available))
            if not info.available and info.description:
                button.setToolTip(info.description)
            button.clicked.connect(
                lambda _checked=False, source=info.source: self.select_source(
                    source
                )
            )
            self._source_layout.addWidget(button)
            self._source_buttons[info.source] = button

    def select_source(self, source: ChatSource) -> None:
        """Select one source and load whatever it offers."""
        self._selected_source = source
        self._selected_file = None
        self._file_label.setText("")

        for candidate, button in self._source_buttons.items():
            button.setChecked(candidate == source)

        is_local = source == ChatSource.LOCAL_FILE
        self._file_button.setVisible(is_local)
        self._file_label.setVisible(is_local)
        self._session_list.clear()

        if is_local:
            self._hint_label.setText(_LOCAL_FILE_HINT)
            self._update_analyze_enabled()
            return

        self._hint_label.setText(_LOADING_SESSIONS)
        self.status_changed.emit(_LOADING_SESSIONS)
        self._load_sessions(source)

    def _load_sessions(self, source: ChatSource) -> None:
        self._executor(
            lambda: self._facade.list_sessions(source),
            on_success=lambda sessions: self._populate_sessions(sessions),
            on_error=self._handle_error,
        )

    def _populate_sessions(self, sessions: Any) -> None:
        """Fill the list with sessions, keeping ids out of the visible text."""
        self._session_list.clear()

        for session in sessions or ():
            item = QListWidgetItem(session.display_name)
            item.setData(SESSION_ID_ROLE, session.session_id)
            item.setData(SOURCE_ROLE, session.source)
            if session.message_count is not None:
                item.setToolTip(
                    f"\u6d88\u606f\u6570\uff1a{session.message_count}"
                )
            self._session_list.addItem(item)

        count = self._session_list.count()
        self._hint_label.setText(
            _NO_SESSIONS
            if count == 0
            else f"\u5171 {count} \u4e2a\u4f1a\u8bdd\u3002"
        )
        self.status_changed.emit(self._hint_label.text())
        self._update_analyze_enabled()

    # ------------------------------------------------------------- file logic

    def _choose_file(self) -> None:  # pragma: no cover - needs a real dialog
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "\u9009\u62e9\u804a\u5929\u5bfc\u51fa\u6587\u4ef6",
            "",
            "Chat exports (*.json *.jsonl);;All files (*)",
        )
        if selected:
            self.set_selected_file(Path(selected))

    def set_selected_file(self, path: Path) -> None:
        """Record the chosen local file. Split out so tests can call it."""
        self._selected_file = Path(path)
        self._file_label.setText(self._selected_file.name)
        self._update_analyze_enabled()

    # --------------------------------------------------------- analysis logic

    def build_config(self) -> AnalysisConfig:
        """Translate the widgets into a facade config."""
        return AnalysisConfig(
            start_time=(
                self._start_date.date().toString("yyyy-MM-dd")
                if self._start_enabled.isChecked()
                else None
            ),
            end_time=(
                self._end_date.date().toString("yyyy-MM-dd")
                if self._end_enabled.isChecked()
                else None
            ),
        )

    def selected_session_id(self) -> str | None:
        """Return the id behind the selected row, never its label."""
        item = self._session_list.currentItem()
        if item is None:
            return None
        return item.data(SESSION_ID_ROLE)

    def start_analysis(self) -> None:
        """Dispatch to the facade, choosing file or session mode."""
        source = self._selected_source
        if source is None:
            return

        config = self.build_config()

        if source == ChatSource.LOCAL_FILE:
            if self._selected_file is None:
                return
            path = self._selected_file
            operation = lambda: self._facade.analyze_file(path, config)
        else:
            session_id = self.selected_session_id()
            if not session_id:
                return
            operation = lambda: self._facade.analyze_session(
                source,
                session_id,
                config,
            )

        self._set_busy(True)
        self.analysis_started.emit()
        self.status_changed.emit(_ANALYZING)
        self._executor(
            operation,
            on_success=self._handle_success,
            on_error=self._handle_error,
            on_finished=lambda: self._set_busy(False),
        )

    def _handle_success(self, outcome: Any) -> None:
        self.analysis_succeeded.emit(outcome)

    def _handle_error(self, code: str, message: str) -> None:
        self._hint_label.setText(message)
        self.analysis_failed.emit(code, message)

    def _set_busy(self, busy: bool) -> None:
        self._analyze_button.setEnabled(not busy)
        if not busy:
            self._update_analyze_enabled()

    def _update_analyze_enabled(self) -> None:
        source = self._selected_source
        if source is None:
            self._analyze_button.setEnabled(False)
            return
        if source == ChatSource.LOCAL_FILE:
            self._analyze_button.setEnabled(self._selected_file is not None)
            return
        self._analyze_button.setEnabled(
            self._session_list.currentItem() is not None
        )