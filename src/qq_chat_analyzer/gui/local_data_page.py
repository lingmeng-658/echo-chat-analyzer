"""Local data management page: Echo report packages."""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
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

from ..application.facade import FacadeError
from .theme import COLOR_ACCENT_SOFT, COLOR_PAPER, LOCAL_DATA_QSS, STATUS_STYLE_BASE
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
        self._refresh_generation = 0
        self._has_loaded = False
        self._load_failed = False
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("localDataPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(LOCAL_DATA_QSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(20)

        title = QLabel("Echo 历史")
        title.setObjectName("localDataTitle")
        layout.addWidget(title)
        description = QLabel(
            "本机保存的 Echo 报告都在这里，可以随时打开回看；删除只影响 Echo 报告文件。"
        )
        description.setObjectName("localDataDescription")
        description.setWordWrap(True)
        layout.addWidget(description)

        summary = QFrame()
        summary.setObjectName("localDataSummary")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(20, 16, 20, 16)
        summary_row = QHBoxLayout()
        self._summary_count_label = QLabel("—")
        self._summary_count_label.setObjectName("localDataCount")
        self._summary_size_label = QLabel("—")
        self._summary_size_label.setObjectName("localDataSize")
        for caption, value in (
            ("已保存报告", self._summary_count_label),
            ("报告文件占用", self._summary_size_label),
        ):
            metric = QVBoxLayout()
            metric.setSpacing(6)
            caption_label = QLabel(caption)
            caption_label.setObjectName("localDataMetricCaption")
            metric.addWidget(caption_label)
            metric.addWidget(value)
            summary_row.addLayout(metric, stretch=1)
        summary_layout.addLayout(summary_row)
        self._summary_note_label = QLabel("")
        self._summary_note_label.setObjectName("localDataSummaryNote")
        self._summary_note_label.setWordWrap(True)
        self._summary_note_label.hide()
        summary_layout.addWidget(self._summary_note_label)
        layout.addWidget(summary)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(STATUS_STYLE_BASE)
        self._status_label.hide()
        layout.addWidget(self._status_label)

        history_box = QGroupBox("报告列表")
        history_box.setObjectName("localDataHistory")
        history_layout = QVBoxLayout(history_box)
        history_layout.setContentsMargins(20, 32, 20, 20)
        history_layout.setSpacing(16)
        search_row = QHBoxLayout()
        self._refresh_button = QPushButton("刷新")
        self._refresh_button.setMinimumHeight(34)
        self._refresh_button.clicked.connect(self.refresh)
        self._search_input = QLineEdit()
        self._search_input.setMinimumHeight(36)
        self._search_input.setPlaceholderText("搜索会话名、来源、类型、日期或分析范围")
        self._search_input.setAccessibleName("搜索历史报告")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._apply_search)
        search_row.addWidget(self._search_input, stretch=1)
        search_row.addWidget(self._refresh_button)
        history_layout.addLayout(search_row)
        self._history_empty_state = QWidget()
        self._history_empty_state.setObjectName("localDataEmptyState")
        empty_layout = QVBoxLayout(self._history_empty_state)
        empty_layout.setContentsMargins(12, 40, 12, 40)
        empty_layout.addStretch(1)
        self._history_empty_label = QLabel("暂无报告")
        self._history_empty_label.setObjectName("localDataEmptyTitle")
        self._history_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._history_empty_label)
        self._history_empty_detail_label = QLabel("分析完成后，报告会保存在本机，方便随时回看。")
        self._history_empty_detail_label.setObjectName("localDataEmptyDetail")
        self._history_empty_detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._history_empty_detail_label.setWordWrap(True)
        empty_layout.addWidget(self._history_empty_detail_label)
        empty_layout.addStretch(1)
        history_layout.addWidget(self._history_empty_state, stretch=1)
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
        self._history_table.verticalHeader().hide()
        self._history_table.verticalHeader().setDefaultSectionSize(44)
        self._history_table.setShowGrid(False)
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
        for column in (2, 4):
            self._history_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.Stretch,
            )
        history_layout.addWidget(self._history_table, stretch=1)

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

    # ---------------------------------------------------------------- public API

    def refresh(self, *, error_message: str = "") -> None:
        """Load the list and storage summary together off the GUI thread."""
        self._refresh_generation += 1
        generation = self._refresh_generation
        self._history_table.clearSelection()
        self._history_table.setCurrentCell(-1, -1)
        self._set_status(_LOADING_STATUS)
        self._refresh_button.setEnabled(False)

        def on_success(result: Any) -> None:
            if generation == self._refresh_generation:
                listing, usage, usage_error = result
                self._render_data(listing, usage, usage_error, error_message)
                self._refresh_button.setEnabled(True)

        def on_error(code: str, message: str) -> None:
            if generation == self._refresh_generation:
                self._load_failed = not self._has_loaded
                self._apply_search()
                self._show_error(code, message)
                self._refresh_button.setEnabled(True)

        self._executor(
            self._load_archive,
            on_success=on_success,
            on_error=on_error,
        )

    # ---------------------------------------------------------------- internals

    def _load_archive(self) -> tuple[Any, Any, str]:
        listing = self._facade.list_report_packages()
        try:
            usage = self._facade.get_report_storage_usage()
        except FacadeError as error:
            return listing, None, error.public_message
        except Exception:
            _LOGGER.exception("Local report storage summary failed")
            return listing, None, "无法统计 Echo 本地报告占用空间，请稍后重试。"
        return listing, usage, ""

    def _render_data(
        self, listing: Any, usage: Any, usage_error: str, error_message: str = "",
    ) -> None:
        _LOGGER.info("Local data rendered reports=%d issues=%d deletion_error=%s",
                     len(listing.reports), len(listing.issues), bool(error_message))
        self._reports = tuple(listing.reports)
        self._has_loaded = True
        self._load_failed = False
        count = usage.package_count if usage is not None else len(self._reports)
        self._summary_count_label.setText(f"{count} 份")
        size = _format_bytes(usage.measured_bytes) if usage is not None else "—"
        self._summary_size_label.setText(size)
        note = usage_error
        if usage is not None and not usage.complete:
            note = (
                f"当前大小为已测量下界；{len(usage.unmeasured_packages)} 份报告无法测量。"
            )
        self._summary_note_label.setText(note)
        self._summary_note_label.setVisible(bool(note))
        self._apply_search()
        self._issues_label.setText(f"发现 {len(listing.issues)} 个无法读取的 Echo 报告")
        self._issues_label.setVisible(bool(listing.issues))
        self._set_status(error_message)

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
        if self._load_failed:
            title, detail = "暂时无法读取本地报告", "请稍后点击刷新重试。"
        elif self._reports:
            title, detail = "没有匹配的报告", "换一个关键词试试，或清空搜索框。"
        else:
            title, detail = "暂无报告", "分析完成后，报告会保存在本机，方便随时回看。"
        self._history_empty_label.setText(title)
        self._history_empty_detail_label.setText(detail)

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
        self._history_empty_detail_label.setVisible(len(records) == 0)
        self._history_empty_state.setVisible(len(records) == 0)
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
        self._set_status(
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
        self._set_status("正在删除选中报告...")
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
        self._set_status("正在删除全部报告...")
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
        self._set_status(message)

    def _set_status(self, message: str) -> None:
        self._status_label.setText(message)
        self._status_label.setVisible(bool(message))


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


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable size unit")


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
