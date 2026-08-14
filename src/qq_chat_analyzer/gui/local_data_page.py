"""Local data management page: analysis history and chat data snapshots."""

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
_SNAPSHOT_STATE_DISPLAY = {
    "available": "可用",
    "removed": "已删除",
}
_UNKNOWN_SESSION_NAME = "未知会话"
_LOADING_STATUS = "正在读取本地数据..."
_UPDATED_STATUS = "本地数据已更新。"


class LocalDataPage(QWidget):
    """Show analysis history and manage chat data snapshots.

    This page owns no storage logic: it only reads view models through the
    facade and renders state, errors, and empty states.
    """

    def __init__(
        self,
        facade: Any,
        parent: QWidget | None = None,
        executor: Any = None,
        confirm_delete: Callable[[], bool] | None = None,
        confirm_clear_history: Callable[[], bool] | None = None,
        confirm_clear_snapshots: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._facade = facade
        self._executor = executor or submit
        self._confirm_delete = confirm_delete
        self._confirm_clear_history = confirm_clear_history
        self._confirm_clear_snapshots = confirm_clear_snapshots
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

        snapshot_box = QGroupBox("数据快照")
        snapshot_layout = QVBoxLayout(snapshot_box)
        self._snapshot_empty_label = QLabel("暂无快照")
        self._snapshot_empty_label.setStyleSheet(EMPTY_TEXT_STYLE)
        snapshot_layout.addWidget(self._snapshot_empty_label)
        self._snapshot_table = QTableWidget(0, 5)
        self._snapshot_table.setHorizontalHeaderLabels(
            ["时间", "会话", "消息数", "大小", "状态"]
        )
        self._snapshot_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._snapshot_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._snapshot_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._snapshot_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._snapshot_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        for column, width in enumerate((160, 240, 80, 100, 90)):
            self._snapshot_table.setColumnWidth(column, width)
        snapshot_layout.addWidget(self._snapshot_table)

        snapshot_actions = QHBoxLayout()
        self._usage_label = QLabel("快照占用空间：0 B")
        snapshot_actions.addWidget(self._usage_label)
        snapshot_actions.addStretch(1)
        self._delete_snapshot_button = QPushButton("删除所选快照")
        self._delete_snapshot_button.setMinimumHeight(34)
        self._delete_snapshot_button.clicked.connect(self._delete_selected_snapshot)
        snapshot_actions.addWidget(self._delete_snapshot_button)
        self._delete_all_snapshot_button = QPushButton("删除全部快照")
        self._delete_all_snapshot_button.setMinimumHeight(34)
        self._delete_all_snapshot_button.clicked.connect(self._delete_all_snapshots)
        snapshot_actions.addWidget(self._delete_all_snapshot_button)
        snapshot_layout.addLayout(snapshot_actions)
        layout.addWidget(snapshot_box, stretch=1)

        self._back_button = QPushButton("返回首页")
        self._back_button.setMinimumWidth(160)
        self._back_button.setMinimumHeight(34)
        self._back_button.clicked.connect(self._on_back_clicked)
        layout.addWidget(self._back_button, alignment=Qt.AlignmentFlag.AlignLeft)

    # ---------------------------------------------------------------- public API

    def refresh(self) -> None:
        """Reload history, snapshots, and storage usage through the facade."""
        self._status_label.setText(_LOADING_STATUS)
        self._executor(
            lambda: (
                self._facade.list_analysis_history(),
                self._facade.list_snapshots(),
                self._facade.get_snapshot_storage_usage(),
            ),
            on_success=self._render_data,
            on_error=self._show_error,
        )

    def selected_snapshot_ids(self) -> list[str]:
        """Return snapshot ids behind the selected rows, in row order."""
        snapshot_ids: list[str] = []
        seen: set[str] = set()
        for item in self._snapshot_table.selectedItems():
            if item.column() != 0:
                continue
            snapshot_id = item.data(Qt.ItemDataRole.UserRole)
            if snapshot_id is not None and snapshot_id not in seen:
                seen.add(snapshot_id)
                snapshot_ids.append(snapshot_id)
        return snapshot_ids

    def selected_snapshot_id(self) -> str | None:
        """Return the first selected snapshot id, if any."""
        snapshot_ids = self.selected_snapshot_ids()
        return snapshot_ids[0] if snapshot_ids else None

    # ---------------------------------------------------------------- internals

    def _render_data(self, result: Any) -> None:
        history, snapshots, usage = result
        self._render_history(history or ())
        self._render_snapshots(snapshots or ())
        self._usage_label.setText(
            f"快照占用空间：{_format_bytes(int(usage or 0))}"
        )
        self._status_label.setText(_UPDATED_STATUS)

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

    def _render_snapshots(self, snapshots: Any) -> None:
        items = [
            snapshot
            for snapshot in snapshots
            if not _snapshot_is_removed(snapshot)
        ]
        self._snapshot_table.setRowCount(len(items))
        for row, snapshot in enumerate(items):
            values = (
                _format_datetime(getattr(snapshot, "acquired_at", None)),
                getattr(snapshot, "session_name", "") or _UNKNOWN_SESSION_NAME,
                str(getattr(snapshot, "message_count", 0)),
                _format_bytes(getattr(snapshot, "data_size_bytes", 0)),
                _snapshot_state_display(
                    getattr(snapshot, "payload_state", None)
                ),
            )
            for column, value in enumerate(values):
                item = _readonly_item(value)
                if column == 0:
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        getattr(snapshot, "id", None),
                    )
                self._snapshot_table.setItem(row, column, item)
        self._snapshot_empty_label.setVisible(len(items) == 0)
        self._snapshot_table.setVisible(len(items) > 0)

    def _delete_selected_snapshot(self) -> None:
        snapshot_ids = self.selected_snapshot_ids()
        if not snapshot_ids:
            self._status_label.setText("请先选择要删除的快照。")
            return
        if not self._ask_delete_confirmation():
            return
        self._status_label.setText("正在删除所选快照...")
        self._executor(
            lambda: self._remove_snapshot_ids(snapshot_ids),
            on_success=lambda _removed: self.refresh(),
            on_error=self._show_error,
        )

    def _remove_snapshot_ids(self, snapshot_ids: list[str]) -> list[Any]:
        """Remove selected snapshots one at a time through the facade."""
        removed = []
        for snapshot_id in snapshot_ids:
            removed.append(self._facade.remove_snapshot(snapshot_id))
        return removed

    def _delete_all_snapshots(self) -> None:
        """Remove every snapshot payload after user confirmation."""
        if not self._ask_clear_snapshots_confirmation():
            return
        self._status_label.setText("正在删除全部快照...")
        self._executor(
            self._facade.remove_all_snapshots,
            on_success=lambda _count: self.refresh(),
            on_error=self._show_error,
        )

    def _ask_clear_snapshots_confirmation(self) -> bool:
        """Return whether the user confirmed deleting every snapshot."""
        if self._confirm_clear_snapshots is not None:
            return bool(self._confirm_clear_snapshots())
        box = _clear_snapshots_confirmation_dialog(self)
        box.exec()
        delete_button = next(
            (button for button in box.buttons() if button.text() == "删除"),
            None,
        )
        return box.clickedButton() is delete_button

    def _ask_delete_confirmation(self) -> bool:
        """Return whether the user confirmed the selected snapshot deletion."""
        if self._confirm_delete is not None:
            return bool(self._confirm_delete())
        box = _delete_confirmation_dialog(self)
        box.exec()
        delete_button = next(
            (button for button in box.buttons() if button.text() == "删除"),
            None,
        )
        return box.clickedButton() is delete_button

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


def _delete_confirmation_dialog(
    parent: QWidget | None = None,
) -> QMessageBox:
    """Build the snapshot deletion confirmation dialog."""
    box = QMessageBox(parent)
    box.setWindowTitle("确认删除")
    box.setText("确定要删除所选快照吗？\n删除后将无法恢复。")
    delete_button = box.addButton("删除", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(delete_button)
    return box


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


def _clear_snapshots_confirmation_dialog(
    parent: QWidget | None = None,
) -> QMessageBox:
    """Build the delete-all-snapshots confirmation dialog."""
    box = QMessageBox(parent)
    box.setWindowTitle("确认删除")
    box.setText("确定删除全部数据快照吗？删除后将无法恢复。")
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


def _snapshot_state_display(value: Any) -> str:
    if value is None:
        return "可用"
    text = getattr(value, "value", value)
    return _SNAPSHOT_STATE_DISPLAY.get(str(text), str(text))


def _snapshot_is_removed(snapshot: Any) -> bool:
    state = getattr(snapshot, "payload_state", None)
    text = getattr(state, "value", state)
    return str(text) == "removed"


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M")
    if value is None:
        return "-"
    return str(value)


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"