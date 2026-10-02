"""RED-GREEN coverage for who owns Echo's shutdown cleanup.

Echo may only stop the processes it recorded, and a stuck or failing cleanup
step must never take the later steps - or the process exit - hostage. These
tests use fake services and fake PIDs only; nothing real is ever killed.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _facade_module():
    return importlib.import_module("qq_chat_analyzer.application.facade")


def _registry_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.qq_process_registry"
    )


def _fast_facade(**overrides):
    """Build a facade whose shutdown steps use a test-sized window."""
    module = _facade_module()
    overrides.setdefault("shutdown_step_seconds", 0.05)
    return module.ChatAnalyzerFacade(**overrides)


def test_shutdown_bounds_each_step_and_never_skips_runtime_termination() -> None:
    """A cleanup step that never returns must not stop runtime termination."""
    events: list[str] = []
    release = threading.Event()

    class _HungQQService:
        def shutdown(self) -> None:
            events.append("direct_db_cleanup")
            release.wait(5.0)

    class _TerminatingRegistry:
        def terminate_all(self) -> int:
            events.append("qq_terminate")
            return 0

    facade = _fast_facade(
        qq_service=_HungQQService(),
        qq_process_registry=_TerminatingRegistry(),
    )

    started = time.monotonic()
    facade.shutdown()
    elapsed = time.monotonic() - started

    assert events == ["direct_db_cleanup", "qq_terminate"]
    assert elapsed < 2.0
    release.set()


def test_shutdown_returns_when_runtime_termination_hangs() -> None:
    """A wedged process kill must not make shutdown wait forever."""
    release = threading.Event()

    class _TerminatingRegistry:
        def terminate_all(self) -> int:
            release.wait(5.0)
            return 0

    facade = _fast_facade(qq_process_registry=_TerminatingRegistry())

    started = time.monotonic()
    facade.shutdown()
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    release.set()


def test_shutdown_terminates_only_recorded_pids_by_pid_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Echo must never fall back to killing QQ by image name."""
    registry_module = _registry_module()
    facade_module = _facade_module()
    calls: list[list[str]] = []

    def _run(args, **kwargs):
        calls.append(list(args))

    monkeypatch.setattr(registry_module.os, "name", "nt")
    monkeypatch.setattr(
        registry_module.subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )
    monkeypatch.setattr(registry_module.subprocess, "run", _run)

    registry = registry_module.QQProcessRegistry()
    registry.record(1111)
    registry.record(2222)
    facade = facade_module.ChatAnalyzerFacade(qq_process_registry=registry)

    facade.shutdown()

    assert [call[0] for call in calls] == ["taskkill", "taskkill"]
    assert sorted(call[2] for call in calls) == ["1111", "2222"]
    for call in calls:
        assert call[1] == "/PID"
        assert call[3:] == ["/T", "/F"]
        assert "/IM" not in call


def test_repeated_shutdown_never_terminates_a_pid_twice() -> None:
    """Closing twice must not repeat an already finished cleanup."""
    registry_module = _registry_module()
    terminated: list[int] = []
    registry = registry_module.QQProcessRegistry(terminator=terminated.append)
    registry.record(4321)
    facade = _fast_facade(qq_process_registry=registry)

    facade.shutdown()
    facade.shutdown()

    assert terminated == [4321]


def test_shutdown_step_window_has_a_finite_default() -> None:
    module = _facade_module()

    assert module.DEFAULT_SHUTDOWN_STEP_SECONDS > 0


def test_facade_shutdown_closes_the_direct_db_gate_before_terminating() -> None:
    """Order matters: plaintext recover, then the owned runtime tree."""
    direct_db = importlib.import_module(
        "qq_chat_analyzer.application.qq_direct_database_import_service"
    )
    events: list[str] = []

    class _RecordingClient:
        def recover(self, *, deadline: float | None = None) -> None:
            events.append("recover")

        def acquire(self) -> str:
            raise AssertionError("no generation may be acquired after shutdown")

        def generation_directory(self, generation_id):
            raise AssertionError("no generation directory after shutdown")

        def cleanup(self, generation_id) -> None:
            raise AssertionError("nothing to clean after shutdown")

    class _TerminatingRegistry:
        def terminate_all(self) -> int:
            events.append("qq_terminate")
            return 0

    service = direct_db.QQDirectDatabaseImportService(
        runtime_client=_RecordingClient(),
        shutdown_drain_seconds=0.05,
    )
    service.start()
    events.clear()
    facade = _fast_facade(
        qq_service=service,
        qq_process_registry=_TerminatingRegistry(),
    )

    facade.shutdown()

    assert events == ["recover", "qq_terminate"]
    assert service.state is direct_db.QQDirectDatabaseState.CLOSED
    with pytest.raises(direct_db.QQDirectDatabaseShuttingDown):
        service.list_sessions()
