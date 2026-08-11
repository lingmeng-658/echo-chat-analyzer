"""Application-layer bridge that starts and tracks QQ authorization.

QCE itself exposes no public login endpoint on its HTTP API. The bundled
runtime owns the login window: the launcher opens the QQ login UI and the
plugin starts the QCE API server after QQ is ready. This bridge keeps that
detail behind one application-layer action so the GUI never has to know
whether the runtime asks for a QR code, a quick login, or a password.

``start_auth_flow()`` reuses the existing setup/connection services to start
the runtime, opens the runtime's own login window, and returns a lifecycle
snapshot. The caller keeps polling ``get_snapshot()`` (or the facade's
snapshot method) until the snapshot reports ``CONNECTED``; that probe path is
the existing provider health/data check, so no new state machine is needed.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from .models import ConnectionSnapshot, ConnectionState
from .qq_connection_manager import QQConnectionManager, SOURCE_QQ
from ..qq_process_registry import (
    QQProcessRegistry,
    default_qq_process_registry,
)


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_auth_bridge")


MESSAGE_ERROR = (
    "\u65e0\u6cd5\u542f\u52a8 QQ \u767b\u5f55\u6388\u6743\uff0c"
    "\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
)
HINT_RETRY = "\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"

MESSAGE_WINDOW_MISSING = (
    "\u672a\u627e\u5230 QQ \u767b\u5f55\u7a97\u53e3\u5165\u53e3\uff0c"
    "\u8bf7\u786e\u8ba4\u8fd0\u884c\u73af\u5883\u5b8c\u6574\u540e\u91cd\u8bd5\u3002"
)
MESSAGE_QQ_MISSING = (
    "\u672a\u68c0\u6d4b\u5230 QQ \u5ba2\u6237\u7aef\uff0c"
    "\u8bf7\u5148\u5b89\u88c5 QQ \u540e\u91cd\u8bd5\u3002"
)
MESSAGE_MAIN_MISSING = (
    "\u672a\u627e\u5230 QQ \u8fd0\u884c\u65f6\u5165\u53e3\uff0c"
    "\u8bf7\u786e\u8ba4\u8fd0\u884c\u73af\u5883\u5b8c\u6574\u540e\u91cd\u8bd5\u3002"
)


class QQAuthWindowUnavailable(Exception):
    """Raised when the runtime's login window cannot be opened."""

    code = "qq_auth_window_unavailable"
    public_message = MESSAGE_WINDOW_MISSING

    def __init__(self, public_message: str | None = None) -> None:
        self.public_message = public_message or type(self).public_message
        super().__init__(self.public_message)


