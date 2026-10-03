"""Local data management page: Echo analysis history."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import EMPTY_TEXT_STYLE, STATUS_STYLE_BASE
from .workers import submit


_SOURCE_DISPLAY = {
    "qq": "QQ",
    "wechat": "微信",
    "local_file": "本地文件",
}
_SCOPE_DISPLAY = {
    "all": "全部消息",
    "last-six-month": "最近六个月",
    "last_six_months": "最近六个月",
    "last_year": "最近一年",
}
_UNKNOWN_SESSION_NAME = "未知会话"
_LOADING_STATUS = "正在读取本地数据..."


class LocalDataPage(QWidget):
    """Show and clear Echo analysis history.

    This page owns no storage logic: it only reads view models through the
    facade and renders state, errors, and empty states.
    """

    def __init__(
        self,
        facade: Any,
        parent: QWidget | None = None,
        executor: Any = None,
        confirm_clear_history: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._facade = facade
        self._executor = executor or submit
        self._confirm_clear_history = confirm_clear_history
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(STATUS_STYLE_BASE)
        layout.addWidget(self._status_label)

        refresh_row = QHBoxLayout()
        self._refresh_button = QPushButton("刷新")
        self._refresh_button.setMinimumHeight(34)
        self._refresh_button.clicked.connect(self.refresh)
        refresh_row.addWidget(self._refresh_button)
        refresh_row.addStretch(1)
        layout.addLayout(refresh_row)

        history_box = QGroupBox("Echo 历史")
        history_layout = QVBoxLayout(history_box)
        self._history_empty_label = QLabel("暂无历史记录")
        self._history_empty_label.setStyleSheet(EMPTY_TEXT_STYLE)
        history_layout.addWidget(self._history_empty_label)
        self._history_table = QTableWidget(0, 5)
        self._history_table.setHorizontalHeaderLabels(
            ["时间", "来源", "会话", "消息数", "分析范围"]
        )
        self._history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._history_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        for column, width in enumerate((160, 80, 240, 80, 220)):
            self._history_table.setColumnWidth(column, width)
        history_layout.addWidget(self._history_table)

        history_actions = QHBoxLayout()
        self._clear_history_button = QPushButton("删除全部历史")
        self._clear_history_button.setMinimumHeight(34)
        self._clear_history_button.clicked.connect(self._delete_all_history)
        history_actions.addStretch(1)
        history_actions.addWidget(self._clear_history_button)
        history_layout.addLayout(history_actions)
        layout.addWidget(history_box, stretch=1)

        self._back_button = QPushButton("返回首页")
        self._back_button.setMinimumWidth(160)
        self._back_button.setMinimumHeight(34)
        self._back_button.clicked.connect(self._on_back_clicked)
        layout.addWidget(self._back_button, alignment=Qt.AlignmentFlag.AlignLeft)

    # ---------------------------------------------------------------- public API

    def refresh(self) -> None:
        """Reload history through the facade."""
        self._status_label.setText(_LOADING_STATUS)
        self._executor(
            lambda: self._facade.list_analysis_history(),
            on_success=self._render_data,
            on_error=self._show_error,
        )

    # ---------------------------------------------------------------- internals

    def _render_data(self, history: Any) -> None:
        """Render history after a successful refresh."""
        self._render_history(history or ())
        self._status_label.clear()

    def _render_history(self, history: Any) -> None:
        records = list(history)
        self._history_table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = (
                _format_datetime(getattr(record, "created_at", None)),
                _source_display(getattr(record, "source", "")),
                getattr(record, "session_name", "") or _UNKNOWN_SESSION_NAME,
                str(getattr(record, "message_count", 0)),
                _scope_display(
                    getattr(record, "analysis_scope", ""),
                    start=getattr(record, "scope_start", None),
                    end=getattr(record, "scope_end", None),
                ),
            )
            for column, value in enumerate(values):
                self._history_table.setItem(
                    row,
                    column,
                    _readonly_item(value),
                )
        self._history_empty_label.setVisible(len(records) == 0)
        self._history_table.setVisible(len(records) > 0)

    def _delete_all_history(self) -> None:
        """Clear every Echo history record after user confirmation."""
        if not self._ask_clear_history_confirmation():
            return
        self._status_label.setText("正在删除全部历史...")
        self._executor(
            self._facade.clear_analysis_history,
            on_success=lambda _result: self.refresh(),
            on_error=self._show_error,
        )

    def _ask_clear_history_confirmation(self) -> bool:
        """Return whether the user confirmed clearing all Echo history."""
        if self._confirm_clear_history is not None:
            return bool(self._confirm_clear_history())
        box = _clear_history_confirmation_dialog(self)
        box.exec()
        delete_button = next(
            (button for button in box.buttons() if button.text() == "删除"),
            None,
        )
        return box.clickedButton() is delete_button

    def _show_error(self, code: str, message: str) -> None:
        self._status_label.setText(message)

    def _on_back_clicked(self) -> None:
        main_window = self.window()
        if hasattr(main_window, "show_home_page"):
            main_window.show_home_page()


def _clear_history_confirmation_dialog(
    parent: QWidget | None = None,
) -> QMessageBox:
    """Build the clear-all-history confirmation dialog."""
    box = QMessageBox(parent)
    box.setWindowTitle("确认删除")
    box.setText("确定删除全部 Echo 历史记录吗？\n删除后无法恢复。")
    delete_button = box.addButton("删除", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(delete_button)
    return box


def _readonly_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _source_display(source: Any) -> str:
    value = getattr(source, "value", source)
    return _SOURCE_DISPLAY.get(str(value), str(value))


def _scope_display(value: Any, start: Any = None, end: Any = None) -> str:
    text = getattr(value, "value", value)
    key = str(text)
    if key in _SCOPE_DISPLAY:
        return _SCOPE_DISPLAY[key]
    if key == "custom":
        start_text = _format_date(start)
        end_text = _format_date(end)
        if start_text and end_text:
            return f"{start_text} 至 {end_text}"
        return "-"
    return key or "-"


def _format_date(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    text = str(value or "").strip()
    return text[:10] if text else ""


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M")
    if value is None:
        return "-"
    return str(value)
