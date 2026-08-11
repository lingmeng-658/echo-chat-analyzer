"""Source, session, and time-range selection page.

This page owns no business logic. It renders whatever
:class:`~qq_chat_analyzer.application.facade.ChatAnalyzerFacade` reports and
turns user gestures into facade calls. It never touches a provider, a parser,
or a database.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from ..resources import default_qq_runtime_directory
from .workers import submit
from .wechat_setup_dialog import WeChatSetupDialog


SESSION_ID_ROLE = Qt.ItemDataRole.UserRole
SOURCE_ROLE = Qt.ItemDataRole.UserRole + 1

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.analysis_page")

_SELECT_SOURCE_HINT = "\u8bf7\u5148\u9009\u62e9\u6570\u636e\u6765\u6e90\u3002"
_LOADING_SESSIONS = "\u6b63\u5728\u52a0\u8f7d\u4f1a\u8bdd\u5217\u8868..."
_NO_SESSIONS = "\u8be5\u6765\u6e90\u6ca1\u6709\u53ef\u5206\u6790\u7684\u4f1a\u8bdd\u3002"
_NO_MESSAGES_AVAILABLE = "\u8be5\u4f1a\u8bdd\u6ca1\u6709\u53ef\u5206\u6790\u6d88\u606f"
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
_QQ_STATUS_CHECKING = "\u6b63\u5728\u68c0\u6d4b QQ \u8fde\u63a5\u72b6\u6001..."
_QQ_CONNECT_LABEL = "\u8fde\u63a5QQ"
_QQ_RECONNECT_LABEL = "\u91cd\u65b0\u8fde\u63a5QQ"
_QQ_CONNECTING = (
    "\u6b63\u5728\u51c6\u5907QQ\u8fde\u63a5\u73af\u5883\uff0c"
    "\u8bf7\u7a0d\u5019..."
)
_QQ_CONNECT_PREPARE = "\u6b63\u5728\u81ea\u52a8\u8fde\u63a5 QQ\uff0c\u8bf7\u7a0d\u5019\u3002"
_QQ_CONNECT_FAILED = "QQ \u8fde\u63a5\u5931\u8d25"
_QQ_CONNECT_MIN_DISPLAY_MS = 500
_QQ_STATUS_POLL_INTERVAL_MS = 2000
_QQ_QRCODE_SIZE = 240
_QQ_QRCODE_RELATIVE_PATH = Path("cache") / "qrcode.png"
_QQ_LOGIN_GUIDE = (
    "登录QQ以读取聊天记录\n\n"
    "1. 请使用手机QQ扫描下方二维码\n"
    "2. 打开手机QQ扫一扫功能（通常位于右上角“+”菜单中）\n"
    "3. 扫描二维码完成QQ登录授权\n"
    "4. 登录成功后，余音会自动加载您的聊天会话\n\n"
    "二维码仅用于QQ登录认证，聊天数据仅在本机处理。"
)
_QQ_STATE_DISCONNECTED = "disconnected"
_QQ_STATE_INITIALIZING = "initializing"
_QQ_STATE_STARTING = "starting"
_QQ_STATE_WAITING_AUTH = "waiting_auth"
_QQ_STATE_CONNECTED = "connected"
_QQ_STATE_ERROR = "error"
_QQ_PENDING_PREFIX = "\U0001F7E1 "
_QQ_PROGRESS_STATES = (
    _QQ_STATE_INITIALIZING,
    _QQ_STATE_STARTING,
)
_QQ_STATE_MESSAGES = {
    _QQ_STATE_DISCONNECTED: "QQ \u5c1a\u672a\u8fde\u63a5\u3002",
    _QQ_STATE_INITIALIZING: (
        "\u6b63\u5728\u521d\u59cb\u5316 QQ \u8fde\u63a5\uff0c\u8bf7\u7a0d\u5019..."
    ),
    _QQ_STATE_STARTING: (
        "\u6b63\u5728\u542f\u52a8 QQ\uff0c\u8bf7\u7a0d\u5019..."
    ),
    _QQ_STATE_WAITING_AUTH: (
        "\u7b49\u5f85 QQ \u767b\u5f55\uff1a\u8bf7\u5728 QQ \u4e2d\u5b8c\u6210\u767b\u5f55\u6388\u6743\u3002"
    ),
    _QQ_STATE_CONNECTED: "QQ \u5df2\u8fde\u63a5\u3002",
    _QQ_STATE_ERROR: (
        "\u65e0\u6cd5\u8fde\u63a5 QQ\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
    ),
}
_WECHAT_CONNECT_LABEL = "\u8fde\u63a5\u5fae\u4fe1"
_WECHAT_RECONNECT_LABEL = "\u91cd\u65b0\u8fde\u63a5\u5fae\u4fe1"
_WECHAT_STATUS_DISCONNECTED = "\u5fae\u4fe1\u672a\u8fde\u63a5"
_WECHAT_STATUS_CONNECTING = "\u6b63\u5728\u8fde\u63a5\u5fae\u4fe1..."
_WECHAT_STATUS_CONNECTED = (
    "\u5fae\u4fe1\u5df2\u8fde\u63a5\uff0c\u53ef\u4ee5\u5f00\u59cb\u5206\u6790"
)
_WECHAT_CONNECTING = _WECHAT_STATUS_CONNECTING
_WECHAT_CONNECT_FAILED = "\u5fae\u4fe1\u8fde\u63a5\u672a\u6210\u529f"
_WECHAT_CONNECT_RETRY_HINT = (
    "请保持微信电脑版打开，在余音中重新点击连接，并按提示完成微信登录。"
)
_WECHAT_GUIDE_STATUS = (
    "请保持微信电脑版打开，\n"
    "余音将在连接过程中等待登录操作。\n"
    "连接期间请不要退出微信或切换账号。"
)
_WECHAT_GUIDE_KEY = (
    "为读取你的本地微信聊天记录，\n"
    "余音会在本机完成微信连接准备。\n"
    "- 仅在本机使用\n"
    "- 不上传\n"
    "- 不保存"
)
_WECHAT_GUIDE_DIRECTORY_MISSING = (
    "如果未自动识别微信数据目录，\n"
    "请点击上方按钮，选择微信设置中显示的存储文件夹。"
)
_WECHAT_DETECTED = "\u2713 \u5df2\u68c0\u6d4b\u5230\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55\u4f4d\u7f6e"
_WECHAT_NOT_DETECTED = "\u672a\u81ea\u52a8\u8bc6\u522b\u5230\u5fae\u4fe1\u5b58\u50a8\u4f4d\u7f6e"
_WECHAT_MULTIPLE_DETECTED = (
    "\u68c0\u6d4b\u5230\u591a\u4e2a\u5fae\u4fe1\u804a\u5929\u8bb0\u5f55\u4f4d\u7f6e\uff0c"
    "\u8bf7\u9009\u62e9\u5176\u4e2d\u4e00\u4e2a\u3002"
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
    "\u6b63\u5728\u51c6\u5907\u5fae\u4fe1\u8fde\u63a5\uff0c\u8bf7\u7a0d\u5019\u3002"
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
        qq_qrcode_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._facade = facade
        self._executor = executor or submit
        self._selected_source: ChatSource | None = None
        self._selected_file: Path | None = None
        self._analysis_running = False
        self._source_buttons: dict[ChatSource, QPushButton] = {}
        self._wechat_connect_pending = False
        self._qq_connect_in_flight = False
        self._message_range: tuple[int, int] | None = None
        self._sessions: list[Any] = []
        self._last_qq_status_message = ""
        self._qq_qrcode_path = (
            Path(qq_qrcode_path)
            if qq_qrcode_path is not None
            else _default_qq_qrcode_path()
        )
        self._qq_status_timer = QTimer(self)
        self._qq_status_timer.setInterval(_QQ_STATUS_POLL_INTERVAL_MS)
        self._qq_status_timer.timeout.connect(self._poll_qq_status)

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

        self._wechat_guide_label = QLabel("")
        self._wechat_guide_label.setWordWrap(True)
        self._wechat_guide_label.setVisible(False)
        layout.addWidget(self._wechat_guide_label)

        self._qq_connect_button = QPushButton(_QQ_CONNECT_LABEL)
        self._qq_connect_button.setVisible(False)
        self._qq_connect_button.clicked.connect(self.connect_qq)
        layout.addWidget(self._qq_connect_button)

        self._qq_qrcode_label = QLabel("")
        self._qq_qrcode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qq_qrcode_label.setFixedSize(_QQ_QRCODE_SIZE, _QQ_QRCODE_SIZE)
        self._qq_qrcode_label.setVisible(False)
        layout.addWidget(self._qq_qrcode_label)

        self._qq_login_guide_label = QLabel("")
        self._qq_login_guide_label.setWordWrap(True)
        self._qq_login_guide_label.setVisible(False)
        layout.addWidget(self._qq_login_guide_label)

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
        layout.addWidget(session_box, stretch=1)

        range_box = QGroupBox("\u65f6\u95f4\u8303\u56f4")
        range_layout = QFormLayout(range_box)
        self._start_enabled = QCheckBox("\u542f\u7528\u5f00\u59cb\u65f6\u95f4")
        self._start_date = QDateEdit()
        self._start_date.setMinimumDate(QDate(1, 1, 1))
        self._start_date.setDate(QDate(1, 1, 1))
        self._start_date.setSpecialValueText("\u672a\u9009\u62e9")
        self._start_date.setCalendarPopup(True)
        self._start_date.setEnabled(False)
        self._start_enabled.toggled.connect(self._on_start_time_toggled)
        self._end_enabled = QCheckBox("\u542f\u7528\u7ed3\u675f\u65f6\u95f4")
        self._end_date = QDateEdit()
        self._end_date.setMinimumDate(QDate(1, 1, 1))
        self._end_date.setDate(QDate(1, 1, 1))
        self._end_date.setSpecialValueText("\u672a\u9009\u62e9")
        self._end_date.setCalendarPopup(True)
        self._end_date.setEnabled(False)
        self._end_enabled.toggled.connect(self._on_end_time_toggled)
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
            if info.source == ChatSource.LOCAL_FILE:
                continue
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
        if source != ChatSource.QQ:
            self._stop_qq_status_polling()
            self._hide_qq_qrcode()
            self._hide_qq_login_guide()

        for candidate, button in self._source_buttons.items():
            button.setChecked(candidate == source)

        is_local = source == ChatSource.LOCAL_FILE
        self._file_button.setVisible(is_local)
        self._file_label.setVisible(is_local)
        self._wechat_connect_button.setVisible(source == ChatSource.WECHAT)
        self._wechat_setup_button.setVisible(source == ChatSource.WECHAT)
        self._wechat_guide_label.setVisible(source == ChatSource.WECHAT)
        if source == ChatSource.WECHAT:
            self._show_wechat_guide()
        else:
            self._wechat_guide_label.clear()
        self._qq_connect_button.setVisible(source == ChatSource.QQ)
        self._qq_connect_button.setEnabled(True)
        self._qq_connect_button.setToolTip("")
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
        available = bool(getattr(status, "available", False))
        prefix = _CONNECTED_PREFIX if available else _DISCONNECTED_PREFIX
        if source == ChatSource.WECHAT:
            message = (
                _WECHAT_STATUS_CONNECTED
                if available
                else _WECHAT_STATUS_DISCONNECTED
            )
        else:
            message = (
                getattr(status, "message", "") or _CONNECTION_STATUS_UNKNOWN
            )
        action_hint = getattr(status, "action_hint", "") or ""
        self._status_label.setText(f"{prefix}{message}")
        self._status_label.setToolTip(action_hint)
        self._status_label.setVisible(True)
        if source == ChatSource.WECHAT:
            self._wechat_setup_button.setVisible(not available)
            if available:
                self._wechat_guide_label.setVisible(False)
            else:
                self._show_wechat_guide()
            self._wechat_connect_button.setText(
                _WECHAT_RECONNECT_LABEL
                if available
                else _WECHAT_CONNECT_LABEL
            )
        elif source == ChatSource.QQ:
            self._qq_connect_button.setText(
                _QQ_RECONNECT_LABEL if available else _QQ_CONNECT_LABEL
            )
            self._qq_connect_button.setEnabled(True)
            self._qq_connect_button.setToolTip("")

        if load_sessions_on_ready:
            self._hint_label.setText(action_hint)
        self._session_list.clear()
        self._update_analyze_enabled()
        if load_sessions_on_ready:
            if source == ChatSource.WECHAT:
                self.status_changed.emit(message)
            else:
                self.status_changed.emit(message)

        if available and load_sessions_on_ready:
            self._hint_label.setText(_LOADING_SESSIONS)
            if source != ChatSource.WECHAT:
                self.status_changed.emit(_LOADING_SESSIONS)
            self._load_sessions(source)

    def _show_wechat_guide(
        self,
        *,
        include_directory_help: bool = False,
    ) -> None:
        """Render the first-time WeChat connection guide."""
        parts = [_WECHAT_GUIDE_STATUS, _WECHAT_GUIDE_KEY]
        if include_directory_help:
            parts.append(_WECHAT_GUIDE_DIRECTORY_MISSING)
        self._wechat_guide_label.setText("\n\n".join(parts))
        self._wechat_guide_label.setVisible(True)

    def _handle_connection_status_error(self, code: str, message: str) -> None:
        if self._qq_connect_in_flight and self._selected_source == ChatSource.QQ:
            return
        self._status_label.setText(_CONNECTION_STATUS_UNKNOWN)
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self._hint_label.setText(message)
        self._session_list.clear()
        self._update_analyze_enabled()

    def refresh_qq_status(self, *, load_sessions_on_ready: bool = False) -> None:
        """Ask the connection manager, through the facade, for QQ state."""
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_STATUS_CHECKING)
        self._status_label.setToolTip("")
        self._session_list.clear()
        self._update_analyze_enabled()
        self._executor(
            lambda: self._facade.get_qq_connection_snapshot(),
            on_success=lambda snapshot: self._show_qq_status(
                snapshot,
                load_sessions_on_ready,
            ),
            on_error=self._handle_connection_status_error,
        )

    def _show_qq_status(
        self,
        snapshot: Any,
        load_sessions_on_ready: bool,
    ) -> None:
        """Render one QQ connection snapshot and the connect button.

        The page does not decide what "connected" means; it reads the state
        the connection manager already resolved.
        """
        if self._qq_connect_in_flight:
            return
        state = _snapshot_state(snapshot)
        message = _snapshot_message(snapshot)
        action_hint = _snapshot_hint(snapshot)
        self._last_qq_status_message = message

        self._status_label.setText(f"{_snapshot_prefix(snapshot)}{message}")
        self._status_label.setToolTip(action_hint)
        self._status_label.setVisible(True)
        self._qq_connect_button.setText(
            (
                _QQ_RECONNECT_LABEL
                if state == _QQ_STATE_CONNECTED
                else _QQ_CONNECT_LABEL
            )
        )
        self._qq_connect_button.setEnabled(not _snapshot_in_progress(snapshot))
        self._qq_connect_button.setToolTip("")
        self._session_list.clear()
        self._update_analyze_enabled()

        if load_sessions_on_ready:
            self._hint_label.setText(action_hint)
            self.status_changed.emit(message)

        if state == _QQ_STATE_CONNECTED and load_sessions_on_ready:
            self._hint_label.setText(_LOADING_SESSIONS)
            self.status_changed.emit(_LOADING_SESSIONS)
            self._load_sessions(ChatSource.QQ)

        if state == _QQ_STATE_WAITING_AUTH:
            self._show_qq_login_guide()
            self._start_qq_status_polling()
            self._refresh_qq_qrcode()
        else:
            self._hide_qq_login_guide()
            self._stop_qq_status_polling()
            self._hide_qq_qrcode()

    def _poll_qq_status(self) -> None:
        """Refresh the QQ snapshot while the user is waiting to log in."""
        if self._selected_source != ChatSource.QQ:
            self._stop_qq_status_polling()
            return
        self._executor(
            lambda: self._facade.get_qq_connection_snapshot(),
            on_success=lambda snapshot: self._show_qq_status(
                snapshot,
                load_sessions_on_ready=True,
            ),
            on_error=self._handle_connection_status_error,
        )

    def _start_qq_status_polling(self) -> None:
        if (
            self._selected_source == ChatSource.QQ
            and not self._qq_status_timer.isActive()
        ):
            self._qq_status_timer.start()

    def _stop_qq_status_polling(self) -> None:
        self._qq_status_timer.stop()

    def _refresh_qq_qrcode(self) -> None:
        """Show the runtime's current login QR image when it exists."""
        if not self._qq_qrcode_path.is_file():
            self._hide_qq_qrcode()
            return
        try:
            pixmap = QPixmap(str(self._qq_qrcode_path))
        except Exception:
            pixmap = QPixmap()
        if pixmap.isNull():
            self._hide_qq_qrcode()
            return
        scaled = pixmap.scaled(
            self._qq_qrcode_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._qq_qrcode_label.setPixmap(scaled)
        self._qq_qrcode_label.setVisible(True)

    def _hide_qq_qrcode(self) -> None:
        """Clear and hide the QR image once it is no longer needed."""
        self._qq_qrcode_label.clear()
        self._qq_qrcode_label.setVisible(False)

    def _show_qq_login_guide(self) -> None:
        """Show the first-time QR login instructions while waiting for auth."""
        self._qq_login_guide_label.setText(_QQ_LOGIN_GUIDE)
        self._qq_login_guide_label.setVisible(True)

    def _hide_qq_login_guide(self) -> None:
        """Hide QR login instructions once the QQ state moves on."""
        self._qq_login_guide_label.clear()
        self._qq_login_guide_label.setVisible(False)

    def connect_qq(self) -> None:
        """Start the QQ authorization flow in one click.

        The facade's auth bridge owns runtime startup and the login window;
        this page only renders the resulting lifecycle snapshot and keeps
        polling until the QQ data source reports connected.
        """
        if self._selected_source != ChatSource.QQ:
            _LOGGER.info(
                "[qq gui] connect_qq ignored selected_source=%r",
                self._selected_source,
            )
            return
        _LOGGER.info(
            "[qq gui] connect_qq requested selected_source=%r",
            self._selected_source,
        )
        started_at = time.monotonic()
        self._qq_connect_in_flight = True
        self._qq_connect_button.setEnabled(False)
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_CONNECTING)
        self._status_label.setToolTip("")
        self._hint_label.setText(_QQ_CONNECT_PREPARE)
        self.status_changed.emit(_QQ_CONNECTING)
        _LOGGER.info("[qq gui] connect_qq worker submitted")
        self._executor(
            lambda report: self._facade.start_qq_auth_flow(progress=report),
            on_success=lambda status: self._finish_qq_connect(
                status,
                started_at,
            ),
            on_error=lambda code, message: self._finish_qq_connect_error(
                code,
                message,
                started_at,
            ),
            on_progress=self._handle_qq_connect_progress,
        )

    def _handle_qq_connect_progress(self, message: str) -> None:
        """Render a stage reported by the QQ backend flow verbatim."""
        if not message:
            return
        self._status_label.setText(_QQ_PENDING_PREFIX + message)
        self._status_label.setToolTip("")
        self._status_label.setVisible(True)
        self._hint_label.setText(message)
        self.status_changed.emit(message)

    def _after_qq_connect(self, snapshot: Any) -> None:
        self._show_qq_status(snapshot, load_sessions_on_ready=True)

    def _finish_qq_connect(self, status: Any, started_at: float) -> None:
        def _apply() -> None:
            self._qq_connect_in_flight = False
            _LOGGER.info(
                "[qq gui] connect_qq succeeded state=%s",
                _snapshot_state(status),
            )
            self._after_qq_connect(status)
            self._qq_connect_button.setEnabled(True)

        QTimer.singleShot(self._connect_display_delay(started_at), _apply)

    def _finish_qq_connect_error(
        self,
        code: str,
        message: str,
        started_at: float,
    ) -> None:
        def _apply() -> None:
            self._qq_connect_in_flight = False
            _LOGGER.info("[qq gui] connect_qq failed code=%s", code)
            self._handle_qq_connect_error(code, message)
            self._qq_connect_button.setEnabled(True)

        QTimer.singleShot(self._connect_display_delay(started_at), _apply)

    @staticmethod
    def _connect_display_delay(started_at: float) -> int:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        return max(0, _QQ_CONNECT_MIN_DISPLAY_MS - elapsed_ms)

    def _handle_qq_connect_error(self, code: str, message: str) -> None:
        self._show_qq_error(_QQ_CONNECT_FAILED, message)

    def _show_qq_error(self, title: str, message: str) -> None:
        self._status_label.setText(_DISCONNECTED_PREFIX + title)
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self._hint_label.setText(message)
        self.status_changed.emit(title)

    def connect_wechat(
        self,
        detect_data_root: Any = None,
        detect_data_roots: Any = None,
    ) -> None:
        """Connect WeChat in one click, asking for a directory only if needed.

        A single detected data root continues the existing one-click flow. No
        candidates fall back to the manual directory dialog with the beginner
        guide, and several candidates are shown for the user to pick.
        """
        if self._selected_source is not ChatSource.WECHAT:
            return

        detect_roots = detect_data_roots or self._facade.detect_wechat_data_roots
        try:
            roots = [Path(value) for value in detect_roots() or ()]
        except Exception:
            roots = []

        self._wechat_connect_pending = True
        if len(roots) == 1:
            self._wechat_connect_pending = False
            self._status_label.setVisible(True)
            self._status_label.setText(_WECHAT_DETECTED)
            self._status_label.setToolTip("")
            self._start_wechat_connect(
                WeChatEnvironmentConfig(data_root=roots[0])
            )
            return

        self._status_label.setVisible(True)
        if len(roots) > 1:
            self._status_label.setText(_WECHAT_MULTIPLE_DETECTED)
            self.open_wechat_setup(data_roots=roots)
            return

        self._status_label.setText(_WECHAT_NOT_DETECTED)
        self._show_wechat_guide(include_directory_help=True)
        self.open_wechat_setup()

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
        """Keep the unified connecting status while showing progress detail."""
        _LOGGER.debug("[wechat gui] received progress: %s", message)
        self._status_label.setVisible(True)
        self._status_label.setText(_WECHAT_CONNECTING)
        self._hint_label.setText(message)

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

    def open_wechat_setup(self, data_roots: Any = None) -> None:
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
            data_roots=data_roots,
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

    def _on_session_selection_changed(self) -> None:
        self._update_analyze_enabled()
        self._reset_time_range()
        if self._selected_source in (ChatSource.QQ, ChatSource.WECHAT):
            session_id = self.selected_session_id()
            if session_id:
                self._request_session_time_range(session_id)

    def _reset_time_range(self) -> None:
        self._message_range = None
        for enabled, edit in (
            (self._start_enabled.isChecked(), self._start_date),
            (self._end_enabled.isChecked(), self._end_date),
        ):
            edit.setDate(
                QDate.currentDate() if enabled else QDate(1, 1, 1)
            )

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
        if self._start_enabled.isChecked():
            self._apply_date_default(self._start_date, 0)
        if self._end_enabled.isChecked():
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
            edit.setDate(
                QDate.fromString(date_text, "yyyy-MM-dd")
            )
        else:
            edit.setDate(QDate.currentDate())

    def _on_start_time_toggled(self, checked: bool) -> None:
        self._start_date.setEnabled(checked)
        if checked:
            self._apply_date_default(self._start_date, 0)

    def _on_end_time_toggled(self, checked: bool) -> None:
        self._end_date.setEnabled(checked)
        if checked:
            self._apply_date_default(self._end_date, 1)

    def _populate_sessions(self, sessions: Any) -> None:
        """Fill the list with sessions, keeping ids out of the visible text."""
        self._sessions = list(sessions or ())
        self._reapply_session_view()

    def _reapply_session_view(self) -> None:
        """Filter and sort the cached sessions for the current controls."""
        query = self._session_search.text().strip().lower()
        sort_mode = self._session_sort.currentData() or _SESSION_SORT_ORDER[0][1]
        indexed = list(enumerate(self._sessions))
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
        if count == 0 and self._sessions:
            self._hint_label.setText(_NO_MATCHING_SESSIONS)
        elif count == 0:
            self._hint_label.setText(_NO_SESSIONS)
        else:
            self._hint_label.setText(f"\u5171 {count} \u4e2a\u4f1a\u8bdd\u3002")
        if self._selected_source == ChatSource.QQ:
            self.status_changed.emit(
                self._last_qq_status_message
                or _QQ_STATE_MESSAGES[_QQ_STATE_CONNECTED]
            )
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
            item.setToolTip(
                f"\u6d88\u606f\u6570\uff1a{session.message_count}"
            )
        self._session_list.addItem(item)

    @staticmethod
    def _recent_session_key(pair: tuple[int, Any]) -> tuple[int, int, int]:
        index, session = pair
        timestamp = getattr(session, "last_message_time", None)
        if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
            return (0, -int(timestamp), index)
        return (1, 0, index)

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
        if self._analysis_running:
            return
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
            item = self._session_list.currentItem()
            if (
                item is None
                or not (item.flags() & Qt.ItemFlag.ItemIsEnabled)
            ):
                return
            operation = lambda: self._facade.analyze_session(
                source,
                session_id,
                config,
            )

        self._set_busy(True)
        self.analysis_started.emit()
        self.status_changed.emit(_ANALYZING)
        QTimer.singleShot(0, lambda: self._submit_analysis(operation))

    def _submit_analysis(self, operation: Any) -> None:
        """Start expensive work only after Qt can paint the processing page."""
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
        self._analysis_running = busy
        self.setEnabled(not busy)
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
        item = self._session_list.currentItem()
        self._analyze_button.setEnabled(
            item is not None
            and bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
        )

