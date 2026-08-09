"""Source, session, and time-range selection page.

This page owns no business logic. It renders whatever
:class:`~qq_chat_analyzer.application.facade.ChatAnalyzerFacade` reports and
turns user gestures into facade calls. It never touches a provider, a parser,
or a database.
"""

from __future__ import annotations

import logging
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

from ..application.facade import (
    AnalysisConfig,
    ChatSource,
    WeChatEnvironmentConfig,
)
from .qq_setup_dialog import QQSetupDialog
from .workers import submit
from .wechat_setup_dialog import WeChatSetupDialog


SESSION_ID_ROLE = Qt.ItemDataRole.UserRole
SOURCE_ROLE = Qt.ItemDataRole.UserRole + 1

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.analysis_page")

_SELECT_SOURCE_HINT = "\u8bf7\u5148\u9009\u62e9\u6570\u636e\u6765\u6e90\u3002"
_LOADING_SESSIONS = "\u6b63\u5728\u52a0\u8f7d\u4f1a\u8bdd\u5217\u8868..."
_NO_SESSIONS = "\u8be5\u6765\u6e90\u6ca1\u6709\u53ef\u5206\u6790\u7684\u4f1a\u8bdd\u3002"
_LOCAL_FILE_HINT = (
    "\u672c\u5730\u6587\u4ef6\u6a21\u5f0f\uff1a\u8bf7\u9009\u62e9\u4e00\u4e2a"
    "\u5bfc\u51fa\u6587\u4ef6\u3002"
)
_ANALYZING = "\u6b63\u5728\u5206\u6790\uff0c\u8bf7\u7a0d\u5019..."
_SOURCE_DISPLAY_NAMES = {
    ChatSource.QQ: "QQ",
    ChatSource.WECHAT: "\u5fae\u4fe1",
}
_CONNECTION_STATUS_LOADING = (
    "\u6b63\u5728\u68c0\u6d4b {source} \u8fde\u63a5\u72b6\u6001..."
)
_CONNECTED_PREFIX = "\U0001F7E2 "
_DISCONNECTED_PREFIX = "\U0001F534 "
_CONNECTION_STATUS_UNKNOWN = (
    "\u65e0\u6cd5\u786e\u8ba4\u8fde\u63a5\u72b6\u6001\u3002"
)
_QQ_ENVIRONMENT_CHECKING = "\u6b63\u5728\u68c0\u6d4b QQ \u73af\u5883..."
_QQ_RUNTIME_STARTING = "\u6b63\u5728\u542f\u52a8 QQ \u8fd0\u884c\u73af\u5883..."
_QQ_SETUP_SAVING = "\u6b63\u5728\u4fdd\u5b58 QQ \u73af\u5883\u8bbe\u7f6e..."
_QQ_SETUP_FAILED = "QQ \u73af\u5883\u8bbe\u7f6e\u5931\u8d25"
_QQ_RUNTIME_OPERATION_FAILED = "QQ \u8fd0\u884c\u73af\u5883\u64cd\u4f5c\u5931\u8d25"
_WECHAT_CONNECT_LABEL = "\u8fde\u63a5\u5fae\u4fe1"
_WECHAT_CONNECTING = (
    "\u6b63\u5728\u51c6\u5907\u5fae\u4fe1\u8fde\u63a5\u73af\u5883\uff0c\u8bf7\u7a0d\u5019\u3002"
    "\u51c6\u5907\u5b8c\u6210\u540e\u4f1a\u63d0\u793a\u767b\u5f55\u5fae\u4fe1\u3002"
)
_WECHAT_CONNECT_FAILED = "\u5fae\u4fe1\u8fde\u63a5\u672a\u6210\u529f"
_WECHAT_CONNECT_RETRY_HINT = (
    "\u8bf7\u5148\u9000\u51fa\u5fae\u4fe1\u5230\u767b\u5f55\u754c\u9762\uff0c\u518d\u70b9\u51fb\u201c\u8fde\u63a5\u5fae\u4fe1\u201d\uff0c"
    "\u5e76\u5728\u51fa\u73b0\u767b\u5f55\u63d0\u793a\u540e\u767b\u5f55\u5fae\u4fe1\u3002"
)
_WECHAT_INTERNAL_TERMS = (
    "db_key",
    "dbkey",
    "hook",
    "runtime",
    "dll",
    "wcdb",
    "\u5bc6\u94a5",
)
_WECHAT_LOGIN_PREPARE = (
    "\u6b63\u5728\u51c6\u5907\u5fae\u4fe1\u8fde\u63a5\u73af\u5883\uff0c\u8bf7\u7a0d\u5019\u3002"
    "\u51c6\u5907\u5b8c\u6210\u540e\u4f1a\u63d0\u793a\u767b\u5f55\u5fae\u4fe1\uff0c\u5c4a\u65f6\u8bf7\u767b\u5f55\u5fae\u4fe1\u5373\u53ef\u81ea\u52a8\u5b8c\u6210\u8fde\u63a5\u3002"
)


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
        self._wechat_connect_pending = False

        self._build_ui()
        self.refresh_sources()

    # ------------------------------------------------------------------ setup

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._source_box = QGroupBox("\u6570\u636e\u6765\u6e90")
        self._source_layout = QHBoxLayout(self._source_box)
        layout.addWidget(self._source_box)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        self._wechat_connect_button = QPushButton(_WECHAT_CONNECT_LABEL)
        self._wechat_connect_button.setVisible(False)
        self._wechat_connect_button.clicked.connect(self.connect_wechat)
        layout.addWidget(self._wechat_connect_button)

        self._wechat_setup_button = QPushButton(
            "\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e..."
        )
        self._wechat_setup_button.setVisible(False)
        self._wechat_setup_button.clicked.connect(self.open_wechat_setup)
        layout.addWidget(self._wechat_setup_button)

        self._qq_setup_button = QPushButton("QQ \u73af\u5883\u8bbe\u7f6e...")
        self._qq_setup_button.setVisible(False)
        self._qq_setup_button.clicked.connect(self.open_qq_setup)
        layout.addWidget(self._qq_setup_button)

        self._qq_runtime_button = QPushButton(
            "\u542f\u52a8 QQ \u8fd0\u884c\u73af\u5883"
        )
        self._qq_runtime_button.setVisible(False)
        self._qq_runtime_button.clicked.connect(self.start_qq_runtime)
        layout.addWidget(self._qq_runtime_button)

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
        self._status_label.setVisible(False)

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

        if ChatSource.QQ in self._source_buttons:
            self.refresh_qq_status()

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
        self._wechat_connect_button.setVisible(source == ChatSource.WECHAT)
        self._wechat_setup_button.setVisible(source == ChatSource.WECHAT)
        self._qq_setup_button.setVisible(source == ChatSource.QQ)
        self._qq_runtime_button.setVisible(source == ChatSource.QQ)
        self._session_list.clear()

        if is_local:
            self._status_label.setVisible(False)
            self._hint_label.setText(_LOCAL_FILE_HINT)
            self._update_analyze_enabled()
            return

        if source == ChatSource.QQ:
            self._session_list.clear()
            self.refresh_qq_status(load_sessions_on_ready=True)
            return

        self._session_list.clear()
        self.refresh_connection_status(source, load_sessions_on_ready=True)

    def refresh_connection_status(
        self,
        source: ChatSource,
        *,
        load_sessions_on_ready: bool = False,
    ) -> None:
        """Ask the facade for one source's connection state and render it.

        The status is a user-layer model produced by the application layer, so
        this page never probes the provider itself.
        """
        display_name = _SOURCE_DISPLAY_NAMES.get(
            source,
            getattr(source, "value", str(source)),
        )
        self._status_label.setVisible(True)
        self._status_label.setText(
            _CONNECTION_STATUS_LOADING.format(source=display_name)
        )
        self._status_label.setToolTip("")
        if load_sessions_on_ready:
            self._hint_label.setText("")
        self._executor(
            lambda: self._facade.get_connection_status(source),
            on_success=lambda status: self._show_connection_status(
                source,
                status,
                load_sessions_on_ready,
            ),
            on_error=self._handle_connection_status_error,
        )

    def _show_connection_status(
        self,
        source: ChatSource,
        status: Any,
        load_sessions_on_ready: bool,
    ) -> None:
        """Render one source's connection status returned by the facade."""
        if getattr(status, "available", False):
            prefix = _CONNECTED_PREFIX
        else:
            prefix = _DISCONNECTED_PREFIX
        message = getattr(status, "message", "") or _CONNECTION_STATUS_UNKNOWN
        action_hint = getattr(status, "action_hint", "") or ""
        self._status_label.setText(f"{prefix}{message}")
        self._status_label.setToolTip(action_hint)
        self._status_label.setVisible(True)
        if source == ChatSource.WECHAT:
            self._wechat_setup_button.setVisible(not bool(getattr(status, "available", False)))

        if load_sessions_on_ready:
            self._hint_label.setText(action_hint)
        self._session_list.clear()
        self._update_analyze_enabled()
        if load_sessions_on_ready:
            self.status_changed.emit(action_hint or message)

        if getattr(status, "available", False) and load_sessions_on_ready:
            self._hint_label.setText(_LOADING_SESSIONS)
            self.status_changed.emit(_LOADING_SESSIONS)
            self._load_sessions(source)

    def _handle_connection_status_error(self, code: str, message: str) -> None:
        self._status_label.setText(_CONNECTION_STATUS_UNKNOWN)
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self._hint_label.setText(message)
        self._session_list.clear()
        self._update_analyze_enabled()

    def refresh_qq_status(self, *, load_sessions_on_ready: bool = False) -> None:
        """Ask the facade for QQ setup, runtime, and connection state."""
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_ENVIRONMENT_CHECKING)
        self._status_label.setToolTip("")
        self._qq_runtime_button.setEnabled(False)
        self._session_list.clear()
        self._update_analyze_enabled()
        self._executor(
            lambda: (
                self._facade.get_qq_setup_status(),
                self._facade.get_qq_runtime_status(),
                self._facade.get_connection_status(ChatSource.QQ),
            ),
            on_success=lambda snapshot: self._show_qq_status(
                snapshot[0],
                snapshot[1],
                snapshot[2],
                load_sessions_on_ready,
            ),
            on_error=self._handle_connection_status_error,
        )

    def _show_qq_status(
        self,
        setup_status: Any,
        runtime_status: Any,
        connection_status: Any,
        load_sessions_on_ready: bool,
    ) -> None:
        """Render QQ setup/runtime/connection state from the facade."""
        configured = bool(getattr(setup_status, "configured", False))
        runtime_state = getattr(runtime_status, "state", None)
        running = runtime_state == "running"
        available = bool(getattr(connection_status, "available", False))

        if not configured:
            message = (
                getattr(setup_status, "message", "")
                or "\u8bf7\u5148\u5b8c\u6210 QQ \u73af\u5883\u8bbe\u7f6e\u3002"
            )
            action_hint = getattr(setup_status, "action_hint", "") or ""
        elif not running:
            message = (
                getattr(runtime_status, "message", "")
                or "QQ \u8fd0\u884c\u73af\u5883\u672a\u8fd0\u884c\u3002"
            )
            action_hint = getattr(runtime_status, "action_hint", "") or ""
        else:
            message = (
                getattr(connection_status, "message", "")
                or _CONNECTION_STATUS_UNKNOWN
            )
            action_hint = getattr(connection_status, "action_hint", "") or ""

        prefix = _CONNECTED_PREFIX if available else _DISCONNECTED_PREFIX
        self._status_label.setText(f"{prefix}{message}")
        self._status_label.setToolTip(action_hint)
        self._status_label.setVisible(True)
        self._qq_setup_button.setVisible(True)
        self._qq_runtime_button.setVisible(True)
        self._qq_runtime_button.setEnabled(configured and not running)
        self._session_list.clear()
        self._update_analyze_enabled()

        if load_sessions_on_ready:
            self._hint_label.setText(action_hint)
            self.status_changed.emit(action_hint or message)

        if available and running and load_sessions_on_ready:
            self._hint_label.setText(_LOADING_SESSIONS)
            self.status_changed.emit(_LOADING_SESSIONS)
            self._load_sessions(ChatSource.QQ)

    def open_qq_setup(self) -> None:
        """Open the QQ setup dialog, showing the current facade state."""
        if self._selected_source is not ChatSource.QQ:
            return
        try:
            setup_status = self._facade.get_qq_setup_status()
        except Exception:
            setup_status = None
        self._qq_setup_dialog = QQSetupDialog(
            self,
            setup_status=setup_status,
        )
        self._qq_setup_dialog.accepted.connect(
            self._save_qq_environment_from_dialog
        )
        self._qq_setup_dialog.show()

    def _save_qq_environment_from_dialog(self) -> None:
        dialog = getattr(self, "_qq_setup_dialog", None)
        if dialog is not None:
            self.save_qq_environment(dialog.config())

    def save_qq_environment(self, config: Any) -> None:
        """Persist one QQ environment through the facade."""
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_SETUP_SAVING)
        self._status_label.setToolTip("")
        self._executor(
            lambda: self._facade.setup_qq_environment(config),
            on_success=lambda _status: self.refresh_qq_status(
                load_sessions_on_ready=True
            ),
            on_error=self._handle_qq_setup_error,
        )

    def start_qq_runtime(self) -> None:
        """Start the configured QQ runtime through the facade."""
        self._qq_runtime_button.setEnabled(False)
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_RUNTIME_STARTING)
        self._status_label.setToolTip("")
        self._executor(
            lambda: self._facade.start_qq_runtime(),
            on_success=lambda _status: self.refresh_qq_status(
                load_sessions_on_ready=True
            ),
            on_error=self._handle_qq_runtime_error,
        )

    def _handle_qq_setup_error(self, code: str, message: str) -> None:
        self._show_qq_error(_QQ_SETUP_FAILED, message)

    def _handle_qq_runtime_error(self, code: str, message: str) -> None:
        self._show_qq_error(_QQ_RUNTIME_OPERATION_FAILED, message)

    def _show_qq_error(self, title: str, message: str) -> None:
        self._status_label.setText(_DISCONNECTED_PREFIX + title)
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self._hint_label.setText(message)
        self.status_changed.emit(message)

    def connect_wechat(self, detect_data_root: Any = None) -> None:
        """Connect WeChat in one click, asking for a directory only if needed.

        The detected data root is handed to the facade, which persists it and
        acquires the database key. That call blocks while the user finishes
        logging in, so it runs through the injected executor and never on the
        UI thread. When nothing can be detected, the existing setup dialog
        collects the directory instead.
        """
        if self._selected_source is not ChatSource.WECHAT:
            return

        detect = detect_data_root or self._facade.detect_wechat_data_root
        try:
            data_root = detect()
        except Exception:
            data_root = None

        if data_root is None:
            self._wechat_connect_pending = True
            self.open_wechat_setup()
            return

        self._start_wechat_connect(
            WeChatEnvironmentConfig(data_root=Path(data_root))
        )

    def _start_wechat_connect(self, config: Any) -> None:
        """Run save-then-key for one config, off the UI thread."""
        self._wechat_connect_button.setEnabled(False)
        self._status_label.setVisible(True)
        self._status_label.setText(_WECHAT_CONNECTING)
        self._status_label.setToolTip("")
        self._hint_label.setText(_WECHAT_LOGIN_PREPARE)
        self.status_changed.emit(_WECHAT_CONNECTING)

        self._executor(
            lambda report: self._connect_wechat_operation(config, report),
            on_success=lambda _result: self._after_wechat_environment_saved(),
            on_error=self._handle_wechat_connect_error,
            on_progress=self._handle_wechat_connect_progress,
            on_finished=lambda: self._wechat_connect_button.setEnabled(True),
        )

    def _connect_wechat_operation(
        self,
        config: Any,
        progress: Any = None,
    ) -> Any:
        """Save the directory, then acquire the key. Runs off the UI thread.

        These are two steps because saving must not depend on WeChat being at
        a login moment. Only the key step waits for the user to log in.
        """
        self._facade.setup_wechat_environment(config)
        return self._facade.acquire_wechat_db_key(progress=progress)

    def _handle_wechat_connect_progress(self, message: str) -> None:
        """Surface a key acquisition status line through existing widgets."""
        _LOGGER.debug("[wechat gui] received progress: %s", message)
        self._status_label.setVisible(True)
        self._status_label.setText(message)
        self._hint_label.setText(message)
        self.status_changed.emit(message)

    def _handle_wechat_connect_error(self, code: str, message: str) -> None:
        """Show a plain-language failure. Internal wording is replaced."""
        detail = message or ""
        lowered = detail.lower()
        if any(term in lowered for term in _WECHAT_INTERNAL_TERMS):
            detail = ""
        text = detail or _WECHAT_CONNECT_RETRY_HINT
        self._status_label.setText(
            _DISCONNECTED_PREFIX + _WECHAT_CONNECT_FAILED
        )
        self._status_label.setToolTip(text)
        self._status_label.setVisible(True)
        self._hint_label.setText(text)
        self.status_changed.emit(text)

    def open_wechat_setup(self) -> None:
        """Open the setup dialog, showing the current facade state."""
        if self._selected_source is not ChatSource.WECHAT:
            return
        try:
            setup_status = self._facade.get_wechat_setup_status()
        except Exception:
            setup_status = None
        try:
            detected_root = self._facade.detect_wechat_data_root()
        except Exception:
            detected_root = None
        self._wechat_setup_dialog = WeChatSetupDialog(
            self,
            setup_status=setup_status,
            data_root=detected_root,
        )
        self._wechat_setup_dialog.accepted.connect(
            self._save_wechat_environment_from_dialog
        )
        self._wechat_setup_dialog.show()

    def _save_wechat_environment_from_dialog(self) -> None:
        dialog = getattr(self, "_wechat_setup_dialog", None)
        if dialog is None:
            return
        pending = getattr(self, "_wechat_connect_pending", False)
        self._wechat_connect_pending = False
        if pending:
            self._start_wechat_connect(dialog.config())
            return
        self.save_wechat_environment(dialog.config())

    def save_wechat_environment(self, config: Any) -> None:
        """Persist one WeChat environment through the facade."""
        self._status_label.setVisible(True)
        self._status_label.setText(
            "\u6b63\u5728\u4fdd\u5b58\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e..."
        )
        self._status_label.setToolTip("")
        self._executor(
            lambda: self._facade.setup_wechat_environment(config),
            on_success=lambda _status: self._after_wechat_environment_saved(),
            on_error=self._handle_setup_error,
        )

    def _after_wechat_environment_saved(self) -> None:
        self.refresh_connection_status(
            ChatSource.WECHAT,
            load_sessions_on_ready=True,
        )

    def _handle_setup_error(self, code: str, message: str) -> None:
        self._status_label.setText(
            _DISCONNECTED_PREFIX + "\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e\u5931\u8d25"
        )
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self._hint_label.setText(message)
        self.status_changed.emit(message)

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
