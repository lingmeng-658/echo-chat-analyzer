"""Behavior tests for the QQ runtime manager.

The manager is exercised against a fake
:class:`~qq_chat_analyzer.runtime.ChatRuntime` so no
real executable, process, or external tool is ever started. Every assertion
focuses on the user-facing lifecycle state the manager must produce.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _manager_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.runtime.qq_runtime_manager"
    )


class _FakeRuntime:
    """Stand in for a real installed QQ runtime."""

    def __init__(
        self,
        *,
        installed: bool = True,
        running: bool = False,
        pid: int | None = 4242,
        version: str | None = "1.0.0",
        start_error: Exception | None = None,
        stop_error: Exception | None = None,
        ready: bool = True,
        ready_error: Exception | None = None,
    ) -> None:
        self._installed = installed
        self._running = running
        self._pid = pid
        self._version = version
        self._start_error = start_error
        self._stop_error = stop_error
        self._ready = ready
        self._ready_error = ready_error
        self.start_calls = 0
        self.stop_calls = 0
        self.wait_ready_calls = 0

    def is_installed(self) -> bool:
        return self._installed

    def running(self) -> bool:
        return self._running

    def start(self):
        self.start_calls += 1
        if self._start_error is not None:
            raise self._start_error
        self._running = True
        return type("Info", (), {"pid": self._pid, "version": self._version})()

    def stop(self) -> None:
        self.stop_calls += 1
        if self._stop_error is not None:
            raise self._stop_error
        self._running = False

    def wait_ready(self, timeout: float = 30.0) -> None:
        self.wait_ready_calls += 1
        if self._ready_error is not None:
            raise self._ready_error
        if not self._ready:
            raise RuntimeError("runtime not ready")

    def get_info(self):
        return type("Info", (), {"pid": self._pid, "version": self._version})()


def _manager(runtime: _FakeRuntime):
    return _manager_module().QQRuntimeManager(
        runtime,
        config_preparer=_RecordingConfigPreparer(),
        process_registry=_FreshProcessRegistry(),
    )


def _manager_with_preparer(runtime: _FakeRuntime, preparer):
    return _manager_module().QQRuntimeManager(
        runtime,
        config_preparer=preparer,
        process_registry=_FreshProcessRegistry(),
    )


def _manager_with_registry(runtime: _FakeRuntime, registry):
    return _manager_module().QQRuntimeManager(
        runtime,
        config_preparer=_RecordingConfigPreparer(),
        process_registry=registry,
    )


class _RecordingConfigPreparer:
    """Record QCE config preparation without touching real files."""

    def __init__(self):
        self.calls = 0

    def __call__(self) -> bool:
        self.calls += 1
        return True


def _FreshProcessRegistry():
    module = importlib.import_module(
        "qq_chat_analyzer.application.qq_process_registry"
    )
    return module.QQProcessRegistry()


# --------------------------------------------------------------- availability


def test_runtime_exists_reports_available_and_stopped() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=True, running=False)

    manager = _manager(runtime)

    assert manager.is_available() is True
    status = manager.get_status()
    assert status.state == module.QQRuntimeState.STOPPED
    assert status.available is True
    assert status.message != ""


def test_runtime_missing_reports_unavailable() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=False)

    manager = _manager(runtime)

    assert manager.is_available() is False
    status = manager.get_status()
    assert status.state == module.QQRuntimeState.UNAVAILABLE
    assert status.available is False
    assert status.message != ""
    assert status.action_hint != ""


# ------------------------------------------------------------------- starting


def test_start_success_returns_running_status() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=True, running=False, pid=777, version="2.0.0")
    manager = _manager(runtime)

    status = manager.start()

    assert runtime.start_calls == 1
    assert status.state == module.QQRuntimeState.RUNNING
    assert status.available is True
    assert status.pid == 777
    assert status.version == "2.0.0"
    assert status.message != ""
    assert manager.get_status().state == module.QQRuntimeState.RUNNING


def test_start_returns_running_without_waiting_for_readiness() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=True, running=False, ready=False)
    manager = _manager(runtime)

    status = manager.start()

    assert runtime.wait_ready_calls == 0
    assert runtime.stop_calls == 0
    assert status.state == module.QQRuntimeState.RUNNING
    assert manager.get_status().state == module.QQRuntimeState.RUNNING


def test_start_failure_returns_error_without_leaking_exception() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(
        installed=True,
        running=False,
        start_error=RuntimeError("runtime launch exploded with secret"),
    )
    manager = _manager(runtime)

    status = manager.start()

    assert status.state == module.QQRuntimeState.ERROR
    assert status.available is True
    assert "runtime launch exploded with secret" not in status.message
    assert "Traceback" not in status.message
    assert status.action_hint != ""
    assert manager.get_status().state == module.QQRuntimeState.ERROR


def test_start_requires_an_installed_runtime() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=False)
    manager = _manager(runtime)

    status = manager.start()

    assert runtime.start_calls == 0
    assert status.state == module.QQRuntimeState.UNAVAILABLE
    assert status.action_hint != ""


def test_start_prepares_qce_webui_config_before_launch() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=True, running=False)
    preparer = _RecordingConfigPreparer()
    manager = _manager_with_preparer(runtime, preparer)

    status = manager.start()

    assert preparer.calls == 1
    assert runtime.start_calls == 1
    assert status.state == module.QQRuntimeState.RUNNING


def test_start_skips_qce_config_when_runtime_unavailable() -> None:
    runtime = _FakeRuntime(installed=False)
    preparer = _RecordingConfigPreparer()
    manager = _manager_with_preparer(runtime, preparer)

    manager.start()

    assert preparer.calls == 0
    assert runtime.start_calls == 0


def test_start_records_the_launched_pid() -> None:
    module = importlib.import_module(
        "qq_chat_analyzer.application.qq_process_registry"
    )
    runtime = _FakeRuntime(installed=True, running=False, pid=4242)
    registry = module.QQProcessRegistry()
    manager = _manager_with_registry(runtime, registry)

    manager.start()

    assert registry.recorded() == (4242,)


def test_stop_discards_the_recorded_pid() -> None:
    module = importlib.import_module(
        "qq_chat_analyzer.application.qq_process_registry"
    )
    runtime = _FakeRuntime(installed=True, running=False, pid=4242)
    registry = module.QQProcessRegistry()
    manager = _manager_with_registry(runtime, registry)
    manager.start()

    manager.stop()

    assert registry.recorded() == ()


# ------------------------------------------------------------------- stopping


def test_stop_success_returns_stopped_status() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=True, running=True)
    manager = _manager(runtime)
    manager.start()

    status = manager.stop()

    assert runtime.stop_calls == 1
    assert status.state == module.QQRuntimeState.STOPPED
    assert status.pid is None
    assert status.message != ""
    assert manager.get_status().state == module.QQRuntimeState.STOPPED


def test_stop_when_not_running_returns_error() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=True, running=False)
    manager = _manager(runtime)

    status = manager.stop()

    assert runtime.stop_calls == 0
    assert status.state == module.QQRuntimeState.ERROR
    assert status.action_hint != ""


def test_stop_failure_returns_error_without_leaking_exception() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(
        installed=True,
        running=True,
        stop_error=RuntimeError("stop exploded with secret"),
    )
    manager = _manager(runtime)
    manager.start()

    status = manager.stop()

    assert status.state == module.QQRuntimeState.ERROR
    assert "stop exploded with secret" not in status.message
    assert "Traceback" not in status.message


# --------------------------------------------------------- state transitions


def test_state_transitions_are_correct() -> None:
    module = _manager_module()
    runtime = _FakeRuntime(installed=True, running=False)
    manager = _manager(runtime)

    assert manager.get_status().state == module.QQRuntimeState.STOPPED
    assert manager.start().state == module.QQRuntimeState.RUNNING
    assert manager.get_status().state == module.QQRuntimeState.RUNNING
    assert manager.stop().state == module.QQRuntimeState.STOPPED
    assert manager.get_status().state == module.QQRuntimeState.STOPPED


def test_runtime_manager_imports_no_gui_framework() -> None:
    module = _manager_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    for forbidden in ("PySide", "PyQt", "tkinter", "sqlite3"):
        assert forbidden not in source
