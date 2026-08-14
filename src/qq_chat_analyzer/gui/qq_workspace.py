"""QQ workspace: connection status, QR login, and session analysis."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..application.facade import ChatSource
from ..resources import default_qq_runtime_directory
from .session_analysis_panel import SessionAnalysisPanel
from .theme import (
    GUIDE_STYLE,
    STATUS_STYLE_BASE,
    STATUS_STYLE_ERROR,
)
from .workers import submit


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_workspace")

_QQ_CONNECT_LABEL = "连接QQ"
_QQ_CONNECTING = "正在准备QQ连接环境，请稍候..."
_QQ_CONNECT_FAILED = "QQ 连接失败"
_QQ_DISCONNECT_LABEL = "退出连接"
_QQ_DISCONNECTING = "正在退出QQ连接..."
_QQ_DISCONNECT_FAILED = "QQ退出连接失败"
_CANCEL_CONNECTION_LABEL = "取消连接"
_RESTART_CONNECTION_LABEL = "重新开始"
_CONNECTION_CANCELLED = "连接已取消，可以重新开始。"
_QQ_CONNECT_MIN_DISPLAY_MS = 500
_QQ_STATUS_POLL_INTERVAL_MS = 2000
_QQ_WAITING_AUTH_TIMEOUT_MS = 120_000
_QQ_AUTH_TIMEOUT_TITLE = "QQ登录等待超时"
_QQ_AUTH_TIMEOUT_HINT = "扫码时间过长，请取消后重新连接。"
_QQ_QRCODE_SIZE = 240
_QQ_QRCODE_RELATIVE_PATH = Path("cache") / "qrcode.png"
_QQ_LOGIN_GUIDE = (
    "等待QQ登录\n\n请扫码登录QQ。\n"
    "QQ主窗口可能不会正常显示，这是正常现象。"
)
_QQ_STARTING_GUIDE = (
    "首次连接 QQ 时，系统可能弹出权限确认窗口。\n\n"
    "这是 Echo 内置的 QQ 数据读取组件，用于分析你的聊天记录，"
    "请允许它运行。"
)
_QQ_STATE_DISCONNECTED = "disconnected"
_QQ_STATE_INITIALIZING = "initializing"
_QQ_STATE_STARTING = "starting"
_QQ_STATE_WAITING_AUTH = "waiting_auth"
_QQ_STATE_CONNECTED = "connected"
_QQ_STATE_ERROR = "error"
_CONNECTED_PREFIX = "\U0001F7E2 "
_DISCONNECTED_PREFIX = "\U0001F534 "
_QQ_PENDING_PREFIX = "\U0001F7E1 "
_QQ_PROGRESS_STATES = (
    _QQ_STATE_INITIALIZING,
    _QQ_STATE_STARTING,
)
_QQ_STATE_MESSAGES = {
    _QQ_STATE_DISCONNECTED: "QQ 尚未连接。",
    _QQ_STATE_INITIALIZING: "正在初始化 QQ 连接，请稍候...",
    _QQ_STATE_STARTING: "正在启动 QQ，请稍候...",
    _QQ_STATE_WAITING_AUTH: "等待 QQ 扫码登录...",
    _QQ_STATE_CONNECTED: "QQ 已连接。",
    _QQ_STATE_ERROR: "QQ 连接异常。",
}
_CONNECTION_STATUS_UNKNOWN = "无法确认连接状态。"
_QQ_STATUS_CHECKING = "正在检测 QQ 连接状态..."
_LOADING_SESSIONS = "正在加载会话列表..."


class QQWorkspace(QWidget):
    """QQ workspace: connection status, QR code, and session analysis.

    This workspace mirrors the QQ half of the GUI-2 AnalysisPage lifecycle:
    status through ``get_qq_connection_snapshot``, auth through
    ``start_qq_auth_flow``, polling while waiting for login, then session
    loading and analysis through the shared panel.
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
        self._qq_connect_in_flight = False
        self._connection_task: Any = None
        self._last_qq_status_message = ""
        self._qq_waiting_auth_since: float | None = None
        self._qq_qrcode_path = _default_qq_qrcode_path()
        self._sessions_loaded = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        self._status_label.setStyleSheet(STATUS_STYLE_BASE)
        main_layout.addWidget(self._status_label)

        self._qq_connect_button = QPushButton(_QQ_CONNECT_LABEL)
        self._qq_connect_button.setVisible(False)
        self._qq_connect_button.clicked.connect(self.connect_qq)
        self._qq_connect_button.setMinimumHeight(34)
        main_layout.addWidget(self._qq_connect_button)

        self._qq_disconnect_button = QPushButton(_QQ_DISCONNECT_LABEL)
        self._qq_disconnect_button.setVisible(False)
        self._qq_disconnect_button.clicked.connect(self.disconnect_qq)
        self._qq_disconnect_button.setMinimumHeight(34)
        main_layout.addWidget(self._qq_disconnect_button)

        self._qq_qrcode_label = QLabel("")
        self._qq_qrcode_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self._qq_qrcode_label.setFixedSize(_QQ_QRCODE_SIZE, _QQ_QRCODE_SIZE)
        self._qq_qrcode_label.setVisible(False)
        main_layout.addWidget(self._qq_qrcode_label)

        self._qq_login_guide_label = QLabel("")
        self._qq_login_guide_label.setWordWrap(True)
        self._qq_login_guide_label.setVisible(False)
        self._qq_login_guide_label.setStyleSheet(GUIDE_STYLE)
        main_layout.addWidget(self._qq_login_guide_label)

        self.session_panel = SessionAnalysisPanel()
        self.session_panel.configure(facade, ChatSource.QQ, executor=self._executor)
        main_layout.addWidget(self.session_panel, stretch=1)

        self.session_panel.analysis_started.connect(self._on_analysis_started)
        self.session_panel.analysis_succeeded.connect(self.analysis_succeeded.emit)
        self.session_panel.analysis_failed.connect(self.analysis_failed.emit)
        self.session_panel.status_changed.connect(self._on_panel_status)

        self._qq_status_timer = QTimer(self)
        self._qq_status_timer.setInterval(_QQ_STATUS_POLL_INTERVAL_MS)
        self._qq_status_timer.timeout.connect(self._poll_qq_status)

        self.session_panel.show_unconnected_placeholder()

    # ---------------------------------------------------------------- public API

    def select_source(self, source: Any) -> None:
        """Configure the panel for QQ and reset transient state."""
        self.session_panel.configure(self._facade, ChatSource.QQ, executor=self._executor)
        self._sessions_loaded = False
        self._stop_qq_status_polling()
        self._hide_qq_qrcode()
        self._hide_qq_login_guide()
        self._qq_disconnect_button.setVisible(False)
        self.session_panel.clear()

    def refresh_connection_status(
        self,
        *,
        load_sessions_on_ready: bool = False,
    ) -> None:
        """Refresh the QQ connection status through the connection snapshot."""
        self.refresh_qq_status(load_sessions_on_ready=load_sessions_on_ready)

    def refresh_qq_status(self, *, load_sessions_on_ready: bool = False) -> None:
        """Ask the connection manager, through the facade, for QQ state."""
        self._status_label.setVisible(True)
        self._status_label.setStyleSheet(STATUS_STYLE_BASE)
        self._status_label.setText(_QQ_STATUS_CHECKING)
        self._status_label.setToolTip("")
        self.session_panel.show_connecting_placeholder()
        self.session_panel.update_analyze_enabled()
        self._executor(
            lambda: self._facade.get_qq_connection_snapshot(),
            on_success=lambda snapshot: self._show_qq_status(
                snapshot,
                load_sessions_on_ready,
            ),
            on_error=lambda code, message: self._handle_source_status_error(
                code,
                message,
            ),
        )

    # ---------------------------------------------------------------- status

    def _handle_source_status_error(self, code: str, message: str) -> None:
        self._handle_connection_status_error(code, message)

    def _handle_connection_status_error(self, code: str, message: str) -> None:
        if self._qq_connect_in_flight:
            return
        self._status_label.setText(_CONNECTION_STATUS_UNKNOWN)
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self.session_panel.show_disconnected_placeholder()
        self._set_restart_action()
        self.session_panel.update_analyze_enabled()

    def _show_qq_status(
        self,
        snapshot: Any,
        load_sessions_on_ready: bool,
    ) -> None:
        """Render one QQ connection snapshot and the connect button."""
        if self._qq_connect_in_flight:
            return
        state = _snapshot_state(snapshot)
        message = _snapshot_message(snapshot)
        action_hint = _snapshot_hint(snapshot)
        if state == _QQ_STATE_WAITING_AUTH:
            if self._qq_waiting_auth_since is None:
                self._qq_waiting_auth_since = time.monotonic()
        else:
            self._qq_waiting_auth_since = None
        self._last_qq_status_message = message
        self._status_label.setStyleSheet(
            STATUS_STYLE_ERROR
            if state == _QQ_STATE_ERROR
            else STATUS_STYLE_BASE
        )

        self._status_label.setText(f"{_snapshot_prefix(snapshot)}{message}")
        self._status_label.setToolTip(action_hint)
        self._status_label.setVisible(True)
        self._qq_connect_button.setText(_QQ_CONNECT_LABEL)
        self._qq_connect_button.setVisible(state != _QQ_STATE_CONNECTED)
        if state == _QQ_STATE_ERROR:
            self._qq_connect_button.setText(_RESTART_CONNECTION_LABEL)
        self._qq_connect_button.setEnabled(not _snapshot_in_progress(snapshot))
        self._qq_connect_button.setToolTip("")
        self._qq_disconnect_button.setVisible(state == _QQ_STATE_CONNECTED)
        self._qq_disconnect_button.setEnabled(state == _QQ_STATE_CONNECTED)
        self._qq_disconnect_button.setToolTip("")
        self.session_panel.update_analyze_enabled()

        if load_sessions_on_ready:
            self.status_changed.emit(message)

        if state == _QQ_STATE_CONNECTED and load_sessions_on_ready:
            self.session_panel.show_reading_placeholder()
            self.status_changed.emit(_LOADING_SESSIONS)
            self._load_sessions()
        elif state in _QQ_PROGRESS_STATES or state == _QQ_STATE_WAITING_AUTH:
            self.session_panel.show_connecting_placeholder()
        elif state != _QQ_STATE_CONNECTED:
            self.session_panel.show_disconnected_placeholder()

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
        if self._qq_auth_waiting_expired():
            self._handle_qq_auth_timeout()
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
        if not self._qq_status_timer.isActive():
            self._qq_status_timer.start()

    def _stop_qq_status_polling(self) -> None:
        self._qq_status_timer.stop()

    def _qq_auth_waiting_expired(self) -> bool:
        since = self._qq_waiting_auth_since
        if since is None:
            return False
        return (time.monotonic() - since) * 1000 >= _QQ_WAITING_AUTH_TIMEOUT_MS

    def _handle_qq_auth_timeout(self) -> None:
        """Stop polling and show a reconnectable error after a long wait."""
        self._stop_qq_status_polling()
        self._hide_qq_qrcode()
        self._hide_qq_login_guide()
        self._status_label.setStyleSheet(STATUS_STYLE_ERROR)
        self._status_label.setText(_DISCONNECTED_PREFIX + _QQ_AUTH_TIMEOUT_TITLE)
        self._status_label.setToolTip(_QQ_AUTH_TIMEOUT_HINT)
        self._status_label.setVisible(True)
        self.session_panel.show_disconnected_placeholder()
        self._set_restart_action()
        self.status_changed.emit(_QQ_AUTH_TIMEOUT_TITLE)

    def _refresh_qq_qrcode(self) -> None:
        """Show the runtime QR only when the facade says it is fresh."""
        if not self._qq_qrcode_path.is_file():
            self._hide_qq_qrcode()
            return
        try:
            fresh = self._facade.is_qq_qrcode_ready()
        except Exception:
            _LOGGER.debug("[qq gui] qr readiness probe failed", exc_info=True)
            fresh = False
        if not fresh:
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

    # ---------------------------------------------------------------- connect

    def connect_qq(self) -> None:
        """Start the QQ authorization flow in one click."""
        if self._qq_connect_in_flight:
            self.cancel_connection()
            return
        _LOGGER.info("[qq gui] connect_qq requested")
        started_at = time.monotonic()
        self._qq_waiting_auth_since = None
        self._qq_connect_in_flight = True
        self._qq_connect_button.setText(_CANCEL_CONNECTION_LABEL)
        self._qq_connect_button.setEnabled(True)
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_CONNECTING)
        self._status_label.setToolTip("")
        self._show_qq_starting_guide()
        self._hide_qq_qrcode()
        self.session_panel.show_connecting_placeholder()
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
            on_progress=lambda message: self._handle_qq_connect_progress(message),
        )

    def _handle_qq_connect_progress(self, message: str) -> None:
        """Translate backend progress into one of the user-facing stages."""
        if not message:
            return
        stage, hint = _qq_progress_copy(message)
        self._status_label.setText(_QQ_PENDING_PREFIX + stage)
        self._status_label.setToolTip("")
        self._status_label.setVisible(True)
        if stage == "等待QQ登录":
            self._show_qq_login_guide()
        else:
            self._show_qq_starting_guide()
        self.status_changed.emit(stage)

    def _after_qq_connect(self, snapshot: Any) -> None:
        self._show_qq_status(snapshot, load_sessions_on_ready=True)

    def _finish_qq_connect(self, status: Any, started_at: float) -> None:
        def _apply() -> None:
            self._qq_connect_in_flight = False
            self._connection_task = None
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
            self._connection_task = None
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
        self._status_label.setStyleSheet(STATUS_STYLE_ERROR)
        self._status_label.setText(_DISCONNECTED_PREFIX + title)
        self._status_label.setToolTip(message)
        self._status_label.setVisible(True)
        self.session_panel.show_disconnected_placeholder()
        self._set_restart_action()
        self.status_changed.emit(title)

    def _set_restart_action(self) -> None:
        self._qq_connect_button.setText(_RESTART_CONNECTION_LABEL)
        self._qq_connect_button.setEnabled(True)
        self._qq_connect_button.setVisible(True)
        self._qq_disconnect_button.setVisible(False)

    def disconnect_qq(self) -> None:
        """Stop the current QQ session and return to a reconnectable page."""
        if self._qq_connect_in_flight:
            self.cancel_connection()
            return
        _LOGGER.info("[qq gui] disconnect_qq requested")
        self._stop_qq_status_polling()
        self._hide_qq_qrcode()
        self._hide_qq_login_guide()
        self._qq_disconnect_button.setEnabled(False)
        self._status_label.setVisible(True)
        self._status_label.setText(_QQ_DISCONNECTING)
        self._status_label.setToolTip("")
        self.session_panel.clear()
        self.status_changed.emit(_QQ_DISCONNECTING)
        self._executor(
            self._facade.disconnect_qq,
            on_success=lambda snapshot: self._show_qq_status(snapshot, False),
            on_error=lambda code, message: self._handle_qq_disconnect_error(
                code,
                message,
            ),
        )

    def _handle_qq_disconnect_error(self, code: str, message: str) -> None:
        self._qq_disconnect_button.setEnabled(True)
        self._show_qq_error(_QQ_DISCONNECT_FAILED, message)

    def cancel_connection(self) -> None:
        """Cancel the active source task and return to a reconnectable page."""
        task = self._connection_task
        if task is None and not self._qq_connect_in_flight:
            return
        cancel = getattr(task, "cancel", None)
        if callable(cancel):
            cancel()
        shutdown = getattr(self._facade, "shutdown_qq_runtime", None)
        if callable(shutdown):
            shutdown()
        self._connection_task = None
        self._qq_connect_in_flight = False
        self._qq_waiting_auth_since = None
        self._stop_qq_status_polling()
        self._hide_qq_qrcode()
        self._hide_qq_login_guide()
        self._qq_connect_button.setText(_QQ_CONNECT_LABEL)
        self._qq_connect_button.setEnabled(True)
        self._qq_disconnect_button.setVisible(False)
        self._status_label.setText(_CONNECTION_CANCELLED)
        self._status_label.setVisible(True)
        self.status_changed.emit(_CONNECTION_CANCELLED)

    def cancel_analysis(self) -> None:
        """Cancel the active analysis."""
        self.session_panel.cancel_analysis()

    # ---------------------------------------------------------------- sessions

    def _load_sessions(self) -> None:
        self._executor(
            lambda: self._facade.list_sessions(ChatSource.QQ),
            on_success=self._handle_sessions_loaded,
            on_error=self._handle_session_error,
        )

    def _handle_sessions_loaded(self, sessions: Any) -> None:
        self._sessions_loaded = True
        self.session_panel.populate_sessions(sessions)
        self.status_changed.emit(
            self._last_qq_status_message
            or _QQ_STATE_MESSAGES[_QQ_STATE_CONNECTED]
        )

    def _handle_session_error(self, code: str, message: str) -> None:
        self._sessions_loaded = False
        self.session_panel.show_disconnected_placeholder()
        self.analysis_failed.emit(code, message)

    # ---------------------------------------------------------------- signals

    def _on_analysis_started(self) -> None:
        self.analysis_started.emit()

    def _on_panel_status(self, message: str) -> None:
        self.status_changed.emit(message)


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


def _default_qq_qrcode_path() -> Path:
    """Return where the bundled QQ runtime writes its login QR image."""
    return default_qq_runtime_directory() / _QQ_QRCODE_RELATIVE_PATH