class QQAuthBridge:
    """Start the QQ authorization flow and keep it observable.

    The bridge only composes existing collaborators. Runtime start stays in
    the setup service, QQ data availability stays in the connection service,
    and snapshot mapping stays in the connection manager.
    """

    def __init__(
        self,
        *,
        setup_service: Any = None,
        connection_service: Any = None,
        manager: Any = None,
        window_launcher: Callable[[], None] | None = None,
        process_registry: QQProcessRegistry | None = None,
    ) -> None:
        self._setup_service = setup_service
        self._connection_service = connection_service
        self._manager = manager
        self._window_launcher = window_launcher
        self._auth_launch_started = False
        self._process_registry = (
            process_registry or default_qq_process_registry()
        )

    def start_auth_flow(self) -> ConnectionSnapshot:
        """Start QQ authorization and return the immediate lifecycle state.

        When QQ data is already usable this returns ``CONNECTED`` without
        touching the runtime. Otherwise the runtime is started through the
        existing setup service and the runtime's own login window is opened.
        The call never blocks waiting for the user; later probes detect the
        authorization result.
        """
        manager = self._manager_instance()
        snapshot = manager.get_snapshot()
        _LOGGER.info(
            "[qq auth] start_auth_flow entered state=%s setup_service=%s",
            _state_value(snapshot.state),
            self._setup_service is not None,
        )
        if snapshot.state is ConnectionState.CONNECTED:
            return snapshot
        if snapshot.state is not ConnectionState.WAITING_AUTH:
            self._auth_launch_started = False
        if self._setup_service is None:
            return self._error_snapshot(MESSAGE_ERROR, HINT_RETRY)

        try:
            snapshot = manager.connect()
        except Exception as error:
            _LOGGER.warning(
                "[qq auth] connect failed error=%s",
                type(error).__name__,
            )
            return self._error_snapshot(
                _public_message(error, MESSAGE_ERROR),
                HINT_RETRY,
            )
        _LOGGER.info(
            "[qq auth] connect finished state=%s",
            _state_value(snapshot.state),
        )

        if snapshot.state is ConnectionState.WAITING_AUTH:
            try:
                _LOGGER.info("[qq auth] opening login window")
                self._launch_window()
            except Exception as error:
                _LOGGER.warning(
                    "[qq auth] login window launch failed error=%s",
                    type(error).__name__,
                )
                return self._error_snapshot(
                    _public_message(error, MESSAGE_ERROR),
                    HINT_RETRY,
                )
            _LOGGER.info("[qq auth] login window launched")

        latest = manager.get_snapshot()
        if latest.state is ConnectionState.CONNECTED:
            return latest
        if snapshot.state in (
            ConnectionState.CONNECTED,
            ConnectionState.WAITING_AUTH,
        ):
            return snapshot
        return latest

    def get_snapshot(self) -> ConnectionSnapshot:
        """Return the current lifecycle snapshot for continued detection."""
        return self._manager_instance().get_snapshot()

    # ---------------------------------------------------------------- internals

    def _manager_instance(self) -> QQConnectionManager:
        if self._manager is None:
            self._manager = QQConnectionManager(
                setup_service=self._setup_service,
                connection_service=self._connection_service,
            )
        return self._manager

    def _launch_window(self) -> None:
        if self._auth_launch_started:
            _LOGGER.info("[qq auth] launcher already started; reusing")
            return
        if self._window_launcher is not None:
            _LOGGER.info("[qq auth] using injected window launcher")
            self._window_launcher()
            self._auth_launch_started = True
            return
        config = self._setup_service.get_environment_config()
        _LOGGER.info(
            "[qq auth] building default window launcher config=%s",
            _config_summary(config),
        )
        launcher = default_auth_window_launcher(config)
        process = launcher()
        self._auth_launch_started = True
        pid = getattr(process, "pid", None)
        if pid is not None:
            self._process_registry.record(pid)

    @staticmethod
    def _error_snapshot(message: str, action_hint: str) -> ConnectionSnapshot:
        return ConnectionSnapshot(
            state=ConnectionState.ERROR,
            source=SOURCE_QQ,
            message=message,
            action_hint=action_hint,
        )


def default_auth_window_launcher(config: Any) -> Callable[[], None]:
    """Build a callable that opens the bundled runtime's login window.

    The runtime's own launcher decides the login form; this code only locates
    the launcher, the QQ install, and the injection hook. No QR code or
    account number is assumed or passed.
    """
    runtime_directory = _runtime_directory(config)
    launcher = runtime_directory / "launcher-user.bat"
    qq_path = resolve_qq_install_path(config, runtime_directory)
    _LOGGER.info(
        "[qq auth] runtime environment runtime_directory=%s exists=%s "
        "launcher=%s launcher_found=%s",
        runtime_directory,
        runtime_directory.is_dir(),
        launcher,
        launcher.is_file(),
    )
    _LOGGER.info(
        "[qq auth] qq install path=%s found=%s",
        qq_path,
        qq_path is not None and qq_path.is_file(),
    )

    if not launcher.is_file():
        raise QQAuthWindowUnavailable(MESSAGE_WINDOW_MISSING)
    if qq_path is None or not qq_path.is_file():
        raise QQAuthWindowUnavailable(MESSAGE_QQ_MISSING)

    return lambda: _launch_auth_window(
        runtime_directory,
        launcher,
        qq_path,
    )


def resolve_qq_install_path(
    config: Any,
    runtime_directory: Path | None = None,
) -> Path | None:
    """Resolve the QQ install executable for the bundled runtime.

    The environment config wins, then the path the launcher already saved in
    ``config/qq_path.txt``, then the bundled ``find-qq.ps1`` detector. All
    results are verified to exist before being returned.
    """
    configured = _path_value(getattr(config, "qq_install_path", None))
    if configured is not None and configured.is_file():
        return configured

    directory = runtime_directory or _runtime_directory(config)
    saved = _read_saved_qq_path(directory / "config" / "qq_path.txt")
    if saved is not None:
        return saved

    detector = directory / "find-qq.ps1"
    if detector.is_file():
        return _detect_qq_path_with_script(detector)
    return None