def _snapshot_state(snapshot: Any) -> str:
    """Read the lifecycle state a connection snapshot resolved."""
    state = getattr(snapshot, "state", None)
    value = getattr(state, "value", state)
    return (
        value
        if value in _QQ_STATE_MESSAGES
        else _QQ_STATE_DISCONNECTED
    )


def _snapshot_prefix(snapshot: Any) -> str:
    """Pick the status dot that matches one lifecycle state."""
    state = _snapshot_state(snapshot)
    if state == _QQ_STATE_CONNECTED:
        return _CONNECTED_PREFIX
    if state in _QQ_PROGRESS_STATES or state == _QQ_STATE_WAITING_AUTH:
        return _QQ_PENDING_PREFIX
    return _DISCONNECTED_PREFIX


def _snapshot_message(snapshot: Any) -> str:
    message = getattr(snapshot, "message", "") or ""
    if message:
        return message
    return _QQ_STATE_MESSAGES.get(
        _snapshot_state(snapshot),
        _CONNECTION_STATUS_UNKNOWN,
    )


def _snapshot_hint(snapshot: Any) -> str:
    return getattr(snapshot, "action_hint", "") or ""


def _snapshot_in_progress(snapshot: Any) -> bool:
    return _snapshot_state(snapshot) in _QQ_PROGRESS_STATES


def _default_qq_qrcode_path() -> Path:
    """Return where the bundled QQ runtime writes its login QR image."""
    return default_qq_runtime_directory() / _QQ_QRCODE_RELATIVE_PATH
