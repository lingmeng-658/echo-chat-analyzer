"""Local data management page: Echo report packages."""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import COLOR_ACCENT_SOFT, COLOR_PAPER, EMPTY_TEXT_STYLE, STATUS_STYLE_BASE
from .workers import submit


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.local_data")


_SOURCE_DISPLAY = {
    "qq": "QQ",
    "wechat": "微信",
}
_KIND_DISPLAY = {"group": "群聊", "private": "私聊", "unknown": "未知类型"}
_SCOPE_DISPLAY = {
    "all": "全部消息",
    "last_six_months": "最近六个月",
    "last_year": "最近一年",
}
_UNKNOWN_SESSION_NAME = "未知会话"
_LOADING_STATUS = "正在读取本地数据..."


class LocalDataPage(QWidget):
    """Show and clear Echo report packages.

    This page owns no storage logic: it only reads view models through the
    facade and renders state, errors, and empty states.
    """

    def __init__(
        self,
        facade: Any,
        parent: QWidget | None = None,
        executor: Any = None,
        confirm_clear_reports: Callable[[], bool] | None = None,
        report_opener: Callable[[Any], bool] | None = None,
        confirm_delete_report: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._facade = facade
        self._executor = executor or submit
        self._confirm_clear_reports = confirm_clear_reports
        self._report_opener = report_opener
        self._confirm_delete_report = confirm_delete_report
        self._reports = ()
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
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索会话名、来源、类型、日期或分析范围")
        self._search_input.setAccessibleName("搜索历史报告")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._apply_search)
        history_layout.addWidget(self._search_input)
        self._history_empty_label = QLabel("暂无报告")
        self._history_empty_label.setStyleSheet(EMPTY_TEXT_STYLE)
        history_layout.addWidget(self._history_empty_label)
        self._issues_label = QLabel("")
        self._issues_label.setWordWrap(True)
        self._issues_label.hide()
        history_layout.addWidget(self._issues_label)
        self._history_table = QTableWidget(0, 5)
        # Hide the native item focus frame while keeping keyboard focus and selection.
        self._history_table.setStyleSheet(
            "QTableWidget { outline: 0; }"
            f"QTableWidget::item:hover:!selected {{ background: {COLOR_PAPER}; }}"
            f"QTableWidget::item:selected:hover {{ background: {COLOR_ACCENT_SOFT}; }}"
        )
        self._history_table.setHorizontalHeaderLabels(
            ["时间", "来源", "会话", "消息数", "分析范围"]
        )
        self._history_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._history_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._history_table.itemSelectionChanged.connect(self._update_open_report_button)
        self._history_table.cellDoubleClicked.connect(
            lambda _row, _column: self._open_selected_report()
        )
        self._history_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        for column, width in enumerate((160, 80, 240, 80, 220)):
            self._history_table.setColumnWidth(column, width)
        history_layout.addWidget(self._history_table)

        history_actions = QHBoxLayout()
        self._open_report_button = QPushButton("打开报告")
        self._open_report_button.setMinimumHeight(34)
        self._open_report_button.setEnabled(False)
        self._open_report_button.clicked.connect(self._open_selected_report)
        self._delete_report_button = QPushButton("删除选中报告")
        self._delete_report_button.setMinimumHeight(34)
        self._delete_report_button.setEnabled(False)
        self._delete_report_button.clicked.connect(self._delete_selected_report)
        self._clear_reports_button = QPushButton("删除全部报告")
        self._clear_reports_button.setMinimumHeight(34)
        self._clear_reports_button.clicked.connect(self._delete_all_reports)
        history_actions.addStretch(1)
        history_actions.addWidget(self._open_report_button)
        history_actions.addWidget(self._delete_report_button)
        history_actions.addWidget(self._clear_reports_button)
        history_layout.addLayout(history_actions)
        layout.addWidget(history_box, stretch=1)

        self._back_button = QPushButton("返回首页")
        self._back_button.setMinimumWidth(160)
        self._back_button.setMinimumHeight(34)
        self._back_button.clicked.connect(self._on_back_clicked)
        layout.addWidget(self._back_button, alignment=Qt.AlignmentFlag.AlignLeft)

    # ---------------------------------------------------------------- public API

    def refresh(self, *, error_message: str = "") -> None:
        """Reload package summaries through the facade."""
        self._history_table.clearSelection()
        self._history_table.setCurrentCell(-1, -1)
        self._status_label.setText(_LOADING_STATUS)
        self._executor(
            lambda: self._facade.list_report_packages(),
            on_success=lambda listing: self._render_data(listing, error_message),
            on_error=self._show_error,
        )

    # ---------------------------------------------------------------- internals

    def _render_data(self, listing: Any, error_message: str = "") -> None:
        _LOGGER.info("Local data rendered reports=%d issues=%d deletion_error=%s",
                     len(listing.reports), len(listing.issues), bool(error_message))
        self._reports = tuple(listing.reports)
        self._apply_search()
        self._issues_label.setText(f"发现 {len(listing.issues)} 个无法读取的 Echo 报告")
        self._issues_label.setVisible(bool(listing.issues))
        self._status_label.setText(error_message)

    def _apply_search(self) -> None:
        """Filter only loaded summaries using their user-facing text."""
        query = self._search_input.text().strip().casefold()
        records = []
        for record in self._reports:
            values = _history_values(record)
            kind = _KIND_DISPLAY.get(getattr(record, "conversation_kind", "unknown"), "未知类型")
            fields = (values[0], values[1], values[2], values[4], kind)
            if not query or any(query in field.casefold() for field in fields):
                records.append(record)
        self._render_history(records)
        self._history_empty_label.setText(
            "没有匹配的报告" if self._reports else "暂无报告"
        )

    def _render_history(self, history: Any) -> None:
        records = list(history)
        self._history_table.clearSelection()
        self._history_table.setCurrentCell(-1, -1)
        self._history_table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = _history_values(record)
            for column, value in enumerate(values):
                item = _readonly_item(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, record.package_name)
                self._history_table.setItem(
                    row,
                    column,
                    item,
                )
        self._history_empty_label.setVisible(len(records) == 0)
        self._history_table.setVisible(len(records) > 0)
        self._update_open_report_button()

    def _selected_package_name(self) -> str | None:
        rows = self._history_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._history_table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _update_open_report_button(self) -> None:
        self._open_report_button.setEnabled(bool(self._selected_package_name()))
        self._delete_report_button.setEnabled(bool(self._selected_package_name()))

    def _open_selected_report(self) -> None:
        package_name = self._selected_package_name()
        if package_name is None:
            return
        self._executor(
            lambda: self._facade.get_report_package_html_path(package_name),
            on_success=self._open_resolved_report,
            on_error=self._show_error,
        )

    def _open_resolved_report(self, path: Any) -> None:
        try:
            opened = self._report_opener(path) if self._report_opener is not None else False
        except Exception:
            opened = False
        self._status_label.setText(
            "" if opened else "无法打开 Echo 报告，请检查系统默认浏览器后重试。"
        )

    def _delete_selected_report(self) -> None:
        package_name = self._selected_package_name()
        if package_name is None:
            return
        if self._confirm_delete_report is not None:
            confirmed = bool(self._confirm_delete_report())
        else:
            box = _delete_report_confirmation_dialog(self)
            box.exec()
            confirmed = box.clickedButton() == next(
                button for button in box.buttons() if button.text() == "删除"
            )
        if not confirmed:
            return
        self._status_label.setText("正在删除选中报告...")
        self._executor(
            lambda: self._facade.delete_report_package(package_name),
            on_success=lambda _result: self.refresh(),
            on_error=lambda code, message: self.refresh(error_message=message),
        )

    def _delete_all_reports(self) -> None:
        """Delete complete Echo report packages after user confirmation."""
        _LOGGER.info("Local data delete-all clicked")
        if not self._ask_clear_reports_confirmation():
            _LOGGER.info("Local data delete-all cancelled")
            return
        _LOGGER.info("Local data delete-all confirmed; submitting package deletion")
        self._status_label.setText("正在删除全部报告...")
        self._executor(
            self._facade.clear_report_packages,
            on_success=lambda _result: self.refresh(),
            on_error=lambda code, message: self.refresh(error_message=message),
        )

    def _ask_clear_reports_confirmation(self) -> bool:
        """Return whether the user confirmed deleting all Echo reports."""
        if self._confirm_clear_reports is not None:
            return bool(self._confirm_clear_reports())
        box = _clear_reports_confirmation_dialog(self)
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