def _runtime_directory(config: Any) -> Path:
    directory = _path_value(getattr(config, "runtime_directory", None))
    return directory if directory is not None else Path(".")


def _path_value(value: Any) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    text = str(value).strip()
    return Path(text) if text else None


def _read_saved_qq_path(path: Path) -> Path | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    for line in raw.splitlines():
        candidate = line.strip().strip('"')
        if not candidate:
            continue
        resolved = Path(candidate)
        if resolved.is_file():
            return resolved
    return None


def _detect_qq_path_with_script(script: Path) -> Path | None:
    options = {
        "capture_output": True,
        "text": True,
        "timeout": 10,
        "check": False,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            **options,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in (completed.stdout or "").splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        resolved = Path(candidate)
        if resolved.is_file():
            return resolved
    return None


def _launch_auth_window(
    runtime_directory: Path,
    launcher: Path,
    qq_path: Path,
) -> Any:
    """Open the runtime login window once, without waiting for login."""
    command = [
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        "call",
        str(launcher),
    ]
    _LOGGER.info(
        "[qq auth] launch command=%s cwd=%s qq_path=%s",
        command,
        runtime_directory,
        qq_path,
    )
    launch_options = {
        "cwd": str(runtime_directory),
        "env": {
            **os.environ,
            "ECHO_MODE": "1",
            "NAPCAT_QQ_PATH": str(qq_path.resolve()),
        },
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        launch_options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        process = subprocess.Popen(
            command,
            **launch_options,
        )
    except OSError as error:
        _LOGGER.warning(
            "[qq auth] launch failed error=%s",
            type(error).__name__,
        )
        raise QQAuthWindowUnavailable() from error
    return_code = process.poll()
    _LOGGER.info(
        "[qq auth] launch result pid=%s returncode=%s",
        getattr(process, "pid", None),
        return_code,
    )
    communicate = getattr(process, "communicate", None)
    if callable(communicate):
        if return_code is None:
            threading.Thread(
                target=_log_launcher_completion,
                args=(process,),
                name="echo-qq-launcher-log",
                daemon=True,
            ).start()
        else:
            _log_launcher_completion(process)
    if return_code not in (None, 0):
        raise QQAuthWindowUnavailable()
    return process


def _log_launcher_completion(process: Any) -> None:
    """Consume launcher pipes and record its eventual result without blocking."""
    try:
        stdout, stderr = process.communicate()
    except Exception as error:
        _LOGGER.warning(
            "[qq auth] launcher output unavailable error=%s",
            type(error).__name__,
        )
        return
    _LOGGER.info(
        "[qq auth] launcher completed returncode=%s stdout=%s stderr=%s",
        getattr(process, "returncode", process.poll()),
        _safe_launcher_output(stdout),
        _safe_launcher_output(stderr),
    )


def _safe_launcher_output(value: Any, limit: int = 2000) -> str:
    """Normalize and bound launcher diagnostics before writing them to logs."""
    text = str(value or "").strip().replace("\r", " ").replace("\n", " | ")
    return text[:limit]


def _ensure_load_script(runtime_directory: Path) -> None:
    """Refresh the bootstrap file the launcher injects into QQ."""
    napcat_main = (runtime_directory / "napcat.mjs").resolve()
    if not napcat_main.is_file():
        raise QQAuthWindowUnavailable(MESSAGE_MAIN_MISSING)
    load_js = runtime_directory / "loadNapCat.js"
    content = (
        '(async () => {await import("file:///'
        + napcat_main.as_posix()
        + '")})()\n'
    )
    load_js.write_text(content, encoding="utf-8")


def _public_message(error: Exception, fallback: str) -> str:
    message = getattr(error, "public_message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    return fallback


def _state_value(state: Any) -> Any:
    return getattr(state, "value", state)


def _config_summary(config: Any) -> str:
    if config is None:
        return "none"
    runtime_directory = _runtime_directory(config)
    return (
        f"runtime_directory={runtime_directory} "
        f"exists={runtime_directory.is_dir()}"
    )


__all__ = [
    "QQAuthBridge",
    "QQAuthWindowUnavailable",
    "default_auth_window_launcher",
    "resolve_qq_install_path",
]
