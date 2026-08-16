"""WeChat workspace: connection, setup guide, and session analysis."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..application.facade import ChatSource, WeChatEnvironmentConfig
from ..resources import default_wechat_login_guide_path
from .session_analysis_panel import SessionAnalysisPanel
from .theme import (
    GUIDE_STYLE,
    GUIDE_STYLE_EMPHASIS,
    STATUS_STYLE_BASE,
    STATUS_STYLE_ERROR,
)
from .wechat_setup_dialog import WeChatSetupDialog
from .workers import submit


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.wechat_workspace")

_WECHAT_CONNECT_LABEL = "连接微信"
_CANCEL_CONNECTION_LABEL = "取消连接"
_RESTART_CONNECTION_LABEL = "重新开始"
_WECHAT_SETUP_LABEL = "微信环境设置..."
_WECHAT_STATUS_DISCONNECTED = "微信未连接"
_WECHAT_STATUS_CONNECTING = "正在连接微信..."
_WECHAT_STATUS_CONNECTED = "微信已连接。"
_WECHAT_CONNECTING = _WECHAT_STATUS_CONNECTING
_WECHAT_CONNECT_FAILED = "微信连接未成功"
_WECHAT_DISCONNECT_LABEL = "退出连接"
_WECHAT_DISCONNECTING = "正在退出微信连接..."
_WECHAT_DISCONNECT_FAILED = "微信退出连接失败"
_WECHAT_CONNECT_RETRY_HINT = (
    "请退出并重新打开微信，保持在登录界面后返回 Echo 重试连接。"
)
_WECHAT_GUIDE_STATUS = "微信连接准备中，正在等待一次新的微信登录事件。"
_WECHAT_GUIDE_KEY = "请从微信登录界面登录"
_WECHAT_GUIDE_WARNING = (
    "Echo 会在登录瞬间获取连接信息。"
    "如果微信已经登录，请退出微信，重新打开至登录界面，"
    "返回 Echo 重新连接微信；连接开始后，再从登录界面登录。"
)
_WECHAT_GUIDE_NOTE = (
    "聊天数据仅在本机读取，不上传、不保存额外副本。"
)
_WECHAT_GUIDE_DIRECTORY_MISSING = (
    "如未在常用位置找到微信数据位置，请按以下步骤获取微信数据目录："
)
_WECHAT_GUIDE_DIRECTORY_NOTE = (
    "1. 进入微信：设置 → 存储位置 → 更改；\n"
    "2. 右键 xwechat_files，选择 复制地址；\n"
    "3. 彻底退出微信，并重新打开微信，使微信回到登录界面（如图片所示）；\n"
    "4. 返回 Echo，将复制的地址直接粘贴到上方输入框；\n"
    "5. 点击 Save；\n"
    "6. Save 后 Echo 会立即开始等待微信登录；\n"
    "7. 此时再从微信登录界面登录。"
)
_WECHAT_DETECTED = "✓ 已检测到微信数据位置，无需手动选择路径。"
_WECHAT_NOT_DETECTED = "未在常用位置找到微信数据位置。"
_WECHAT_MULTIPLE_DETECTED = (
    "检测到多个微信聊天记录位置，请选择其中一个。"
)
_WECHAT_READING_DATABASE = "正在读取微信数据库..."
_WECHAT_LOADING_SESSIONS = "正在加载微信会话..."
_WECHAT_WAITING_LOGIN = "等待微信登录"
_WECHAT_KEY_ACQUIRING = "Key 获取中"
_WECHAT_DATABASE_FAILED = "微信数据库读取失败"
_WECHAT_SESSIONS_FAILED = "微信会话加载失败"
_WECHAT_INTERNAL_TERMS = (
    "db_key",
    "dbkey",
    "hook",
    "runtime",
    "dll",
    "wcdb",
    "密钥",
)
_WECHAT_GUIDE_IMAGE_WIDTH = 160
_WECHAT_GUIDE_IMAGE_HEIGHT = 220
_CONNECTED_PREFIX = "\U0001F7E2 "
_DISCONNECTED_PREFIX = "\U0001F534 "
_CONNECTION_STATUS_LOADING = "正在检测 {source} 连接状态..."
_SESSION_CONNECTING_TITLE = "正在连接数据源..."
_SESSION_READING_TITLE = "正在读取聊天数据..."


class WeChatWorkspace(QWidget):
    """WeChat workspace: connection, setup guide, and session analysis.

    This workspace mirrors the WeChat half of the GUI-2 AnalysisPage
    lifecycle: status through ``get_connection_status(WECHAT)``, one-click
    connect through data-root detection plus environment/key acquisition,
    then session loading and analysis through the shared panel.
    """

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
        self._wechat_connect_pending = False
        self._connection_task: Any = None
        self._wechat_guide_image_path = default_wechat_login_guide_path()
        self._sessions_loaded = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        self._status_label.setStyleSheet(STATUS_STYLE_BASE)
        main_layout.addWidget(self._status_label)

        self._wechat_connect_button = QPushButton(_WECHAT_CONNECT_LABEL)
        self._wechat_connect_button.setVisible(False)
        self._wechat_connect_button.clicked.connect(self.connect_wechat)
        self._wechat_connect_button.setMinimumHeight(34)
        main_layout.addWidget(self._wechat_connect_button)

        self._wechat_disconnect_button = QPushButton(_WECHAT_DISCONNECT_LABEL)
        self._wechat_disconnect_button.setVisible(False)
        self._wechat_disconnect_button.clicked.connect(self.disconnect_wechat)
        self._wechat_disconnect_button.setMinimumHeight(34)
        main_layout.addWidget(self._wechat_disconnect_button)

        self._wechat_setup_button = QPushButton(_WECHAT_SETUP_LABEL)
        self._wechat_setup_button.setVisible(False)
        self._wechat_setup_button.clicked.connect(self.open_wechat_setup)
        self._wechat_setup_button.setMinimumHeight(34)
        main_layout.addWidget(self._wechat_setup_button)

        self._wechat_guide_image_label = QLabel("")
        self._wechat_guide_image_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self._wechat_guide_image_label.setMaximumWidth(
            _WECHAT_GUIDE_IMAGE_WIDTH
        )
        self._wechat_guide_image_label.setVisible(False)

        self._wechat_guide_label = QLabel("")
        self._wechat_guide_label.setWordWrap(True)
        self._wechat_guide_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._wechat_guide_label.setVisible(False)
        self._wechat_guide_label.setStyleSheet(GUIDE_STYLE)

        self._wechat_guide_key_label = QLabel("")
        self._wechat_guide_key_label.setWordWrap(True)
        self._wechat_guide_key_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._wechat_guide_key_label.setVisible(False)
        self._wechat_guide_key_label.setStyleSheet(GUIDE_STYLE_EMPHASIS)

        self._wechat_guide_note_label = QLabel("")
        self._wechat_guide_note_label.setWordWrap(True)
        self._wechat_guide_note_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._wechat_guide_note_label.setVisible(False)
        self._wechat_guide_note_label.setStyleSheet(GUIDE_STYLE)

        self._wechat_guide_text_column = QVBoxLayout()
        self._wechat_guide_text_column.setSpacing(8)
        self._wechat_guide_text_column.addWidget(
            self._wechat_guide_label,
            stretch=1,
        )
        self._wechat_guide_text_column.addWidget(
            self._wechat_guide_note_label,
            stretch=1,
        )
        self._wechat_guide_text_column.addWidget(
            self._wechat_guide_key_label,
            stretch=1,
        )

        self._wechat_guide_row = QHBoxLayout()
        self._wechat_guide_row.setSpacing(12)
        self._wechat_guide_row.addWidget(
            self._wechat_guide_image_label,
            stretch=0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )
        self._wechat_guide_row.addLayout(
            self._wechat_guide_text_column,
            stretch=1,
        )
        main_layout.addLayout(self._wechat_guide_row)

        self.session_panel = SessionAnalysisPanel()
        self.session_panel.configure(
            facade,
            ChatSource.WECHAT,
            executor=self._executor,
        )
        main_layout.addWidget(self.session_panel, stretch=1)

        self.session_panel.analysis_started.connect(self._on_analysis_started)
        self.session_panel.analysis_succeeded.connect(self.analysis_succeeded.emit)
        self.session_panel.analysis_failed.connect(self.analysis_failed.emit)
        self.session_panel.status_changed.connect(self._on_panel_status)

        self.session_panel.show_unconnected_placeholder()

    # ---------------------------------------------------------------- public API

    def select_source(self, source: Any) -> None:
        """Configure the panel for WeChat and reset transient state."""
        self.session_panel.configure(
            self._facade,
            ChatSource.WECHAT,
            executor=self._executor,
        )
        self._sessions_loaded = False
        self._wechat_disconnect_button.setVisible(False)
        self.session_panel.clear()

    def refresh_connection_status(
        self,
        *,
        load_sessions_on_ready: bool = False,
    ) -> None:
        """Ask the facade for WeChat's connection state and render it."""
        self._status_label.setVisible(True)
        self._status_label.setText(
            _CONNECTION_STATUS_LOADING.format(source="微信")
        )
        self._status_label.setToolTip("")
        self.session_panel.show_connecting_placeholder()
        if load_sessions_on_ready:
            self._executor(
                lambda: self._facade.get_connection_status(ChatSource.WECHAT),
                on_success=lambda status: self._show_connection_status(
                    status,
                    load_sessions_on_ready,
                ),
                on_error=lambda code, message: self._handle_connection_status_error(
                    code,
                    message,
                ),
            )

    def _handle_connection_status_error(self, code: str, message: str) -> None:
        self._status_label.setText(_DISCONNECTED_PREFIX + message)
        self._status_label.setToolTip("")
        self._status_label.setVisible(True)
        self.session_panel.show_disconnected_placeholder()
        self._wechat_connect_button.setVisible(True)
        self._wechat_setup_button.setVisible(True)
        self._wechat_disconnect_button.setVisible(False)
        self.session_panel.update_analyze_enabled()

    def _show_connection_status(
        self,
        status: Any,
        load_sessions_on_ready: bool,
    ) -> None:
        """Render WeChat's connection status returned by the facade."""
        available = bool(getattr(status, "available", False))
        prefix = _CONNECTED_PREFIX if available else _DISCONNECTED_PREFIX
        message = (
            _WECHAT_STATUS_CONNECTED
            if available
            else _wechat_unavailable_message(status)
        )
        action_hint = getattr(status, "action_hint", "") or ""
        self._status_label.setText(f"{prefix}{message}")
        self._status_label.setToolTip(action_hint)
        self._status_label.setVisible(True)

        self._wechat_setup_button.setVisible(False)
        if available:
            self._hide_wechat_guide()
        else:
            self._show_wechat_guide()
        self._wechat_connect_button.setText(_WECHAT_CONNECT_LABEL)
        self._wechat_connect_button.setVisible(not available)
        self._wechat_connect_button.setEnabled(True)
        self._wechat_disconnect_button.setVisible(available)
        self._wechat_disconnect_button.setEnabled(available)

        if load_sessions_on_ready:
            self.status_changed.emit(message)

        if available and load_sessions_on_ready:
            self._status_label.setText(_WECHAT_LOADING_SESSIONS)
            self.session_panel.show_reading_placeholder()
            self._load_sessions()
        elif not available:
            self.session_panel.show_disconnected_placeholder()

        if (
            load_sessions_on_ready
            and not available
            and not bool(getattr(status, "data_found", False))
            and self._connection_task is None
            and not self._wechat_connect_pending
        ):
            self.connect_wechat()

    # ---------------------------------------------------------------- guide

    def _show_wechat_guide(
        self,
        *,
        include_directory_help: bool = False,
    ) -> None:
        """Render the first-time WeChat connection guide with plain-text labels."""
        if include_directory_help:
            self._wechat_guide_label.setText(_WECHAT_GUIDE_DIRECTORY_MISSING)
            self._wechat_guide_note_label.setText(_WECHAT_GUIDE_DIRECTORY_NOTE)
            self._wechat_guide_note_label.setStyleSheet(GUIDE_STYLE_EMPHASIS)
            self._wechat_guide_key_label.clear()
            self._wechat_guide_key_label.setVisible(False)
        else:
            self._wechat_guide_label.setText(_WECHAT_GUIDE_STATUS)
            self._wechat_guide_note_label.setText(
                f"{_WECHAT_GUIDE_KEY}\n\n{_WECHAT_GUIDE_NOTE}"
            )
            self._wechat_guide_note_label.setStyleSheet(GUIDE_STYLE)
            self._wechat_guide_key_label.setText(_WECHAT_GUIDE_WARNING)
            self._wechat_guide_key_label.setVisible(True)
        self._wechat_guide_label.setVisible(True)
        self._wechat_guide_note_label.setVisible(True)

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

    def _hide_wechat_guide(self) -> None:
        self._wechat_guide_label.clear()
        self._wechat_guide_label.setVisible(False)
        self._wechat_guide_note_label.clear()
        self._wechat_guide_note_label.setVisible(False)
        self._wechat_guide_key_label.clear()
        self._wechat_guide_key_label.setVisible(False)
        self._hide_wechat_guide_image()

    # ---------------------------------------------------------------- connect

    def connect_wechat(
        self,
        detect_data_root: Any = None,
        detect_data_roots: Any = None,
    ) -> None:
        """Connect WeChat in one click, asking for a directory only if needed."""
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
        self._wechat_connect_button.setText(_CANCEL_CONNECTION_LABEL)
        self._wechat_connect_button.setEnabled(True)
        self._status_label.setVisible(True)
        self._status_label.setText(_WECHAT_CONNECTING)
        self._status_label.setToolTip("")
        self._show_wechat_guide()
        self.session_panel.show_connecting_placeholder()
        self.status_changed.emit(_WECHAT_CONNECTING)

        self._connection_task = self._executor(
            lambda report: self._connect_wechat_operation(config, report),
            on_success=self._after_wechat_key_acquired,
            on_error=lambda code, message: self._handle_wechat_connect_error(
                code,
                message,
            ),
            on_progress=self._handle_wechat_connect_progress,
            on_finished=self._finish_wechat_connect,
        )

    def _connect_wechat_operation(
        self,
        config: Any,
        progress: Any = None,
    ) -> Any:
        """Save the directory, then acquire the key. Runs off the UI thread."""
        self._facade.setup_wechat_environment(config)
        self._facade.acquire_wechat_db_key(progress=progress)
        if progress is not None:
            progress(_WECHAT_READING_DATABASE)
        return self._facade.get_connection_status(ChatSource.WECHAT)

    def _finish_wechat_connect(self) -> None:
        """Clean up after the WeChat connection attempt."""
        self._connection_task = None
        self._wechat_connect_button.setEnabled(True)
        connected = self._status_label.text().startswith(_CONNECTED_PREFIX)
        self._wechat_connect_button.setVisible(not connected)

    def _after_wechat_key_acquired(self, status: Any) -> None:
        self._show_connection_status(
            status,
            load_sessions_on_ready=True,
        )

    def _handle_wechat_connect_progress(self, message: str) -> None:
        """Keep the unified connecting status while showing progress detail."""
        _LOGGER.debug("[wechat gui] received progress: %s", message)
        self._status_label.setVisible(True)
        if message == _WECHAT_READING_DATABASE:
            stage = _WECHAT_READING_DATABASE
            self.session_panel.show_reading_placeholder()
        elif "登录" in message:
            stage = (
                "等待微信登录：当前等待的是一次新的微信登录事件。"
                "请从微信登录界面登录，Echo 会在登录瞬间获取连接信息。"
                "如果微信已经登录，请退出微信，重新打开至登录界面，"
                "返回 Echo 重新连接微信；连接开始后，再从登录界面登录。"
            )
            self.session_panel.show_connecting_placeholder()
        else:
            stage = _WECHAT_KEY_ACQUIRING
            self.session_panel.show_connecting_placeholder()
        self._status_label.setText(stage)

    def _handle_wechat_connect_error(self, code: str, message: str) -> None:
        """Show the classified application failure without flattening it."""
        detail = message or ""
        lowered = detail.lower()
        titles = {
            "wechat_environment_missing": "微信连接环境不完整",
            "wechat_not_running": "微信未启动",
            "wechat_waiting_login": "等待微信登录",
            "wechat_hook_failed": "正在获取权限时失败",
            "wechat_process_incompatible": "微信进程不兼容",
            "wechat_key_timeout": "Key 获取失败",
            "wechat_key_unavailable": "Key 获取失败",
            "key_timeout": "Key 获取失败",
            "database_not_found": _WECHAT_DATABASE_FAILED,
            "wechat_database_error": _WECHAT_DATABASE_FAILED,
            "wechat_invalid_environment": _WECHAT_DATABASE_FAILED,
            "query_failed": _WECHAT_DATABASE_FAILED,
            "wcdb_helper_not_found": _WECHAT_DATABASE_FAILED,
            "wcdb_library_not_found": _WECHAT_DATABASE_FAILED,
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
        self.session_panel.show_disconnected_placeholder()
        self._set_restart_action()
        self.status_changed.emit(text)

    def _set_restart_action(self) -> None:
        self._wechat_connect_button.setText(_RESTART_CONNECTION_LABEL)
        self._wechat_connect_button.setEnabled(True)
        self._wechat_connect_button.setVisible(True)
        self._wechat_disconnect_button.setVisible(False)

    def disconnect_wechat(self) -> None:
        """Release the current WeChat connection and return to reconnect."""
        if self._connection_task is not None:
            self.cancel_connection()
            return
        _LOGGER.info("[wechat gui] disconnect_wechat requested")
        self._wechat_disconnect_button.setEnabled(False)
        self._status_label.setVisible(True)
        self._status_label.setText(_WECHAT_DISCONNECTING)
        self._status_label.setToolTip("")
        self._hide_wechat_guide()
        self.session_panel.clear()
        self.status_changed.emit(_WECHAT_DISCONNECTING)
        self._connection_task = self._executor(
            self._facade.disconnect_wechat,
            on_success=self._after_wechat_disconnect,
            on_error=lambda code, message: self._handle_wechat_disconnect_error(
                code,
                message,
            ),
            on_finished=self._finish_wechat_disconnect,
        )

    def _after_wechat_disconnect(self, status: Any) -> None:
        self._show_connection_status(status, False)

    def _finish_wechat_disconnect(self) -> None:
        self._connection_task = None
        self._wechat_disconnect_button.setEnabled(True)

    def _handle_wechat_disconnect_error(self, code: str, message: str) -> None:
        self._status_label.setText(
            _DISCONNECTED_PREFIX + _WECHAT_DISCONNECT_FAILED
        )
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self.session_panel.show_disconnected_placeholder()
        self._set_restart_action()
        self.status_changed.emit(message)

    def cancel_connection(self) -> None:
        """Cancel an in-flight WeChat connection."""
        if self._connection_task is not None:
            cancel = getattr(self._connection_task, "cancel", None)
            if callable(cancel):
                cancel()
            # Keep the task reference until on_finished runs so a new
            # connection cannot overlap the one that is still winding down.
        self._wechat_connect_pending = False
        self._hide_wechat_guide()
        self._wechat_connect_button.setText(_WECHAT_CONNECT_LABEL)
        self._wechat_connect_button.setEnabled(
            self._connection_task is None
        )
        self._wechat_disconnect_button.setVisible(False)
        self._status_label.setText("连接已取消，可以重新开始。")
        self._status_label.setVisible(True)
        self.status_changed.emit("连接已取消，可以重新开始。")

    def cancel_analysis(self) -> None:
        """Cancel the active analysis."""
        self.session_panel.cancel_analysis()

    # ---------------------------------------------------------------- sessions

    def _load_sessions(self) -> None:
        self._executor(
            lambda: self._facade.list_sessions(ChatSource.WECHAT),
            on_success=self._handle_sessions_loaded,
            on_error=self._handle_session_error,
        )

    def _handle_sessions_loaded(self, sessions: Any) -> None:
        self._sessions_loaded = True
        self.session_panel.populate_sessions(sessions)
        self._status_label.setText(_CONNECTED_PREFIX + _WECHAT_STATUS_CONNECTED)
        self._status_label.setToolTip("")
        self._status_label.setVisible(True)
        self._hide_wechat_guide()
        self._wechat_connect_button.setVisible(False)
        self._wechat_disconnect_button.setVisible(True)

    def _handle_session_error(self, code: str, message: str) -> None:
        self._sessions_loaded = False
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
        self._set_restart_action()
        self.status_changed.emit(detail)

    # ---------------------------------------------------------------- setup

    def open_wechat_setup(self, data_roots: Any = None) -> None:
        """Open the setup dialog, showing the current facade state."""
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
        self._status_label.setText("正在保存微信环境设置...")
        self._status_label.setToolTip("")
        self._executor(
            lambda: self._facade.setup_wechat_environment(config),
            on_success=lambda _status: self._after_wechat_environment_saved(),
            on_error=self._handle_setup_error,
        )

    def _after_wechat_environment_saved(self) -> None:
        self.refresh_connection_status(load_sessions_on_ready=True)

    def _handle_setup_error(self, code: str, message: str) -> None:
        self._status_label.setText(
            _DISCONNECTED_PREFIX + "微信环境设置失败"
        )
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self._set_restart_action()
        self.status_changed.emit(message)

    # ---------------------------------------------------------------- signals

    def _on_analysis_started(self) -> None:
        self.analysis_started.emit()

    def _on_panel_status(self, message: str) -> None:
        self.status_changed.emit(message)


def _wechat_unavailable_message(status: Any) -> str:
    if not bool(getattr(status, "runtime_available", False)):
        return "微信连接环境不存在"
    if not bool(getattr(status, "data_found", False)):
        return "微信数据库未就绪"
    if not bool(getattr(status, "db_key_available", False)):
        return _WECHAT_WAITING_LOGIN
    return getattr(status, "message", "") or _WECHAT_STATUS_DISCONNECTED
