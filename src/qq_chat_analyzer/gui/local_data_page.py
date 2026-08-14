"""Local data management page: analysis history and chat data snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .workers import submit


_SOURCE_DISPLAY = {
    "qq": "QQ",
    "wechat": "微信",
    "local_file": "本地文件",
}
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
    ) -> None:
        super().__init__(parent)
        self._facade = facade
        self._executor = executor or submit
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            "padding: 8px 10px; border-radius: 6px; "
            "background: palette(alternate-base);"
        )
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
        self._history_empty_label.setStyleSheet("color: #666;")
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
        self._history_table.horizontalHeader().setStretchLastSection(True)
        history_layout.addWidget(self._history_table)
        layout.addWidget(history_box, stretch=1)

        snapshot_box = QGroupBox("数据快照")
        snapshot_layout = QVBoxLayout(snapshot_box)
        self._snapshot_empty_label = QLabel("暂无快照")
        self._snapshot_empty_label.setStyleSheet("color: #666;")
        snapshot_layout.addWidget(self._snapshot_empty_label)
        self._snapshot_table = QTableWidget(0, 6)
        self._snapshot_table.setHorizontalHeaderLabels(
            ["时间", "来源", "会话", "消息数", "大小", "状态"]
        )
        self._snapshot_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._snapshot_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._snapshot_table.horizontalHeader().setStretchLastSection(True)
        snapshot_layout.addWidget(self._snapshot_table)

        snapshot_actions = QHBoxLayout()
        self._usage_label = QLabel("快照占用空间：0 B")
        snapshot_actions.addWidget(self._usage_label)
        snapshot_actions.addStretch(1)
        self._delete_snapshot_button = QPushButton("删除所选快照")
        self._delete_snapshot_button.setMinimumHeight(34)
        self._delete_snapshot_button.clicked.connect(self._delete_selected_snapshot)
        snapshot_actions.addWidget(self._delete_snapshot_button)
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

    def selected_snapshot_id(self) -> str | None:
        """Return the snapshot id behind the selected row, if any."""
        row = self._snapshot_table.currentRow()
        if row < 0:
            return None
        item = self._snapshot_table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

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
                getattr(record, "session_name", "") or getattr(
                    record, "session_id", ""
                ) or "-",
                str(getattr(record, "message_count", 0)),
                getattr(record, "analysis_scope", "") or "-",
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
        items = list(snapshots)
        self._snapshot_table.setRowCount(len(items))
        for row, snapshot in enumerate(items):
            values = (
                _format_datetime(getattr(snapshot, "acquired_at", None)),
                _source_display(getattr(snapshot, "source", "")),
                getattr(snapshot, "session_name", "") or getattr(
                    snapshot, "session_id", ""
                ) or "-",
                str(getattr(snapshot, "message_count", 0)),
                _format_bytes(getattr(snapshot, "data_size_bytes", 0)),
                "可用"
                if getattr(snapshot, "payload_state", None) is None
                else str(getattr(snapshot, "payload_state", "")),
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
        snapshot_id = self.selected_snapshot_id()
        if not snapshot_id:
            self._status_label.setText("请先选择要删除的快照。")
            return
        self._status_label.setText("正在删除快照...")
        self._executor(
            lambda: self._facade.remove_snapshot(snapshot_id),
            on_success=lambda _removed: self.refresh(),
            on_error=self._show_error,
        )

    def _show_error(self, code: str, message: str) -> None:
        self._status_label.setText(message)

    def _on_back_clicked(self) -> None:
        main_window = self.window()
        if hasattr(main_window, "show_home_page"):
            main_window.show_home_page()


def _readonly_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _source_display(source: Any) -> str:
    value = getattr(source, "value", source)
    return _SOURCE_DISPLAY.get(str(value), str(value))


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