def _delete_report_confirmation_dialog(parent: QWidget | None = None) -> QMessageBox:
    box = QMessageBox(parent)
    box.setWindowTitle("确认删除")
    box.setText("确定删除这份 Echo 报告吗？\n删除后无法恢复。")
    box.addButton("删除", QMessageBox.ButtonRole.DestructiveRole)
    cancel_button = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    return box


def _clear_reports_confirmation_dialog(
    parent: QWidget | None = None,
) -> QMessageBox:
    """Build the clear-all-reports confirmation dialog."""
    box = QMessageBox(parent)
    box.setWindowTitle("确认删除")
    box.setText(
        "将删除 Echo 在本机保存的全部历史报告及其报告文件。\n"
        "不会删除 QQ / 微信原始聊天数据，也不会删除用户另存到其他位置的文件。\n"
        "删除后无法恢复。"
    )
    delete_button = box.addButton("删除", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(delete_button)
    return box


def _readonly_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _history_values(record: Any) -> tuple[str, ...]:
    return (
        _format_datetime(record.generated_at),
        _source_display(getattr(record, "source", "")),
        record.conversation_name or _UNKNOWN_SESSION_NAME,
        str(getattr(record, "message_count", 0)),
        _scope_display(
            record.analysis_scope.mode,
            start=record.analysis_scope.start_date,
            end=record.analysis_scope.end_date,
        ),
    )


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
