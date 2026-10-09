"""Contracts for externally managed chat runtimes.

The runtime layer describes what an external tool must offer so the
application can detect, start, stop and inspect it. Concrete runtime
implementations (for example the bundled Echo NapCat launcher) live here or
are injected by the desktop composition root; the application layer never
touches the external process directly.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from .windows_job import WindowsJobProcess, launch_owned_process


DEFAULT_READY_TIMEOUT_SECONDS = 30.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.5


class QQChatRuntimeError(Exception):
    """Base error for external chat runtime lifecycle failures."""

    code = "qq_runtime_error"
    public_message = "\u804a\u5929\u8fd0\u884c\u73af\u5883\u64cd\u4f5c\u5931\u8d25\u3002"

    def __init__(self, public_message: str | None = None) -> None:
        self.public_message = public_message or type(self).public_message
        super().__init__(self.public_message)


@dataclass(frozen=True, slots=True)
class RuntimeInfo:
    """Privacy-safe description of a running or installed runtime."""

    pid: int | None = None
    version: str | None = None
    owned_process: bool = False
    owned_process_handle: object | None = field(default=None, repr=False, compare=False)


@runtime_checkable
class ChatRuntime(Protocol):
    """Minimal surface a runtime manager needs from an external tool."""

    def is_installed(self) -> bool:  # pragma: no cover - contract only
        """Return whether the runtime binary or bundle exists."""
        ...

    def running(self) -> bool:  # pragma: no cover - contract only
        """Return whether the runtime process is currently running."""
        ...

    def start(self) -> RuntimeInfo:  # pragma: no cover - contract only
        """Start the runtime and return its process information."""
        ...

    def stop(self) -> None:  # pragma: no cover - contract only
        """Stop the runtime process."""
        ...

    def get_info(self) -> RuntimeInfo:  # pragma: no cover - contract only
        """Return the latest process information."""
        ...

    def wait_ready(self, timeout: float = 30.0) -> None:
        """Block until the runtime's service is ready or raise an error."""
        ...


@dataclass(frozen=True, slots=True)
class QQRuntimeConfig:
    """Everything needed to locate and launch a bundled QQ runtime."""

    executable_path: Path
    working_directory: Path
    base_url: str = "http://127.0.0.1:40655"
    version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable_path", Path(self.executable_path))
        object.__setattr__(self, "working_directory", Path(self.working_directory))


class BundledQQRuntime:
    """Launch and manage one locally bundled Echo NapCat runtime."""

    def __init__(
        self,
        config: QQRuntimeConfig,
        *,
        health_checker: object,
        ready_timeout: float = DEFAULT_READY_TIMEOUT_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        monotonic: object | None = None,
        launcher: object | None = None,
    ) -> None:
        self._config = config
        self._launcher = launcher
        self._health_checker = health_checker
        self._ready_timeout = ready_timeout
        self._poll_interval = poll_interval
        self._monotonic = monotonic or time.monotonic
        self._process: subprocess.Popen | WindowsJobProcess | None = None
        self._external_service = False
        self._lifecycle_lock = threading.RLock()
        self._generation = 0
        self._starting = False
        self._info = RuntimeInfo(
            pid=None,
            version=config.version,
            owned_process=False,
        )

    def is_installed(self) -> bool:
        return self._config.executable_path.is_file()

    def running(self) -> bool:
        process = self._process
        if process is None:
            return self._external_service and self._service_is_healthy()
        tree_running = getattr(process, "tree_running", None)
        return tree_running() if callable(tree_running) else process.poll() is None

    def start(self) -> RuntimeInfo:
        with self._lifecycle_lock:
            if self._starting:
                raise QQChatRuntimeError()
            if not self.is_installed():
                raise QQChatRuntimeError(
                    "\u672a\u627e\u5230\u90e8\u7f72\u7684 QQ \u8fd0\u884c\u73af\u5883\u3002"
                )
            if self._process is not None:
                if self.running():
                    return self._info
                self.stop()
            if self._service_is_healthy():
                self._process = None
                self._external_service = True
                self._info = RuntimeInfo(
                    pid=None,
                    version=self._config.version,
                    owned_process=False,
                )
                return self._info
            generation = self._generation
            self._starting = True
        launch_options = {
            "cwd": str(self._config.working_directory),
            "env": {**os.environ, "NAPCAT_DISABLE_FFMPEG_DOWNLOAD": "1"},
        }
        if os.name == "nt":
            launch_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            spawn = launch_owned_process if os.name == "nt" else subprocess.Popen
            process = self._launcher() if self._launcher is not None else spawn(
                [str(self._config.executable_path)],
                **launch_options,
            )
            with self._lifecycle_lock:
                if generation != self._generation:
                    self._close_process(process)
                    raise QQChatRuntimeError()
                self._process = process
                self._external_service = False
                self._info = RuntimeInfo(
                    pid=process.pid,
                    version=self._config.version,
                    owned_process=True,
                    owned_process_handle=process if callable(getattr(process, "close", None)) else None,
                )
                return self._info
        except OSError as error:
            raise QQChatRuntimeError() from error
        finally:
            with self._lifecycle_lock:
                self._starting = False

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._generation += 1
            process = self._process
            if process is None:
                return
            self._close_process(process)
            self._process = None
            self._info = RuntimeInfo(
                pid=None,
                version=self._config.version,
                owned_process=False,
            )

    @staticmethod
    def _close_process(process) -> None:
        close = getattr(process, "close", None)
        if callable(close):
            close()
        elif process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def get_info(self) -> RuntimeInfo:
        return self._info

    def wait_ready(self, timeout: float | None = None) -> None:
        if self._process is None and not self._external_service:
            raise QQChatRuntimeError(
                "\u8fd0\u884c\u73af\u5883\u5c1a\u672a\u542f\u52a8\uff0c"
                "\u65e0\u6cd5\u68c0\u6d4b\u5c31\u7eea\u72b6\u6001\u3002"
            )
        budget = self._ready_timeout if timeout is None else timeout
        deadline = self._monotonic() + budget
        while True:
            try:
                if self._health_checker(self._config.base_url):
                    return
            except Exception:
                pass
            if self._process is not None and not self.running():
                raise QQChatRuntimeError(
                    "\u8fd0\u884c\u73af\u5883\u8fdb\u7a0b\u5df2\u9000\u51fa\uff0c"
                    "\u65e0\u6cd5\u5c31\u7eea\u3002"
                )
            if self._monotonic() >= deadline:
                raise QQChatRuntimeError(
                    "\u8fd0\u884c\u73af\u5883\u542f\u52a8\u8d85\u65f6\uff0c"
                    "\u670d\u52a1\u672a\u5c31\u7eea\u3002"
                )
            time.sleep(self._poll_interval)

    def _service_is_healthy(self) -> bool:
        try:
            return bool(self._health_checker(self._config.base_url))
        except Exception:
            return False


__all__ = [
    "BundledQQRuntime",
    "ChatRuntime",
    "QQChatRuntimeError",
    "QQRuntimeConfig",
    "RuntimeInfo",
]
