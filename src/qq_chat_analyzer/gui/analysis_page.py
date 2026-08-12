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
    QButtonGroup,
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
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..application.facade import (
    AnalysisConfig,
    AnalysisScopeMode,
    ChatSource,
    WeChatEnvironmentConfig,
)
from ..resources import (
    default_qq_runtime_directory,
    default_wechat_login_guide_path,
)
from .workers import submit
from .wechat_setup_dialog import WeChatSetupDialog


SESSION_ID_ROLE = Qt.ItemDataRole.UserRole
SOURCE_ROLE = Qt.ItemDataRole.UserRole + 1

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.analysis_page")

_SELECT_SOURCE_HINT = "\u8bf7\u5148\u9009\u62e9\u6570\u636e\u6765\u6e90\u3002"
_LOADING_SESSIONS = "\u6b63\u5728\u52a0\u8f7d\u4f1a\u8bdd\u5217\u8868..."
_NO_SESSIONS = "\u8be5\u6765\u6e90\u6ca1\u6709\u53ef\u5206\u6790\u7684\u4f1a\u8bdd\u3002"
_SESSION_EMPTY_TITLE = "暂无会话"
_SESSION_EMPTY_DETAIL = "连接数据源后，这里会显示聊天记录"
_SESSION_CONNECTING_TITLE = "正在连接数据源..."
_SESSION_READING_TITLE = "正在读取聊天数据..."
_SESSION_NO_DATA_TITLE = "没有找到可分析的聊天记录"
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
_ANALYZING = "正在准备分析..."
_CANCEL_CONNECTION_LABEL = "取消连接"
_RESTART_CONNECTION_LABEL = "重新开始"
_RETURN_SOURCE_LABEL = "返回数据源选择"
_CONNECTION_CANCELLED = "连接已取消，可以重新开始。"
_ANALYSIS_CANCELLED = "分析已取消。"
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
    "等待QQ登录\n\n请扫码登录QQ。\n"
    "QQ主窗口可能不会正常显示，这是正常现象。\n\n"
    "不要手动启动QQ，也不要关闭连接窗口。\n"
    "登录成功后，余音会自动继续。"
)
_QQ_STARTING_GUIDE = (
    "首次连接 QQ 时，系统可能弹出权限确认窗口。\n\n"
    "这是 Echo 内置的 QQ 数据读取组件，用于分析你的聊天记录，"
    "请允许它运行。\n"
    "聊天数据仅在本机处理，不会上传。\n\n"
    "请不要手动打开QQ。余音会自动启动QQ环境，随后提示扫码登录。"
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
    "正在准备微信连接\n\n请确保微信电脑版已安装。\n"
    "如需查看微信数据目录，完成后请退出微信账号，返回登录界面。"
)
_WECHAT_GUIDE_KEY = (
    "等待微信登录<br><br>"
    "<span style='color:#c2410c;font-weight:600'>"
    "请保持微信停留在登录界面，不要点击进入微信"
    "</span><br>"
    "不要进入聊天页面、切换账号或关闭微信。<br>"
    "登录成功后，余音会自动继续。<br>"
    "聊天数据仅在本机读取，不上传、不保存额外副本。"
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
_WECHAT_READING_DATABASE = "\u6b63\u5728\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u5e93..."
_WECHAT_LOADING_SESSIONS = "\u6b63\u5728\u52a0\u8f7d\u5fae\u4fe1\u4f1a\u8bdd..."
_WECHAT_WAITING_LOGIN = "\u7b49\u5f85\u5fae\u4fe1\u767b\u5f55"
_WECHAT_KEY_ACQUIRING = "Key \u83b7\u53d6\u4e2d"
_WECHAT_DATABASE_FAILED = "\u5fae\u4fe1\u6570\u636e\u5e93\u8bfb\u53d6\u5931\u8d25"
_WECHAT_SESSIONS_FAILED = "\u5fae\u4fe1\u4f1a\u8bdd\u52a0\u8f7d\u5931\u8d25"
_WECHAT_GUIDE_IMAGE_WIDTH = 160
_WECHAT_GUIDE_IMAGE_HEIGHT = 220


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
        wechat_guide_image_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._facade = facade
        self._executor = executor or submit
        self._selected_source: ChatSource | None = None
        self._selected_file: Path | None = None
        self._analysis_running = False
        self._analysis_task: Any = None
        self._connection_task: Any = None
        self._source_enabled_before_lock: dict[ChatSource, bool] = {}
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
        self._wechat_guide_image_path = (
            Path(wechat_guide_image_path)
            if wechat_guide_image_path is not None
            else default_wechat_login_guide_path()
        )
        self._qq_status_timer = QTimer(self)
        self._qq_status_timer.setInterval(_QQ_STATUS_POLL_INTERVAL_MS)
        self._qq_status_timer.timeout.connect(self._poll_qq_status)

        self._build_ui()
        self.refresh_sources()
        self._show_unconnected_session_placeholder()

    # ------------------------------------------------------------------ setup

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._source_box = QGroupBox("\u6570\u636e\u6765\u6e90")
        self._source_layout = QHBoxLayout(self._source_box)
        layout.addWidget(self._source_box)

        self._return_source_button = QPushButton(_RETURN_SOURCE_LABEL)
        self._return_source_button.setVisible(False)
        self._return_source_button.clicked.connect(
            self.return_to_source_selection
        )
        layout.addWidget(self._return_source_button)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        self._status_label.setStyleSheet(
            "padding: 8px 10px; border-radius: 6px; "
            "background: palette(alternate-base);"
        )
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

        self._wechat_guide_image_label = QLabel("")
        self._wechat_guide_image_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self._wechat_guide_image_label.setVisible(False)
        layout.addWidget(self._wechat_guide_image_label)

        self._wechat_guide_label = QLabel("")
        self._wechat_guide_label.setWordWrap(False)
        self._wechat_guide_label.setMinimumWidth(480)
        self._wechat_guide_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._wechat_guide_label.setVisible(False)
        self._wechat_guide_label.setStyleSheet(
            "padding: 10px; border-radius: 6px; "
            "background: palette(alternate-base);"
        )
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
        self._qq_login_guide_label.setStyleSheet(
            "padding: 10px; border-radius: 6px; "
            "background: palette(alternate-base);"
        )
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

        self._session_box = QGroupBox("\u4f1a\u8bdd")
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

        range_box = QGroupBox("分析范围")
        range_layout = QVBoxLayout(range_box)
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

        self._custom_range_widget = QWidget(range_box)
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
        layout.addWidget(range_box)

        self._analyze_button = QPushButton("\u5f00\u59cb\u5206\u6790")
        self._analyze_button.setEnabled(False)
        self._analyze_button.clicked.connect(self.start_analysis)
        layout.addWidget(self._analyze_button)

        self._hint_label = QLabel(_SELECT_SOURCE_HINT)
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)

        for button in (
            self._return_source_button,
            self._wechat_connect_button,
            self._wechat_setup_button,
            self._qq_connect_button,
            self._file_button,
            self._analyze_button,
        ):
            button.setMinimumHeight(34)

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
        if self._connection_task is not None or self._analysis_running:
            return
        source = ChatSource(source)
        self._clear_connection_view()
        self._selected_source = source
        self._selected_file = None
        self._file_label.setText("")
        self._return_source_button.setVisible(True)
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
        if source == ChatSource.WECHAT:
            self._show_wechat_guide()
        else:
            self._wechat_guide_label.clear()
            self._hide_wechat_guide_image()
        self._qq_connect_button.setVisible(source == ChatSource.QQ)
        self._qq_connect_button.setEnabled(True)
        self._qq_connect_button.setToolTip("")
        if is_local:
            self._status_label.setVisible(False)
            self._hint_label.setText(_LOCAL_FILE_HINT)
            self._session_list.clear()
            self._update_analyze_enabled()
            return

        if source == ChatSource.QQ:
            self._session_list.clear()
            self.refresh_qq_status(load_sessions_on_ready=True)
            return

        self._session_list.clear()
        self.refresh_connection_status(source, load_sessions_on_ready=True)

    def return_to_source_selection(self) -> None:
        """Abandon the current view without closing an external chat client."""
        if self._analysis_running:
            return
        task = self._connection_task
        cancel = getattr(task, "cancel", None)
        if callable(cancel):
            cancel()
        self._connection_task = None
        self._qq_connect_in_flight = False
        self._wechat_connect_pending = False
        self._stop_qq_status_polling()
        self._lock_sources(False)
        self._selected_source = None
        for button in self._source_buttons.values():
            button.setChecked(False)
        self._clear_connection_view()
        self._return_source_button.setVisible(False)
        self._hint_label.setText(_SELECT_SOURCE_HINT)
        self._show_unconnected_session_placeholder()

    def _clear_connection_view(self) -> None:
        """Clear source-specific presentation state before changing source."""
        self._sessions = []
        self._message_range = None
        self._last_qq_status_message = ""
        self._selected_file = None
        self._file_label.clear()
        self._session_search.blockSignals(True)
        self._session_search.clear()
        self._session_search.blockSignals(False)
        self._session_sort.blockSignals(True)
        self._session_sort.setCurrentIndex(0)
        self._session_sort.blockSignals(False)
        self._session_list.clear()
        self._session_box.setVisible(False)
        self._status_label.clear()
        self._status_label.setToolTip("")
        self._status_label.setVisible(False)
        self._file_button.setVisible(False)
        self._file_label.setVisible(False)
        self._qq_connect_button.setText(_QQ_CONNECT_LABEL)
        self._qq_connect_button.setVisible(False)
        self._wechat_connect_button.setText(_WECHAT_CONNECT_LABEL)
        self._wechat_connect_button.setVisible(False)
        self._wechat_setup_button.setVisible(False)
        self._wechat_guide_label.clear()
        self._wechat_guide_label.setVisible(False)
        self._hide_wechat_guide_image()
        self._hide_qq_qrcode()
        self._hide_qq_login_guide()
        self._set_session_controls_ready(False)
        self._update_analyze_enabled()

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
        self._show_session_placeholder(_SESSION_CONNECTING_TITLE)
        if load_sessions_on_ready:
            self._hint_label.setText("")
        self._executor(
            lambda: self._facade.get_connection_status(source),
            on_success=lambda status: self._show_connection_status(
                source,
                status,
                load_sessions_on_ready,
            ),
            on_error=lambda code, message: self._handle_source_status_error(
                source,
                code,
                message,
            ),
        )

    def _show_connection_status(
        self,
        source: ChatSource,
        status: Any,
        load_sessions_on_ready: bool,
    ) -> None:
        """Render one source's connection status returned by the facade."""
        if self._selected_source != source:
            return
        available = bool(getattr(status, "available", False))
        prefix = _CONNECTED_PREFIX if available else _DISCONNECTED_PREFIX
        if source == ChatSource.WECHAT:
            message = (
                _WECHAT_STATUS_CONNECTED
                if available
                else _wechat_unavailable_message(status)
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
            self._wechat_setup_button.setVisible(False)
            if available:
                self._wechat_guide_label.setVisible(False)
                self._hide_wechat_guide_image()
            else:
                self._show_wechat_guide()
            self._wechat_connect_button.setText(_WECHAT_CONNECT_LABEL)
            self._wechat_connect_button.setVisible(not available)
        elif source == ChatSource.QQ:
            self._qq_connect_button.setText(_QQ_CONNECT_LABEL)
            self._qq_connect_button.setVisible(not available)
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
            loading_message = (
                _WECHAT_LOADING_SESSIONS
                if source == ChatSource.WECHAT
                else _LOADING_SESSIONS
            )
            if source == ChatSource.WECHAT:
                self._status_label.setText(loading_message)
            self._hint_label.setText(loading_message)
            self._show_session_placeholder(_SESSION_READING_TITLE)
            if source != ChatSource.WECHAT:
                self.status_changed.emit(_LOADING_SESSIONS)
            self._load_sessions(source)
        elif not available:
            self._show_disconnected_session_placeholder(source)

    def _show_wechat_guide(
        self,
        *,
        include_directory_help: bool = False,
    ) -> None:
        """Render the first-time WeChat connection guide."""
        parts = [_WECHAT_GUIDE_STATUS, _WECHAT_GUIDE_KEY]
        if include_directory_help:
            parts.append(_WECHAT_GUIDE_DIRECTORY_MISSING)
        self._wechat_guide_label.setText("<br><br>".join(parts))
        self._wechat_guide_label.setVisible(True)

        self._refresh_wechat_guide_image()

    def _refresh_wechat_guide_image(self) -> None:
        """Load the optional guide image without making connection depend on it."""
        if not self._wechat_guide_image_path.is_file():
            self._hide_wechat_guide_image()
            return
        try:
            pixmap = QPixmap(str(self._wechat_guide_image_path))
        except Exception:
            pixmap = QPixmap()
        if pixmap.isNull():
            self._hide_wechat_guide_image()
            return
        scaled = pixmap.scaled(
            _WECHAT_GUIDE_IMAGE_WIDTH,
            _WECHAT_GUIDE_IMAGE_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._wechat_guide_image_label.setPixmap(scaled)
        self._wechat_guide_image_label.setVisible(True)

    def _hide_wechat_guide_image(self) -> None:
        self._wechat_guide_image_label.clear()
        self._wechat_guide_image_label.setVisible(False)

    def _handle_source_status_error(
        self,
        source: ChatSource,
        code: str,
        message: str,
    ) -> None:
        if self._selected_source != source:
            return
        self._handle_connection_status_error(code, message)

    def _handle_connection_status_error(self, code: str, message: str) -> None:
        if self._qq_connect_in_flight and self._selected_source == ChatSource.QQ:
            return
        self._status_label.setText(_CONNECTION_STATUS_UNKNOWN)
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self._hint_label.setText(message)
        self._session_list.clear()
        if self._selected_source in (ChatSource.QQ, ChatSource.WECHAT):
            self._show_disconnected_session_placeholder(self._selected_source)
            self._set_restart_action(self._selected_source)
        self._update_analyze_enabled()

    def refresh_qq_status(self, *, load_sessions_on_ready: bool = False) -> None:
        """Ask the connection manager, through the facade, for QQ state."""
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_STATUS_CHECKING)
        self._status_label.setToolTip("")
        self._show_session_placeholder(_SESSION_CONNECTING_TITLE)
        self._update_analyze_enabled()
        self._executor(
            lambda: self._facade.get_qq_connection_snapshot(),
            on_success=lambda snapshot: self._show_qq_status(
                snapshot,
                load_sessions_on_ready,
            ),
            on_error=lambda code, message: self._handle_source_status_error(
                ChatSource.QQ,
                code,
                message,
            ),
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
        if self._selected_source != ChatSource.QQ or self._qq_connect_in_flight:
            return
        state = _snapshot_state(snapshot)
        message = _snapshot_message(snapshot)
        action_hint = _snapshot_hint(snapshot)
        self._last_qq_status_message = message

        self._status_label.setText(f"{_snapshot_prefix(snapshot)}{message}")
        self._status_label.setToolTip(action_hint)
        self._status_label.setVisible(True)
        self._qq_connect_button.setText(_QQ_CONNECT_LABEL)
        self._qq_connect_button.setVisible(state != _QQ_STATE_CONNECTED)
        if state == _QQ_STATE_ERROR:
            self._qq_connect_button.setText(_RESTART_CONNECTION_LABEL)
        self._qq_connect_button.setEnabled(not _snapshot_in_progress(snapshot))
        self._qq_connect_button.setToolTip("")
        self._session_list.clear()
        self._update_analyze_enabled()

        if load_sessions_on_ready:
            self._hint_label.setText(action_hint)
            self.status_changed.emit(message)

        if state == _QQ_STATE_CONNECTED and load_sessions_on_ready:
            self._hint_label.setText(_LOADING_SESSIONS)
            self._show_session_placeholder(_SESSION_READING_TITLE)
            self.status_changed.emit(_LOADING_SESSIONS)
            self._load_sessions(ChatSource.QQ)
        elif state in _QQ_PROGRESS_STATES or state == _QQ_STATE_WAITING_AUTH:
            self._show_session_placeholder(_SESSION_CONNECTING_TITLE)
        elif state != _QQ_STATE_CONNECTED:
            self._show_disconnected_session_placeholder(ChatSource.QQ)

        if state == _QQ_STATE_WAITING_AUTH:
            self._show_qq_login_guide()
            self._start_qq_status_polling()
            self._refresh_qq_qrcode()
        elif state in _QQ_PROGRESS_STATES:
            self._show_qq_starting_guide()
            self._stop_qq_status_polling()
            self._hide_qq_qrcode()
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

    def _show_qq_starting_guide(self) -> None:
        """Explain the expected Windows prompt before QQ login begins."""
        self._qq_login_guide_label.setText(_QQ_STARTING_GUIDE)
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
        if self._qq_connect_in_flight:
            self.cancel_connection()
            return
        _LOGGER.info(
            "[qq gui] connect_qq requested selected_source=%r",
            self._selected_source,
        )
        started_at = time.monotonic()
        self._qq_connect_in_flight = True
        self._lock_sources(True)
        self._qq_connect_button.setText(_CANCEL_CONNECTION_LABEL)
        self._qq_connect_button.setEnabled(True)
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_CONNECTING)
        self._status_label.setToolTip("")
        self._hint_label.setText(_QQ_CONNECT_PREPARE)
        self._show_qq_starting_guide()
        self._show_session_placeholder(_SESSION_CONNECTING_TITLE)
        self.status_changed.emit(_QQ_CONNECTING)
        _LOGGER.info("[qq gui] connect_qq worker submitted")
        self._connection_task = self._executor(
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
            on_progress=lambda message: (
                self._handle_qq_connect_progress(message)
                if self._selected_source == ChatSource.QQ
                else None
            ),
        )

    def _handle_qq_connect_progress(self, message: str) -> None:
        """Translate backend progress into one of the user-facing stages."""
        if not message:
            return
        stage, hint = _qq_progress_copy(message)
        self._status_label.setText(_QQ_PENDING_PREFIX + stage)
        self._status_label.setToolTip("")
        self._status_label.setVisible(True)
        self._hint_label.setText(hint)
        if stage == "等待QQ登录":
            self._show_qq_login_guide()
        else:
            self._show_qq_starting_guide()
        self.status_changed.emit(stage)

    def _after_qq_connect(self, snapshot: Any) -> None:
        self._show_qq_status(snapshot, load_sessions_on_ready=True)

    def _finish_qq_connect(self, status: Any, started_at: float) -> None:
        def _apply() -> None:
            if self._selected_source != ChatSource.QQ:
                return
            self._qq_connect_in_flight = False
            self._connection_task = None
            self._lock_sources(False)
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
            if self._selected_source != ChatSource.QQ:
                return
            self._qq_connect_in_flight = False
            self._connection_task = None
            self._lock_sources(False)
            _LOGGER.info("[qq gui] connect_qq failed code=%s", code)
            self._handle_qq_connect_error(code, message)
            self._qq_connect_button.setEnabled(True)

        QTimer.singleShot(self._connect_display_delay(started_at), _apply)

    @staticmethod
    def _connect_display_delay(started_at: float) -> int:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        return max(0, _QQ_CONNECT_MIN_DISPLAY_MS - elapsed_ms)

    def _handle_qq_connect_error(self, code: str, message: str) -> None:
        self._show_qq_error(_qq_error_title(code), message)

    def _show_qq_error(self, title: str, message: str) -> None:
        self._status_label.setText(_DISCONNECTED_PREFIX + title)
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self._hint_label.setText(message)
        self._show_disconnected_session_placeholder(ChatSource.QQ)
        self._set_restart_action(ChatSource.QQ)
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
        if self._connection_task is not None:
            self.cancel_connection()
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
        self._lock_sources(True)
        self._wechat_connect_button.setText(_CANCEL_CONNECTION_LABEL)
        self._wechat_connect_button.setEnabled(True)
        self._status_label.setVisible(True)
        self._status_label.setText(_WECHAT_CONNECTING)
        self._status_label.setToolTip("")
        self._hint_label.setText(_WECHAT_LOGIN_PREPARE)
        self._show_wechat_guide()
        self._show_session_placeholder(_SESSION_CONNECTING_TITLE)
        self.status_changed.emit(_WECHAT_CONNECTING)

        self._connection_task = self._executor(
            lambda report: self._connect_wechat_operation(config, report),
            on_success=self._after_wechat_key_acquired,
            on_error=lambda code, message: (
                self._handle_wechat_connect_error(code, message)
                if self._selected_source is ChatSource.WECHAT
                else None
            ),
            on_progress=lambda message: (
                self._handle_wechat_connect_progress(message)
                if self._selected_source is ChatSource.WECHAT
                else None
            ),
            on_finished=self._finish_wechat_connect,
        )

    def _finish_wechat_connect(self) -> None:
        self._connection_task = None
        self._lock_sources(False)
        self._wechat_connect_button.setEnabled(True)
        if self._selected_source is ChatSource.WECHAT:
            connected = self._status_label.text().startswith(_CONNECTED_PREFIX)
            self._wechat_connect_button.setVisible(not connected)
            if not connected and self._wechat_connect_button.text() == (
                _CANCEL_CONNECTION_LABEL
            ):
                self._wechat_connect_button.setText(_RESTART_CONNECTION_LABEL)

    def cancel_connection(self) -> None:
        """Cancel the active source task and return to a reconnectable page."""
        task = self._connection_task
        if task is None and not self._qq_connect_in_flight:
            return
        cancel = getattr(task, "cancel", None)
        if callable(cancel):
            cancel()
        if self._selected_source is ChatSource.QQ:
            shutdown = getattr(self._facade, "shutdown_qq_runtime", None)
            if callable(shutdown):
                shutdown()
        self._connection_task = None
        self._qq_connect_in_flight = False
        self._wechat_connect_pending = False
        self._stop_qq_status_polling()
        self._hide_qq_qrcode()
        self._hide_qq_login_guide()
        self._lock_sources(False)
        self._qq_connect_button.setText(_QQ_CONNECT_LABEL)
        self._wechat_connect_button.setText(_WECHAT_CONNECT_LABEL)
        self._qq_connect_button.setEnabled(True)
        self._wechat_connect_button.setEnabled(True)
        self._status_label.setText(_CONNECTION_CANCELLED)
        self._status_label.setVisible(True)
        self._hint_label.setText(_CONNECTION_CANCELLED)
        self.status_changed.emit(_CONNECTION_CANCELLED)

    def _lock_sources(self, locked: bool) -> None:
        if locked:
            self._source_enabled_before_lock = {
                source: button.isEnabled()
                for source, button in self._source_buttons.items()
            }
            for button in self._source_buttons.values():
                button.setEnabled(False)
            return
        if not self._source_enabled_before_lock:
            return
        for source, button in self._source_buttons.items():
            button.setEnabled(self._source_enabled_before_lock.get(source, True))
        self._source_enabled_before_lock.clear()

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
        self._facade.acquire_wechat_db_key(progress=progress)
        if progress is not None:
            progress(_WECHAT_READING_DATABASE)
        return self._facade.get_connection_status(ChatSource.WECHAT)

    def _after_wechat_key_acquired(self, status: Any) -> None:
        self._show_connection_status(
            ChatSource.WECHAT,
            status,
            load_sessions_on_ready=True,
        )

    def _handle_wechat_connect_progress(self, message: str) -> None:
        """Keep the unified connecting status while showing progress detail."""
        _LOGGER.debug("[wechat gui] received progress: %s", message)
        self._status_label.setVisible(True)
        if message == _WECHAT_READING_DATABASE:
            stage = _WECHAT_READING_DATABASE
            self._show_session_placeholder(_SESSION_READING_TITLE)
        elif "\u767b\u5f55" in message:
            stage = _WECHAT_WAITING_LOGIN
            self._show_session_placeholder(_SESSION_CONNECTING_TITLE)
        else:
            stage = _WECHAT_KEY_ACQUIRING
            self._show_session_placeholder(_SESSION_CONNECTING_TITLE)
        self._status_label.setText(stage)
        self._hint_label.setText(message)

    def _handle_wechat_connect_error(self, code: str, message: str) -> None:
        """Show the classified application failure without flattening it."""
        detail = message or ""
        lowered = detail.lower()
        titles = {
            "wechat_environment_missing": "\u5fae\u4fe1\u8fde\u63a5\u73af\u5883\u4e0d\u5b8c\u6574",
            "wechat_not_running": "\u5fae\u4fe1\u672a\u542f\u52a8",
            "wechat_waiting_login": "\u7b49\u5f85\u5fae\u4fe1\u767b\u5f55",
            "wechat_hook_failed": "\u6b63\u5728\u83b7\u53d6\u6743\u9650\u65f6\u5931\u8d25",
            "wechat_process_incompatible": "\u5fae\u4fe1\u8fdb\u7a0b\u4e0d\u517c\u5bb9",
            "wechat_key_timeout": "Key \u83b7\u53d6\u5931\u8d25",
            "key_timeout": "Key \u83b7\u53d6\u5931\u8d25",
        }
        if code not in titles and any(
            term in lowered for term in _WECHAT_INTERNAL_TERMS
        ):
            detail = ""
        text = detail or _WECHAT_CONNECT_RETRY_HINT
        self._status_label.setText(
            _DISCONNECTED_PREFIX + titles.get(code, _WECHAT_CONNECT_FAILED)
        )
        self._status_label.setToolTip(text)
        self._status_label.setVisible(True)
        self._hint_label.setText(text)
        self._show_disconnected_session_placeholder(ChatSource.WECHAT)
        self._set_restart_action(ChatSource.WECHAT)
        self.status_changed.emit(text)

    def _set_restart_action(self, source: ChatSource) -> None:
        button = (
            self._qq_connect_button
            if source == ChatSource.QQ
            else self._wechat_connect_button
        )
        button.setText(_RESTART_CONNECTION_LABEL)
        button.setEnabled(True)
        button.setVisible(self._selected_source == source)

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
        if self._selected_source is ChatSource.WECHAT:
            self._set_restart_action(ChatSource.WECHAT)
        self.status_changed.emit(message)

    def _load_sessions(self, source: ChatSource) -> None:
        self._executor(
            lambda: self._facade.list_sessions(source),
            on_success=lambda sessions: self._handle_source_sessions_loaded(
                source,
                sessions,
            ),
            on_error=lambda code, message: self._handle_source_session_error(
                source,
                code,
                message,
            ),
        )

    def _handle_source_sessions_loaded(
        self,
        source: ChatSource,
        sessions: Any,
    ) -> None:
        if self._selected_source != source:
            return
        if source == ChatSource.WECHAT:
            self._handle_wechat_sessions_loaded(sessions)
        else:
            self._populate_sessions(sessions)

    def _handle_source_session_error(
        self,
        source: ChatSource,
        code: str,
        message: str,
    ) -> None:
        if self._selected_source != source:
            return
        if source == ChatSource.WECHAT:
            self._handle_wechat_session_error(code, message)
        else:
            self._handle_error(code, message)

    def _handle_wechat_sessions_loaded(self, sessions: Any) -> None:
        self._populate_sessions(sessions)
        self._status_label.setText(_CONNECTED_PREFIX + _WECHAT_STATUS_CONNECTED)
        self._status_label.setToolTip("")
        self._status_label.setVisible(True)
        self._wechat_guide_label.setVisible(False)
        self._hide_wechat_guide_image()
        self._wechat_connect_button.setVisible(False)

    def _handle_wechat_session_error(self, code: str, message: str) -> None:
        database_codes = {
            "database_not_found",
            "key_unavailable",
            "query_failed",
            "wechat_database_error",
            "wcdb_helper_not_found",
            "wcdb_library_not_found",
        }
        title = (
            _WECHAT_DATABASE_FAILED
            if code in database_codes
            else _WECHAT_SESSIONS_FAILED
        )
        detail = message or _WECHAT_CONNECT_RETRY_HINT
        self._status_label.setText(_DISCONNECTED_PREFIX + title)
        self._status_label.setToolTip(detail)
        self._status_label.setVisible(True)
        self._hint_label.setText(detail)
        self._set_restart_action(ChatSource.WECHAT)
        self.status_changed.emit(detail)

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
            edit.setDate(
                QDate.fromString(date_text, "yyyy-MM-dd")
            )
        else:
            edit.setDate(QDate.currentDate())

    def _on_custom_scope_toggled(self, checked: bool) -> None:
        self._custom_range_widget.setVisible(checked)
        if checked:
            self._apply_date_default(self._start_date, 0)
            self._apply_date_default(self._end_date, 1)

    def _populate_sessions(self, sessions: Any) -> None:
        """Fill the list with sessions, keeping ids out of the visible text."""
        self._sessions = list(sessions or ())
        self._set_session_controls_ready(True)
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
            self._show_session_placeholder(
                _NO_MATCHING_SESSIONS,
                session_controls_ready=True,
                session_container_visible=True,
            )
        elif count == 0:
            self._hint_label.setText(_NO_SESSIONS)
            self._show_session_placeholder(
                _SESSION_NO_DATA_TITLE,
                session_controls_ready=True,
            )
        else:
            self._session_box.setVisible(True)
            self._hint_label.setText(f"\u5171 {count} \u4e2a\u4f1a\u8bdd\u3002")
        if self._selected_source == ChatSource.QQ:
            self.status_changed.emit(
                self._last_qq_status_message
                or _QQ_STATE_MESSAGES[_QQ_STATE_CONNECTED]
            )
        self._update_analyze_enabled()

    def _show_disconnected_session_placeholder(self, source: ChatSource) -> None:
        self._show_unconnected_session_placeholder()

    def _show_unconnected_session_placeholder(self) -> None:
        self._show_session_placeholder(
            _SESSION_EMPTY_TITLE,
            _SESSION_EMPTY_DETAIL,
        )

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
        text = f"{title}\n{detail}" if detail else title
        item = QListWidgetItem(text)
        item.setFlags(
            item.flags()
            & ~Qt.ItemFlag.ItemIsEnabled
            & ~Qt.ItemFlag.ItemIsSelectable
        )
        self._session_list.addItem(item)
        self._update_analyze_enabled()

    def _set_session_controls_ready(self, ready: bool) -> None:
        self._session_search.setEnabled(ready)
        self._session_sort.setEnabled(ready)

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
            operation = lambda report: self._facade.analyze_file(
                path,
                config,
                progress=report,
            )
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

    def _submit_analysis(self, operation: Any) -> None:
        """Start expensive work only after Qt can paint the processing page."""
        self._analysis_task = self._executor(
            operation,
            on_success=self._handle_success,
            on_error=self._handle_error,
            on_finished=self._finish_analysis,
            on_progress=self._handle_analysis_progress,
        )

    def _handle_analysis_progress(self, message: str) -> None:
        """Display a stage supplied by the facade without deriving state."""
        if message:
            self.status_changed.emit(message)

    def _finish_analysis(self) -> None:
        self._analysis_task = None
        self._set_busy(False)

    def cancel_analysis(self) -> None:
        """Cancel the active analysis and restore all selection controls."""
        if not self._analysis_running:
            return
        cancel = getattr(self._analysis_task, "cancel", None)
        if callable(cancel):
            cancel()
        self._analysis_task = None
        self._set_busy(False)
        self._hint_label.setText(_ANALYSIS_CANCELLED)
        self.status_changed.emit(_ANALYSIS_CANCELLED)

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

def _wechat_unavailable_message(status: Any) -> str:
    if not bool(getattr(status, "runtime_available", False)):
        return "\u5fae\u4fe1\u8fde\u63a5\u73af\u5883\u4e0d\u5b58\u5728"
    if not bool(getattr(status, "data_found", False)):
        return "\u5fae\u4fe1\u6570\u636e\u5e93\u672a\u5c31\u7eea"
    if not bool(getattr(status, "db_key_available", False)):
        return _WECHAT_WAITING_LOGIN
    return getattr(status, "message", "") or _WECHAT_STATUS_DISCONNECTED


def _qq_progress_copy(message: str) -> tuple[str, str]:
    lowered = message.lower()
    if any(term in lowered for term in ("扫码", "登录", "auth", "qrcode")):
        return "等待QQ登录", _QQ_LOGIN_GUIDE
    return "正在启动QQ连接环境", _QQ_STARTING_GUIDE


def _qq_error_title(code: str) -> str:
    if code in {"qq_not_installed", "qq_runtime_missing", "runtime_unavailable"}:
        return "QQ连接环境启动失败"
    if code in {"qq_login_timeout", "qq_auth_failed", "authentication_failed"}:
        return "QQ登录失败"
    if code in {"qce_unavailable", "qce_start_failed", "service_unavailable"}:
        return "QQ连接服务启动失败"
    return _QQ_CONNECT_FAILED


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
