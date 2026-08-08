"""Contracts for externally managed chat runtimes.

The runtime layer describes what an external tool must offer so the
application can detect, start, stop and inspect it. Concrete runtime
implementations (for example a bundled QQChatExporter executable) live here or
are injected by the desktop composition root; the application layer never
touches the external process directly.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


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
    base_url: str = "http://127.0.0.1:40653"
    config_directory: Path | None = None
    security_path: Path | None = None
    version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable_path", Path(self.executable_path))
        object.__setattr__(self, "working_directory", Path(self.working_directory))
        if self.config_directory is not None:
            object.__setattr__(
                self,
                "config_directory",
                Path(self.config_directory),
            )
        if self.security_path is None and self.config_directory is not None:
            object.__setattr__(
                self,
                "security_path",
                self.config_directory / "security.json",
            )
        if self.security_path is not None:
            object.__setattr__(self, "security_path", Path(self.security_path))


def default_health_checker(base_url: str) -> bool:
    """Probe ``/api/health`` without parsing any provider-specific payload."""
    try:
        with urllib.request.urlopen(  # noqa: S310 - local runtime only
            f"{base_url.rstrip('/')}/api/health",
            timeout=1,
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


class BundledQQRuntime:
    """Launch and manage one locally bundled QQChatExporter executable."""

    def __init__(
        self,
        config: QQRuntimeConfig,
        *,
        health_checker: object | None = None,
        ready_timeout: float = DEFAULT_READY_TIMEOUT_SECONDS,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        monotonic: object | None = None,
    ) -> None:
        self._config = config
        self._health_checker = health_checker or default_health_checker
        self._ready_timeout = ready_timeout
        self._poll_interval = poll_interval
        self._monotonic = monotonic or time.monotonic
        self._process: subprocess.Popen | None = None
        self._info = RuntimeInfo(pid=None, version=config.version)

    def is_installed(self) -> bool:
        return self._config.executable_path.is_file()

    def running(self) -> bool:
        process = self._process
        if process is None:
            return False
        return process.poll() is None

    def start(self) -> RuntimeInfo:
        if not self.is_installed():
            raise QQChatRuntimeError(
                "\u672a\u627e\u5230\u90e8\u7f72\u7684 QQ \u8fd0\u884c\u73af\u5883\u3002"
            )
        try:
            process = subprocess.Popen(
                [str(self._config.executable_path)],
                cwd=str(self._config.working_directory),
                env=os.environ.copy(),
            )
        except OSError as error:
            raise QQChatRuntimeError() from error
        self._process = process
        self._info = RuntimeInfo(
            pid=process.pid,
            version=self._config.version,
        )
        return self._info

    def stop(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._process = None
        self._info = RuntimeInfo(pid=None, version=self._config.version)

    def get_info(self) -> RuntimeInfo:
        return self._info

    def wait_ready(self, timeout: float | None = None) -> None:
        if self._process is None:
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
            if self._process.poll() is not None:
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


__all__ = [
    "BundledQQRuntime",
    "ChatRuntime",
    "QQChatRuntimeError",
    "QQRuntimeConfig",
    "RuntimeInfo",
    "default_health_checker",
]
