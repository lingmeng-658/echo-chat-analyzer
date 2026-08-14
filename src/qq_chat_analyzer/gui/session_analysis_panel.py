"""Shared session list, search, sort, date-range, and analysis controls panel."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..application.facade import AnalysisConfig, AnalysisScopeMode, ChatSource
from .workers import submit


SESSION_ID_ROLE = Qt.ItemDataRole.UserRole
SOURCE_ROLE = Qt.ItemDataRole.UserRole + 1

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.session_analysis_panel")

_SESSION_EMPTY_TITLE = "暂无会话"
_SESSION_EMPTY_DETAIL = "连接数据源后，这里会显示聊天记录"
_SESSION_CONNECTING_TITLE = "正在连接数据源..."
_SESSION_READING_TITLE = "正在读取聊天数据..."
_SESSION_NO_DATA_TITLE = "没有找到可分析的聊天记录"
_NO_MESSAGES_AVAILABLE = "该会话没有可分析消息"
_NO_MATCHING_SESSIONS = "没有匹配的会话。"
_SESSION_SEARCH_PLACEHOLDER = "搜索群名、好友名或显示名称"
_SESSION_SORT_LABEL = "排序"
_SESSION_SORT_RECENT = "最近消息"
_SESSION_SORT_MESSAGE_COUNT = "消息数量"
_SESSION_SORT_NAME = "名称"
_SESSION_SORT_ORDER = (
    (_SESSION_SORT_RECENT, "recent"),
    (_SESSION_SORT_MESSAGE_COUNT, "message_count"),
    (_SESSION_SORT_NAME, "name"),
)
_ANALYZING = "正在准备分析..."
_ANALYSIS_CANCELLED = "分析已取消。"


class SessionAnalysisPanel(QWidget):
    """Reusable session list, search, sort, date-range, and analysis controls.

    The panel owns no QQ/WeChat connection orchestration. Workspaces supply
    sessions through :meth:`populate_sessions` and forward the analysis
    signals this widget emits.
    """

    analysis_started = Signal()
    analysis_succeeded = Signal(object)
    analysis_failed = Signal(str, str)
    status_changed = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._facade: Any = None
        self._executor: Any = submit
        self._analysis_running = False
        self._analysis_task: Any = None
        self._sessions_ready = False
        self._selected_source: ChatSource | None = None
        self._sessions_data: list[Any] = []
        self._message_range: tuple[int, int] | None = None
        self._build_ui()
        self._show_unconnected_session_placeholder()

    # ---------------------------------------------------------------- UI build

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._session_box = QGroupBox("会话列表（0）")
        self._session_box.setVisible(False)
        session_layout = QVBoxLayout(self._session_box)
        self._session_search = QLineEdit()
        self._session_search.setPlaceholderText(_SESSION_SEARCH_PLACEHOLDER)
        self._session_search.setClearButtonEnabled(True)
        self._session_search.textChanged.connect(self._reapply_session_view)
        session_layout.addWidget(self._session_search)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel(_SESSION_SORT_LABEL))
        self._session_sort = QComboBox()
        for label, value in _SESSION_SORT_ORDER:
            self._session_sort.addItem(label, value)
        sort_row.addWidget(self._session_sort, stretch=1)
        session_layout.addLayout(sort_row)

        self._session_list = QListWidget()
        self._session_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._session_list.itemSelectionChanged.connect(
            self._on_session_selection_changed
        )
        self._session_sort.currentIndexChanged.connect(
            self._reapply_session_view
        )
        session_layout.addWidget(self._session_list)
        layout.addWidget(self._session_box, stretch=1)

        self._analysis_range_box = QGroupBox("分析范围")
        self._analysis_range_box.setVisible(False)
        range_layout = QVBoxLayout(self._analysis_range_box)
        range_options = QHBoxLayout()
        self._scope_group = QButtonGroup(self)
        self._scope_all = QRadioButton("全部聊天记录")
        self._scope_last_year = QRadioButton("最近一年")
        self._scope_last_six_months = QRadioButton("最近半年")
        self._scope_custom = QRadioButton("自定义")
        for button in (
            self._scope_all,
            self._scope_last_year,
            self._scope_last_six_months,
            self._scope_custom,
        ):
            self._scope_group.addButton(button)
            range_options.addWidget(button)
        self._scope_all.setChecked(True)
        range_layout.addLayout(range_options)

        self._custom_range_widget = QWidget(self._analysis_range_box)
        custom_range_layout = QFormLayout(self._custom_range_widget)
        self._start_date = QDateEdit()
        self._start_date.setMinimumDate(QDate(1, 1, 1))
        self._start_date.setDate(QDate.currentDate())
        self._start_date.setCalendarPopup(True)
        self._end_date = QDateEdit()
        self._end_date.setMinimumDate(QDate(1, 1, 1))
        self._end_date.setDate(QDate.currentDate())
        self._end_date.setCalendarPopup(True)
        custom_range_layout.addRow("开始日期", self._start_date)
        custom_range_layout.addRow("结束日期", self._end_date)
        self._custom_range_widget.setVisible(False)
        self._scope_custom.toggled.connect(self._on_custom_scope_toggled)
        range_layout.addWidget(self._custom_range_widget)
        layout.addWidget(self._analysis_range_box)

        self._analyze_button = QPushButton("开始分析")
        self._analyze_button.setEnabled(False)
        self._analyze_button.setVisible(False)
        self._analyze_button.clicked.connect(self.start_analysis)
        self._analyze_button.setMinimumHeight(34)
        layout.addWidget(self._analyze_button)

    # ---------------------------------------------------------------- public API

    def configure(
        self,
        facade: Any,
        source: ChatSource,
        executor: Any = None,
    ) -> None:
        """Set the facade, source, and optional executor for this panel."""
        self._facade = facade
        self._selected_source = ChatSource(source)
        if executor is not None:
            self._executor = executor

    def populate_sessions(self, sessions: Any) -> None:
        """Load sessions into the list and make analysis controls ready."""
        self._sessions_data = list(sessions or ())
        self._set_session_controls_ready(True)
        self._reapply_session_view()

    def clear(self) -> None:
        """Clear all session data and restore the unconnected placeholder."""
        self._sessions_data = []
        self._sessions_ready = False
        self._show_unconnected_session_placeholder()

    def set_session_count(self, count: int) -> None:
        """Update the session count in the group box title."""
        self._session_box.setTitle(f"会话列表（{count}）")

    def selected_session_id(self) -> str | None:
        """Return the selected session ID or None."""
        item = self._session_list.currentItem()
        if item is None:
            return None
        return item.data(SESSION_ID_ROLE)

    def build_config(self) -> AnalysisConfig:
        """Translate the widgets into a facade config."""
        if self._scope_last_year.isChecked():
            scope_mode = AnalysisScopeMode.LAST_YEAR
        elif self._scope_last_six_months.isChecked():
            scope_mode = AnalysisScopeMode.LAST_SIX_MONTHS
        elif self._scope_custom.isChecked():
            scope_mode = AnalysisScopeMode.CUSTOM
        else:
            scope_mode = AnalysisScopeMode.ALL
        return AnalysisConfig(
            scope_mode=scope_mode,
            start_time=(
                self._start_date.date().toString("yyyy-MM-dd")
                if scope_mode is AnalysisScopeMode.CUSTOM
                else None
            ),
            end_time=(
                self._end_date.date().toString("yyyy-MM-dd")
                if scope_mode is AnalysisScopeMode.CUSTOM
                else None
            ),
        )

    def start_analysis(self) -> None:
        """Start analysis for the selected session through the facade."""
        if self._analysis_running:
            return
        source = self._selected_source
        if source is None or source == ChatSource.LOCAL_FILE:
            return
        session_id = self.selected_session_id()
        if not session_id:
            return
        item = self._session_list.currentItem()
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        config = self.build_config()
        operation = lambda report: self._facade.analyze_session(
            source,
            session_id,
            config,
            progress=report,
        )
        self._set_busy(True)
        self.analysis_started.emit()
        self.status_changed.emit(_ANALYZING)
        QTimer.singleShot(0, lambda: self._submit_analysis(operation))

    def cancel_analysis(self) -> None:
        """Cancel the active analysis and restore selection controls."""
        if not self._analysis_running:
            return
        cancel = getattr(self._analysis_task, "cancel", None)
        if callable(cancel):
            cancel()
        self._analysis_task = None
        self._set_busy(False)
        self.status_changed.emit(_ANALYSIS_CANCELLED)

    def update_analyze_enabled(self) -> None:
        """Refresh the analyze button state (used by workspaces)."""
        self._update_analyze_enabled()

    def show_connecting_placeholder(self) -> None:
        """Show the connecting state inside the session list region."""
        self._show_session_placeholder(_SESSION_CONNECTING_TITLE)

    def show_reading_placeholder(self) -> None:
        """Show the reading state inside the session list region."""
        self._show_session_placeholder(_SESSION_READING_TITLE)

    def show_disconnected_placeholder(self) -> None:
        """Show the disconnected/empty state inside the session list region."""
        self._show_unconnected_session_placeholder()

    def show_unconnected_placeholder(self) -> None:
        """Show the disconnected/empty state inside the session list region."""
        self._show_unconnected_session_placeholder()

    # ---------------------------------------------------------------- internal

    def _submit_analysis(self, operation: Any) -> None:
        self._analysis_task = self._executor(
            operation,
            on_success=self._handle_success,
            on_error=self._handle_error,
            on_finished=self._finish_analysis,
            on_progress=self._handle_analysis_progress,
        )

    def _handle_analysis_progress(self, message: str) -> None:
        if message:
            self.status_changed.emit(message)

    def _finish_analysis(self) -> None:
        self._analysis_task = None
        self._set_busy(False)

    def _handle_success(self, outcome: Any) -> None:
        self.analysis_succeeded.emit(outcome)

    def _handle_error(self, code: str, message: str) -> None:
        self.analysis_failed.emit(code, message)

    def _set_busy(self, busy: bool) -> None:
        self._analysis_running = busy
        self.setEnabled(not busy)
        self._analyze_button.setEnabled(not busy)
        if not busy:
            self._update_analyze_enabled()

    def _update_analyze_enabled(self) -> None:
        self._update_analysis_controls_visibility()
        source = self._selected_source
        if source is None:
            self._analyze_button.setEnabled(False)
            return
        if source == ChatSource.LOCAL_FILE:
            self._analyze_button.setEnabled(False)
            return
        item = self._session_list.currentItem()
        self._analyze_button.setEnabled(
            item is not None
            and bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
        )

    def _update_analysis_controls_visibility(self) -> None:
        visible = bool(self._sessions_ready)
        self._analysis_range_box.setVisible(visible)
        self._analyze_button.setVisible(visible)

    def _on_session_selection_changed(self) -> None:
        self._update_analyze_enabled()
        self._reset_time_range()
        if self._selected_source in (ChatSource.QQ, ChatSource.WECHAT):
            session_id = self.selected_session_id()
            if session_id:
                self._request_session_time_range(session_id)

    def _reset_time_range(self) -> None:
        self._message_range = None
        self._start_date.setDate(QDate.currentDate())
        self._end_date.setDate(QDate.currentDate())

    def _request_session_time_range(self, session_id: str) -> None:
        facade_method = getattr(
            self._facade,
            "get_session_message_range",
            None,
        )
        if facade_method is None:
            return
        source = self._selected_source
        if source not in (ChatSource.QQ, ChatSource.WECHAT):
            return
        self._executor(
            lambda: facade_method(source, session_id),
            on_success=self._set_message_range,
            on_error=lambda *_: None,
        )

    def _set_message_range(self, message_range: Any) -> None:
        if not isinstance(message_range, (tuple, list)) or len(message_range) != 2:
            return
        self._message_range = (
            int(message_range[0]),
            int(message_range[1]),
        )
        self._apply_time_range_defaults()

    def _apply_time_range_defaults(self) -> None:
        if self._scope_custom.isChecked():
            self._apply_date_default(self._start_date, 0)
            self._apply_date_default(self._end_date, 1)

    def _apply_date_default(
        self,
        edit: QDateEdit,
        index: int,
    ) -> None:
        timestamp = (
            self._message_range[index]
            if self._message_range is not None
            else None
        )
        if timestamp is not None:
            date_text = datetime.fromtimestamp(timestamp).strftime(
                "%Y-%m-%d"
            )
            edit.setDate(QDate.fromString(date_text, "yyyy-MM-dd"))
        else:
            edit.setDate(QDate.currentDate())

    def _on_custom_scope_toggled(self, checked: bool) -> None:
        self._custom_range_widget.setVisible(checked)
        if checked:
            self._apply_date_default(self._start_date, 0)
            self._apply_date_default(self._end_date, 1)

    def _reapply_session_view(self) -> None:
        """Filter and sort the cached sessions for the current controls."""
        query = self._session_search.text().strip().lower()
        sort_mode = self._session_sort.currentData() or _SESSION_SORT_ORDER[0][1]
        indexed = list(enumerate(self._sessions_data))
        filtered = [
            (index, session)
            for index, session in indexed
            if query in session.display_name.lower()
        ]
        if sort_mode == _SESSION_SORT_ORDER[2][1]:
            filtered.sort(
                key=lambda pair: (pair[1].display_name.casefold(), pair[0])
            )
        elif sort_mode == _SESSION_SORT_ORDER[1][1]:
            filtered.sort(
                key=lambda pair: (
                    pair[1].message_count is None,
                    -(pair[1].message_count or 0),
                    pair[0],
                )
            )
        else:
            filtered.sort(key=self._recent_session_key)

        self._session_list.clear()

        for _, session in filtered:
            self._add_session_item(session)

        count = self._session_list.count()
        self._set_session_count(count)
        if count == 0 and self._sessions_data:
            self._show_session_placeholder(
                _NO_MATCHING_SESSIONS,
                session_controls_ready=True,
                session_container_visible=True,
            )
        elif count == 0:
            self._show_session_placeholder(
                _SESSION_NO_DATA_TITLE,
                session_controls_ready=True,
            )
        else:
            self._session_box.setVisible(True)
        self._update_analyze_enabled()

    def _add_session_item(self, session: Any) -> None:
        item = QListWidgetItem(session.display_name)
        item.setData(SESSION_ID_ROLE, session.session_id)
        item.setData(SOURCE_ROLE, session.source)
        if not bool(getattr(session, "message_available", True)):
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            item.setToolTip(
                getattr(session, "unavailable_reason", None)
                or _NO_MESSAGES_AVAILABLE
            )
        elif session.message_count is not None:
            item.setToolTip(f"消息数：{session.message_count}")
        self._session_list.addItem(item)

    @staticmethod
    def _recent_session_key(pair: tuple[int, Any]) -> tuple[int, int, int]:
        index, session = pair
        timestamp = getattr(session, "last_message_time", None)
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
            return (0, -int(timestamp), index)
        return (1, 0, index)

    def _show_session_placeholder(
        self,
        title: str,
        detail: str = "",
        *,
        session_controls_ready: bool = False,
        session_container_visible: bool = False,
    ) -> None:
        """Render a non-interactive state inside the session list region."""
        self._session_box.setVisible(session_container_visible)
        self._set_session_controls_ready(session_controls_ready)
        self._session_list.clear()
        self._set_session_count(0)
        text = f"{title}\n{detail}" if detail else title
        item = QListWidgetItem(text)
        item.setFlags(
            item.flags()
            & ~Qt.ItemFlag.ItemIsEnabled
            & ~Qt.ItemFlag.ItemIsSelectable
        )
        self._session_list.addItem(item)
        self._update_analyze_enabled()

    def _show_disconnected_session_placeholder(self) -> None:
        self._show_unconnected_session_placeholder()

    def _show_unconnected_session_placeholder(self) -> None:
        self._show_session_placeholder(
            _SESSION_EMPTY_TITLE,
            _SESSION_EMPTY_DETAIL,
        )

    def _set_session_count(self, count: int) -> None:
        self._session_box.setTitle(f"会话列表（{count}）")

    def _set_session_controls_ready(self, ready: bool) -> None:
        self._sessions_ready = bool(ready)
        self._session_search.setEnabled(ready)
        self._session_sort.setEnabled(ready)