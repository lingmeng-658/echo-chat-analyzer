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

import hashlib
import logging
import os
import subprocess
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .models import ConnectionSnapshot, ConnectionState
from .qq_connection_manager import (
    HINT_WAITING_AUTH,
    MESSAGE_WAITING_AUTH,
    QQConnectionManager,
    SOURCE_QQ,
)
from ..qq_environment_config import (
    QQConfigNotFound,
    QQEnvironmentConfigLoader,
)
from ..qq_process_registry import (
    QQProcessRegistry,
    default_qq_process_registry,
)
from ..qq_webui_config import disable_qce_auto_open_browser


_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_auth_bridge")


MESSAGE_ERROR = (
    "\u65e0\u6cd5\u542f\u52a8 QQ \u767b\u5f55\u6388\u6743\uff0c"
    "\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
)
HINT_RETRY = "\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
MESSAGE_RUNTIME_UNAVAILABLE = (
    "\u672a\u627e\u5230\u53ef\u7528\u7684 QQ \u8fd0\u884c\u7ec4\u4ef6\uff0c"
    "\u8bf7\u786e\u8ba4 Echo \u5b89\u88c5\u5b8c\u6574\u540e\u91cd\u8bd5\u3002"
)

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

PROGRESS_CHECKING = "正在检查 QQ 运行环境..."
PROGRESS_STARTING = "正在启动 QQ 环境..."
PROGRESS_LOADING_NAPCAT = "正在加载 NapCat..."
PROGRESS_WAITING_LOGIN = "等待 QQ 登录..."
PROGRESS_CONNECTED = "QQ 已连接"


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
        config_preparer: Callable[[], bool] | None = None,
        qrcode_path: Path | None = None,
        runtime_cleaner: Callable[[Path], None] | None = None,
    ) -> None:
        self._setup_service = setup_service
        self._connection_service = connection_service
        self._manager = manager
        self._window_launcher = window_launcher
        self._config_preparer = config_preparer or disable_qce_auto_open_browser
        self._qrcode_path = qrcode_path
        self._runtime_cleaner = runtime_cleaner
        self._auth_launch_started = False
        self._launched_process: Any | None = None
        self._qr_baseline: tuple[str, int, int] | None = None
        self._qr_session_started_at: float | None = None
        self._qr_ready_logged = False
        self._process_registry = (
            process_registry or default_qq_process_registry()
        )

    def start_auth_flow(
        self,
        progress: Callable[[str], None] | None = None,
    ) -> ConnectionSnapshot:
        """Launch QQ authorization and return the immediate lifecycle state.

        When QQ data is already usable this returns ``CONNECTED`` without
        touching the runtime. Otherwise the runtime's own login window is
        opened; the launcher owns NapCat and the QCE server, so no qce-server
        is pre-started here. Later probes detect the authorization result.
        """
        _report_progress(progress, PROGRESS_CHECKING)
        manager = self._manager_instance()
        snapshot = manager.get_snapshot()
        _LOGGER.info(
            "[qq auth] start_auth_flow entered state=%s setup_service=%s",
            _state_value(snapshot.state),
            self._setup_service is not None,
        )
        if snapshot.state is ConnectionState.CONNECTED:
            _report_progress(progress, PROGRESS_CONNECTED)
            return snapshot
        if snapshot.state is not ConnectionState.WAITING_AUTH:
            self._auth_launch_started = False
        if self._setup_service is None:
            return self._error_snapshot(MESSAGE_ERROR, HINT_RETRY)

        if snapshot.state in (
            ConnectionState.INITIALIZING,
            ConnectionState.STARTING,
        ):
            return snapshot

        try:
            _report_progress(progress, PROGRESS_STARTING)
            self._config_preparer()
            _report_progress(progress, PROGRESS_LOADING_NAPCAT)
            if not self._auth_launch_started:
                self._clean_stale_runtime()
                self._remember_qr_baseline()
            manager.begin_auth_waiting()
            _LOGGER.info("[qq auth] opening login window")
            self._launch_window()
        except Exception as error:
            manager.end_auth_waiting()
            _LOGGER.warning(
                "[qq auth] login window launch failed error=%s",
                type(error).__name__,
            )
            return self._error_snapshot(
                _public_message(error, MESSAGE_ERROR),
                HINT_RETRY,
            )
        _LOGGER.info("[qq auth] login window launched")
        _report_progress(progress, PROGRESS_WAITING_LOGIN)

        latest = manager.get_snapshot()
        if latest.state is ConnectionState.CONNECTED:
            manager.end_auth_waiting()
            _report_progress(progress, PROGRESS_CONNECTED)
            return latest
        if latest.state is ConnectionState.ERROR:
            manager.end_auth_waiting()
            return latest
        return replace(
            latest,
            state=ConnectionState.WAITING_AUTH,
            message=MESSAGE_WAITING_AUTH,
            action_hint=HINT_WAITING_AUTH,
        )

    def get_snapshot(self) -> ConnectionSnapshot:
        """Return the current lifecycle snapshot for continued detection."""
        return self._manager_instance().get_snapshot()

    def is_qrcode_ready(self) -> bool:
        """Return whether the QR cache belongs to the current auth session.

        A fresh auth flow records the QR cache state before launching NapCat.
        Until the file changes, any pre-existing ``qrcode.png`` is treated as
        stale and must not be shown to the user.
        """
        path = self._qrcode_cache_path()
        if path is None:
            return False
        fingerprint = _qr_fingerprint(path)
        if fingerprint is None:
            self._qr_ready_logged = False
            return False
        fresh = (
            self._qr_baseline is None
            or fingerprint != self._qr_baseline
        )
        if fresh:
            if self._qr_baseline is not None and not self._qr_ready_logged:
                _LOGGER.info(
                    "[qq auth] qr accepted path=%s %s",
                    path,
                    _qr_fingerprint_text(
                        fingerprint,
                        elapsed_since=self._qr_session_started_at,
                    ),
                )
                self._qr_ready_logged = True
        else:
            self._qr_ready_logged = False
        return fresh

    # ---------------------------------------------------------------- internals

    def _manager_instance(self) -> QQConnectionManager:
        if self._manager is None:
            self._manager = QQConnectionManager(
                setup_service=self._setup_service,
                connection_service=self._connection_service,
            )
        return self._manager

    def _launch_window(self) -> None:
        if self._auth_launch_started and self._launcher_process_alive():
            _LOGGER.info("[qq auth] launcher already started; reusing")
            return
        self._auth_launch_started = False
        if self._window_launcher is not None:
            _LOGGER.info("[qq auth] using injected window launcher")
            self._window_launcher()
            self._auth_launch_started = True
            return
        try:
            config = self._setup_service.get_environment_config()
        except QQConfigNotFound:
            config = self._recover_environment_config()
        _LOGGER.info(
            "[qq auth] building default window launcher config=%s",
            _config_summary(config),
        )
        launcher = default_auth_window_launcher(config)
        process = launcher()
        self._auth_launch_started = True
        self._launched_process = process
        pid = getattr(process, "pid", None)
        if pid is not None:
            self._process_registry.record(pid)

    def _launcher_process_alive(self) -> bool:
        """Return whether the launched window process is still running.

        An injected launcher does not expose a process, so it is treated as
        alive to preserve the single-launch guard used by tests and stubs.
        """
        process = self._launched_process
        if process is None:
            return True
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return True
        return poll() is None

    def _recover_environment_config(self) -> Any:
        """Persist the effective default config, then return it for launch.

        The launcher still owns the runtime lifecycle, so recovery only
        writes qq.json; no qce-server is started here.
        """
        _LOGGER.info("[qq auth] environment config missing; auto-initializing")
        try:
            config = QQEnvironmentConfigLoader().load_or_default()
            saver = getattr(self._setup_service, "save_environment", None)
            if not callable(saver):
                raise QQConfigNotFound()
            saver(config)
            return self._setup_service.get_environment_config()
        except QQConfigNotFound:
            raise QQConfigNotFound(MESSAGE_RUNTIME_UNAVAILABLE) from None

    def _remember_qr_baseline(self) -> None:
        """Record the QR cache state that predates this auth session."""
        self._qr_session_started_at = time.monotonic()
        self._qr_ready_logged = False
        path = self._qrcode_cache_path()
        self._qr_baseline = _qr_fingerprint(path)
        if path is None:
            _LOGGER.info("[qq auth] qr baseline unavailable")
            return
        if self._qr_baseline is None:
            _LOGGER.info("[qq auth] qr baseline missing path=%s", path)
            return
        _LOGGER.info(
            "[qq auth] qr baseline exists path=%s %s",
            path,
            _qr_fingerprint_text(self._qr_baseline),
        )

    def _clean_stale_runtime(self) -> None:
        """Stop old Echo-launched runtime sessions before a fresh launch."""
        if self._runtime_cleaner is None:
            return
        config = self._environment_config()
        if config is None:
            return
        directory = _path_value(getattr(config, "runtime_directory", None))
        if directory is None:
            return
        _LOGGER.info(
            "[qq auth] stopping stale runtime sessions dir=%s",
            directory,
        )
        try:
            self._runtime_cleaner(directory)
        except Exception as error:
            _LOGGER.warning(
                "[qq auth] stale runtime cleanup failed error=%s",
                type(error).__name__,
            )

    def _qrcode_cache_path(self) -> Path | None:
        """Resolve the bundled runtime's QR cache path when available."""
        if self._qrcode_path is not None:
            return Path(self._qrcode_path)
        config = self._environment_config()
        if config is None:
            return None
        directory = _path_value(getattr(config, "runtime_directory", None))
        if directory is None:
            return None
        return directory / "cache" / "qrcode.png"

    def _environment_config(self) -> Any:
        if self._setup_service is None:
            return None
        getter = getattr(self._setup_service, "get_environment_config", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:
            _LOGGER.debug(
                "[qq auth] environment config unavailable",
                exc_info=True,
            )
            return None

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


def terminate_bundled_runtime_sessions(runtime_directory: Path) -> None:
    """Stop NapCat boot launchers started from one Echo runtime directory.

    A new QQ login session must not share the QR cache with an old session.
    The launcher starts ``NapCatWinBootMain.exe`` from the runtime directory,
    and that process owns the QQ process tree, so terminating it also stops
    the old QQ/NapCat session that would otherwise keep writing ``qrcode.png``.
    """
    if os.name != "nt":
        return
    target = (runtime_directory / "NapCatWinBootMain.exe").resolve()
    script = r"""
$ErrorActionPreference = "SilentlyContinue"
$target = $env:QCE_RUNTIME_DIR
Get-CimInstance Win32_Process -Filter "Name='NapCatWinBootMain.exe'" | ForEach-Object {
    $exe = $_.ExecutablePath
    if ($exe -and [IO.Path]::GetFullPath($exe) -eq [IO.Path]::GetFullPath($target)) {
        $process = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
        taskkill /PID $_.ProcessId /T /F | Out-Null
        if ($process) {
            $process | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
        }
    }
}
"""
    options = {
        "capture_output": True,
        "text": True,
        "timeout": 10,
        "check": False,
        "env": {**os.environ, "QCE_RUNTIME_DIR": str(target)},
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            **options,
        )
    except (OSError, subprocess.SubprocessError):
        _LOGGER.warning(
            "[qq auth] stale runtime cleanup command failed",
            exc_info=True,
        )


def _launch_auth_window(
    runtime_directory: Path,
    launcher: Path,
    qq_path: Path,
) -> Any:
    """Open the runtime login window once, without waiting for login."""
    # The launcher directory is already the child process cwd. Invoking the
    # fixed basename avoids passing any user-controlled path through cmd's
    # parsing rules, so spaces, parentheses, and Unicode parent directories
    # cannot split or group the command.
    command = [
        "cmd.exe",
        "/d",
        "/s",
        "/c",
        launcher.name,
    ]
    _LOGGER.info(
        "[qq auth] launch command=%s cwd=%s qq_path=%s",
        command,
        runtime_directory,
        qq_path,
    )
    environment = os.environ.copy()
    environment.pop("ECHO_MODE", None)
    environment["NAPCAT_QQ_PATH"] = str(qq_path.resolve())
    launch_options = {
        "cwd": str(runtime_directory),
        "env": environment,
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


def _report_progress(
    progress: Callable[[str], None] | None,
    message: str,
) -> None:
    """Publish an observed backend stage without affecting the auth flow."""
    if progress is None:
        return
    try:
        progress(message)
    except Exception:
        _LOGGER.debug("[qq auth] progress callback failed", exc_info=True)


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


def _qr_fingerprint(path: Path | None) -> tuple[str, int, int] | None:
    """Return a stable identity for the QR file, or None when unreadable."""
    if path is None:
        return None
    try:
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    return (digest, stat.st_mtime_ns, stat.st_size)


def _qr_fingerprint_text(
    fingerprint: tuple[str, int, int],
    *,
    elapsed_since: float | None = None,
) -> str:
    digest, mtime_ns, size = fingerprint
    mtime = datetime.fromtimestamp(mtime_ns / 1_000_000_000, tz=timezone.utc)
    text = (
        f"mtime={mtime.isoformat()} mtime_ns={mtime_ns} "
        f"size={size} sha256={digest}"
    )
    if elapsed_since is not None:
        elapsed_ms = int((time.monotonic() - elapsed_since) * 1000)
        text += f" elapsed_ms={elapsed_ms}"
    return text


__all__ = [
    "QQAuthBridge",
    "QQAuthWindowUnavailable",
    "default_auth_window_launcher",
    "resolve_qq_install_path",
    "terminate_bundled_runtime_sessions",
]
