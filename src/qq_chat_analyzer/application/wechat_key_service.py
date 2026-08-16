"""Acquire the WeChat 4.x database key from a running Weixin.exe process.

This service wraps the verified ``wx_key.dll`` hook surface:
``InitializeHook(pid)``, ``PollKeyData(buffer, size)``, and
``CleanupHook()``. It never reads databases and never prints the key.
Development logs record only flow milestones and safe error types, never the
key value or raw helper output. Callers inject fake process finders and DLL
adapters in tests so no real WeChat process or native library is ever touched.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable

from ..resources import default_wechat_wx_key_dll_path
from .errors import ApplicationServiceError


KEY_LENGTH = 64
BUFFER_SIZE = 65
DEFAULT_POLL_INTERVAL_SECONDS = 0.2
DEFAULT_TIMEOUT_SECONDS = 600.0
WECHAT_PROCESS_NAME = "Weixin.exe"
HELPER_FILE_NAME = "wx_key_helper.cjs"
_MAX_RETAINED_ERROR_LINES = 20
_KEY_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
# Process-local bridge for the manual WCDB diagnostic runner: the freshly
# obtained key is exposed to child processes for the lifetime of this process
# only (never persisted, never logged, never printed).
KEY_ENVIRONMENT_VARIABLE = "ECHO_WX_DB_KEY"
_ELAPSED_PATTERN = re.compile(r"elapsed=(\d+)s")
_COMPONENTS_READY_MESSAGE = (
    "\u5fae\u4fe1\u8fde\u63a5\u7ec4\u4ef6\u5df2\u51c6\u5907\u5b8c\u6210\uff0c"
    "\u8bf7\u73b0\u5728\u6253\u5f00\u5fae\u4fe1\u5e76\u767b\u5f55"
)
_KEY_RECEIVED_MESSAGE = "\u5fae\u4fe1\u8fde\u63a5\u51c6\u5907\u5b8c\u6210"

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.wechat_key_service")


class WeChatKeyUnavailable(ApplicationServiceError):
    """Raised when the WeChat database key cannot be acquired safely."""

    code = "wechat_key_unavailable"
    public_message = "\u5fae\u4fe1\u8fde\u63a5\u51c6\u5907\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5\u3002"

    def __init__(
        self,
        public_message: str | None = None,
        *,
        code: str | None = None,
    ) -> None:
        self.code = code or type(self).code
        self.public_message = public_message or type(self).public_message
        super().__init__()


class WeChatKeyService:
    """Detect WeChat, hook it, and return a 64-hex database key."""

    def __init__(
        self,
        *,
        dll_path: str | Path | None = None,
        process_finder: Callable[[], list[int]] | None = None,
        dll_loader: Callable[[Path], Any] | None = None,
        buffer_factory: Callable[[int], Any] | None = None,
        sleep: Callable[[float], None] | None = None,
        monotonic: Callable[[], float] | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        helper_path: str | Path | None = None,
        node_executable: str = "node",
        node_finder: Callable[[str], str | None] | None = None,
        subprocess_runner: Callable[..., Any] | None = None,
        koffi_module_path: str | Path | None = None,
        process_launcher: Callable[..., Any] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._dll_path = (
            Path(dll_path)
            if dll_path is not None
            else default_wechat_wx_key_dll_path()
        )
        self._process_finder = process_finder or _find_weixin_pids
        self._dll_loader = dll_loader or _load_hook_api
        self._buffer_factory = buffer_factory or _create_buffer
        self._sleep = sleep or time.sleep
        self._monotonic = monotonic or time.monotonic
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._helper_path = (
            Path(helper_path)
            if helper_path is not None
            else self._dll_path.with_name(HELPER_FILE_NAME)
        )
        self._node_executable = node_executable
        self._node_finder = node_finder or shutil.which
        self._subprocess_runner = subprocess_runner
        self._process_launcher = process_launcher
        self._progress_callback = progress_callback
        self._legacy_injected = dll_loader is not None or process_finder is not None
        self._koffi_module_path = (
            Path(koffi_module_path) if koffi_module_path is not None
            else self._helper_path.parent / "node_modules"
        )

    def clear(self) -> None:
        """Drop the process-local key so helpers start without stale state."""
        _clear_key_environment()

    def acquire(
        self,
        timeout: float | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> str:
        """Return one 64-hex database key, raising a user-safe error."""
        _LOGGER.info("wechat.connect.start")
        try:
            key = self._acquire(timeout=timeout, progress=progress)
        except Exception as error:
            _LOGGER.warning(
                "wechat.key.capture success=false error_type=%s",
                type(error).__name__,
            )
            raise
        _LOGGER.info("wechat.key.capture success=true")
        return key

    def _acquire(
        self,
        timeout: float | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> str:
        """Return one 64-hex database key, raising a user-safe error."""
        _clear_key_environment()
        if not self._dll_path.is_file():
            raise WeChatKeyUnavailable(
                "\u4f59\u97f3\u7684\u5fae\u4fe1\u8fde\u63a5\u7ec4\u4ef6"
                "\u4e0d\u5b8c\u6574\uff0c\u8bf7\u91cd\u65b0\u5b89\u88c5"
                "\u540e\u91cd\u8bd5\u3002",
                code="wechat_environment_missing",
            )

        if not self._legacy_injected:
            key = self._acquire_with_helper(timeout, progress)
            _expose_key_to_environment(key)
            return key

        pids = self._process_finder()
        if not pids:
            raise WeChatKeyUnavailable(
                "\u672a\u68c0\u6d4b\u5230\u5fae\u4fe1\uff0c"
                "\u8bf7\u5148\u6253\u5f00\u5e76\u767b\u5f55"
                "\u5fae\u4fe1\u7535\u8111\u7248\u3002",
                code="wechat_not_running",
            )

        timeout_seconds = self._timeout if timeout is None else timeout
        last_error = ""
        api = self._dll_loader(self._dll_path)

        for pid in pids:
            deadline = self._monotonic() + timeout_seconds
            try:
                hooked = bool(api.initialize(pid))
            except Exception:
                last_error = self._error_text(api)
                continue

            if not hooked:
                last_error = self._error_text(api)
                continue

            try:
                key = self._poll_key(api, deadline)
                if key:
                    _expose_key_to_environment(key)
                    return key
            finally:
                try:
                    api.cleanup()
                except Exception:
                    pass

        if last_error:
            raise WeChatKeyUnavailable(
                "\u5fae\u4fe1 Hook \u5931\u8d25\uff0c\u5f53\u524d\u5fae\u4fe1\u8fdb\u7a0b\u53ef\u80fd\u4e0d\u517c\u5bb9\u3002",
                code="wechat_hook_failed",
            )
        raise WeChatKeyUnavailable(
            "Key \u83b7\u53d6\u8d85\u65f6\uff0c\u8bf7\u5728\u5fae\u4fe1\u767b\u5f55\u65f6\u91cd\u8bd5\u3002",
            code="wechat_key_timeout",
        )

    def _acquire_with_helper(
        self,
        timeout: float | None,
        progress: Callable[[str], None] | None,
    ) -> str:
        if not self._helper_path.is_file():
            raise WeChatKeyUnavailable(
                "\u4f59\u97f3\u7684\u5fae\u4fe1\u8fde\u63a5\u7ec4\u4ef6"
                "\u4e0d\u5b8c\u6574\uff0c\u8bf7\u91cd\u65b0\u5b89\u88c5"
                "\u540e\u91cd\u8bd5\u3002",
                code="wechat_environment_missing",
            )
        timeout_seconds = self._timeout if timeout is None else timeout
        command, options = self._build_helper_invocation(timeout_seconds)

        if self._subprocess_runner is not None:
            return self._run_helper_buffered(command, options)
        return self._run_helper_streaming(command, options, progress)

    def _build_helper_invocation(
        self, timeout_seconds: float
    ) -> tuple[list[str], dict[str, Any]]:
        """Build the one command and option set both helper paths share."""
        command = [
            self._resolve_node_executable(),
            str(self._helper_path),
            "--dll",
            str(self._dll_path),
            "--timeout-ms",
            str(max(0, round(timeout_seconds * 1000))),
        ]
        environment = os.environ.copy()
        environment["NODE_PATH"] = str(self._koffi_module_path)
        options: dict[str, Any] = {
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": max(1.0, timeout_seconds + 5.0),
            "env": environment,
            "cwd": str(self._helper_path.parent),
        }
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        return command, options

    def _resolve_node_executable(self) -> str:
        bundled_node = self._helper_path.with_name("node.exe")
        if bundled_node.is_file():
            return str(bundled_node)

        system_node = self._node_finder(self._node_executable)
        if system_node:
            return str(system_node)

        raise WeChatKeyUnavailable(
            "微信连接组件缺少 Node.js 运行环境，"
            "请重新安装余音后重试。"
        )

    def _run_helper_buffered(
        self, command: list[str], options: dict[str, Any]
    ) -> str:
        """Run the helper through an injected runner, collecting output at once."""
        runner_options = dict(options)
        runner_options["capture_output"] = True
        runner_options["check"] = False
        try:
            result = self._subprocess_runner(command, **runner_options)
        except subprocess.TimeoutExpired:
            raise WeChatKeyUnavailable(
                _helper_timeout_message(), code="wechat_key_timeout"
            ) from None
        except (OSError, subprocess.SubprocessError):
            raise WeChatKeyUnavailable(_helper_launch_message()) from None
        except Exception:
            raise WeChatKeyUnavailable(
                "\u5fae\u4fe1\u8fde\u63a5\u51c6\u5907\u5931\u8d25\uff0c"
                "\u8bf7\u91cd\u8bd5\u3002"
            ) from None
        if result.returncode != 0:
            raise WeChatKeyUnavailable(
                _helper_failure_message(result.stderr),
                code=_helper_failure_code(result.stderr),
            )
        return self._finalize_key(result.stdout)

    def _run_helper_streaming(
        self,
        command: list[str],
        options: dict[str, Any],
        progress: Callable[[str], None] | None,
    ) -> str:
        """Run the helper and report each stderr line while it still runs.

        The helper writes only the key to stdout and every diagnostic to
        stderr, so a reader thread drains stderr into user-safe progress text
        while the main thread waits for stdout. Timeouts are distinguished from
        launch failures because they need different user guidance.
        """
        launcher = self._process_launcher or subprocess.Popen
        popen_options = dict(options)
        wait_timeout = popen_options.pop("timeout")
        popen_options["stdout"] = subprocess.PIPE
        popen_options["stderr"] = subprocess.PIPE
        popen_options["stdin"] = subprocess.DEVNULL

        try:
            process = launcher(command, **popen_options)
        except subprocess.TimeoutExpired:
            raise WeChatKeyUnavailable(
                _helper_timeout_message(), code="wechat_key_timeout"
            ) from None
        except (OSError, subprocess.SubprocessError):
            raise WeChatKeyUnavailable(_helper_launch_message()) from None

        recent_errors: list[str] = []
        reader = threading.Thread(
            target=self._drain_progress,
            args=(process.stderr, recent_errors, progress),
            daemon=True,
        )
        reader.start()

        stdout_lines: list[str] = []

        def _read_stdout(stream: Any) -> None:
            if stream is None:
                return
            try:
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    stdout_lines.append(line)
            except Exception:
                return

        stdout_reader = threading.Thread(
            target=_read_stdout,
            args=(process.stdout,),
            daemon=True,
        )
        stdout_reader.start()

        deadline = time.monotonic() + wait_timeout
        try:
            remaining = max(0.0, deadline - time.monotonic())
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            self._terminate(process)
            raise WeChatKeyUnavailable(
                _helper_timeout_message(), code="wechat_key_timeout"
            ) from None
        except (OSError, subprocess.SubprocessError):
            self._terminate(process)
            raise WeChatKeyUnavailable(_helper_launch_message()) from None
        finally:
            stdout_reader.join(timeout=1.0)
            reader.join(timeout=1.0)

        stdout = "".join(stdout_lines)
        if process.returncode not in (0, None):
            raise WeChatKeyUnavailable(
                _helper_failure_message("\n".join(recent_errors)),
                code=_helper_failure_code("\n".join(recent_errors)),
            )
        key = self._finalize_key(stdout)
        self._report_progress(_KEY_RECEIVED_MESSAGE, progress)
        return key

    def _drain_progress(
        self,
        stream: Any,
        recent_errors: list[str],
        progress: Callable[[str], None] | None = None,
    ) -> None:
        """Turn helper stderr lines into user-safe progress, never raising."""
        if stream is None:
            return
        try:
            while True:
                line = stream.readline()
                if not line:
                    break
                text = str(line).strip()
                if not text:
                    continue
                if len(recent_errors) >= _MAX_RETAINED_ERROR_LINES:
                    recent_errors.pop(0)
                recent_errors.append(text)
                self._report_progress(text, progress)
        except Exception:
            return

    def _report_progress(
        self,
        line: str,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        callback = progress or self._progress_callback
        if callback is None:
            return
        message = _progress_message(line)
        if message is None:
            return
        try:
            callback(message)
        except Exception as error:
            _LOGGER.warning(
                "wechat.progress.callback success=false error_type=%s",
                type(error).__name__,
            )
            return

    @staticmethod
    def _terminate(process: Any) -> None:
        """Stop a helper that outlived its deadline so it stops hooking WeChat."""
        try:
            process.kill()
        except Exception:
            return
        try:
            process.wait(timeout=5.0)
        except Exception:
            return

    @staticmethod
    def _finalize_key(stdout: Any) -> str:
        key = str(stdout or "").replace("\x00", "").strip()
        if len(key) < KEY_LENGTH:
            raise WeChatKeyUnavailable(
                "\u672a\u80fd\u83b7\u53d6\u5fae\u4fe1\u6570\u636e\u5e93"
                "\u5bc6\u94a5\uff0c\u8bf7\u91cd\u8bd5\u3002"
            )
        return key[:KEY_LENGTH].lower()

    # ---------------------------------------------------------------- internals

    def _poll_key(self, api: Any, deadline: float) -> str | None:
        while self._monotonic() < deadline:
            buffer = self._buffer_factory(BUFFER_SIZE)
            try:
                got = bool(api.poll_key(buffer, BUFFER_SIZE))
            except Exception:
                return None
            if got:
                key = _extract_key(buffer)
                if key:
                    return key
            self._sleep(self._poll_interval)
        return None

    @staticmethod
    def _error_text(api: Any) -> str:
        try:
            value = api.error_message()
        except Exception:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip()
        return str(value or "").strip()


def _expose_key_to_environment(key: str) -> None:
    """Share the just-acquired key with child processes (for example the
    WCDB diagnostic runner) for the lifetime of this process only."""
    os.environ[KEY_ENVIRONMENT_VARIABLE] = key


def _clear_key_environment() -> None:
    """Drop any previously exposed key so a failed acquisition never
    leaves a stale key behind for child processes."""
    os.environ.pop(KEY_ENVIRONMENT_VARIABLE, None)


def _helper_timeout_message() -> str:
    """Waiting ran out of time. The user can retry while WeChat logs in."""
    return (
        "Key \u83b7\u53d6\u8d85\u65f6\uff0c"
        "\u8bf7\u5728\u5fae\u4fe1\u767b\u5f55\u65f6\u91cd\u8bd5\u3002"
    )


def _helper_launch_message() -> str:
    """The helper process could not start at all."""
    return (
        "\u65e0\u6cd5\u542f\u52a8\u5fae\u4fe1\u8fde\u63a5\u7ec4\u4ef6\uff0c"
        "\u8bf7\u91cd\u65b0\u5b89\u88c5\u4f59\u97f3\u540e\u91cd\u8bd5\u3002"
    )


def _progress_message(line: str) -> str | None:
    """Map one helper stderr line to user-safe progress, or drop it.

    Only a whitelist becomes user-visible: helper diagnostics carry DLL paths
    and native export names that must never reach the GUI.
    """
    if "exports loaded" in line:
        return _COMPONENTS_READY_MESSAGE
    match = _ELAPSED_PATTERN.search(line)
    if match:
        return (
            "\u6b63\u5728\u7b49\u5f85\u5fae\u4fe1\u767b\u5f55\u2026"
            "\uff08\u5df2\u7b49\u5f85 "
            + match.group(1)
            + " \u79d2\uff09"
        )
    return None


def _helper_failure_message(stderr: Any) -> str:
    # Native/helper details stay out of the public error surface.
    detail = str(stderr or "").strip().lower()
    if "no weixin process" in detail:
        return "未检测到微信，请先打开并登录微信电脑版。"
    if "key unavailable" in detail or "timeout" in detail:
        return "Key 获取超时，请在微信登录时重试。"
    if "initializehook" in detail and "-> true" not in detail:
        return "微信 Hook 失败，当前微信进程可能不兼容。"
    if "dll" in detail or "load" in detail:
        return "微信连接组件加载失败，请重新安装余音后重试。"
    return "微信连接准备失败，请重试。"

def _helper_failure_code(stderr: Any) -> str:
    detail = str(stderr or "").lower()
    if "no weixin process" in detail:
        return "wechat_not_running"
    if "initializehook" in detail and "-> true" not in detail:
        return "wechat_hook_failed"
    if "timeout" in detail or "key unavailable" in detail:
        return "wechat_key_timeout"
    if "dll" in detail or "load" in detail:
        return "wechat_environment_missing"
    return "wechat_process_incompatible"


def _extract_key(buffer: Any) -> str | None:
    if hasattr(buffer, "raw"):
        raw = buffer.raw
    elif isinstance(buffer, (bytes, bytearray)):
        raw = bytes(buffer)
    else:
        raw = str(buffer).encode("utf-8", errors="replace")
    text = raw.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()
    if _KEY_PATTERN.fullmatch(text):
        return text.lower()
    return None


def _create_buffer(size: int) -> Any:
    return ctypes.create_string_buffer(size)


def _load_hook_api(path: Path) -> Any:
    if os.name != "nt":
        raise WeChatKeyUnavailable("\u4ec5\u652f\u6301 Windows \u5fae\u4fe1 4.x\u3002")
    library = ctypes.WinDLL(str(path))
    library.InitializeHook.argtypes = [wintypes.DWORD]
    library.InitializeHook.restype = wintypes.BOOL
    library.PollKeyData.argtypes = [ctypes.c_char_p, ctypes.c_int32]
    library.PollKeyData.restype = wintypes.BOOL
    library.CleanupHook.argtypes = []
    library.CleanupHook.restype = wintypes.BOOL
    library.GetLastErrorMsg.argtypes = []
    library.GetLastErrorMsg.restype = ctypes.c_char_p
    return _WxKeyHookApi(library)


class _WxKeyHookApi:
    """Thin ctypes adapter around the verified wx_key.dll exports."""

    def __init__(self, library: Any) -> None:
        self._initialize = library.InitializeHook
        self._poll = library.PollKeyData
        self._cleanup = library.CleanupHook
        self._error = library.GetLastErrorMsg

    def initialize(self, pid: int) -> bool:
        return bool(self._initialize(pid))

    def poll_key(self, buffer: Any, size: int) -> bool:
        return bool(self._poll(buffer, size))

    def cleanup(self) -> bool:
        return bool(self._cleanup())

    def error_message(self) -> bytes:
        return self._error() or b""


def _find_weixin_pids() -> list[int]:
    """Return every running Weixin.exe process id, never raising."""
    if os.name != "nt":
        return []

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (0, ctypes.c_void_p(-1).value):
        return []

    pids: list[int] = []
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == WECHAT_PROCESS_NAME.lower():
                pids.append(int(entry.th32ProcessID))
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return pids


__all__ = [
    "WeChatKeyService",
    "WeChatKeyUnavailable",
    "_extract_key",
]
