"""Tests for the QQ process registry.

Only fake PIDs and injected terminators are used; nothing is ever killed.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _module():
    return importlib.import_module(
        "qq_chat_analyzer.application.qq_process_registry"
    )


class _RecordingTerminator:
    def __init__(self):
        self.terminated: list[int] = []

    def __call__(self, pid: int) -> None:
        self.terminated.append(pid)


def test_record_keeps_only_valid_pids() -> None:
    module = _module()
    registry = module.QQProcessRegistry()

    registry.record(1001)
    registry.record(1001)
    registry.record(0)
    registry.record(-1)
    registry.record(True)
    registry.record(None)

    assert registry.recorded() == (1001,)


def test_terminate_all_stops_only_recorded_pids() -> None:
    module = _module()
    terminator = _RecordingTerminator()
    registry = module.QQProcessRegistry(terminator=terminator)
    registry.record(2001)

    count = registry.terminate_all()

    assert count == 1
    assert terminator.terminated == [2001]
    assert registry.recorded() == ()


def test_terminate_all_never_raises_on_terminator_failure() -> None:
    module = _module()

    def _explode(pid: int) -> None:
        raise OSError("cannot kill")

    registry = module.QQProcessRegistry(terminator=_explode)
    registry.record(3001)

    assert registry.terminate_all() == 1


def test_windows_taskkill_hides_its_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def _run(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(
        module.subprocess,
        "CREATE_NO_WINDOW",
        0x08000000,
        raising=False,
    )
    monkeypatch.setattr(module.subprocess, "run", _run)

    module._terminate_process_tree(6001)

    assert calls == [
        (
            ["taskkill", "/PID", "6001", "/T", "/F"],
            {
                "capture_output": True,
                "timeout": 5,
                "check": False,
                "creationflags": 0x08000000,
            },
        )
    ]


def test_discard_forgets_one_pid() -> None:
    module = _module()
    registry = module.QQProcessRegistry()
    registry.record(4001)
    registry.record(4002)

    registry.discard(4001)

    assert registry.recorded() == (4002,)


def test_clear_forgets_everything_without_terminating() -> None:
    module = _module()
    terminator = _RecordingTerminator()
    registry = module.QQProcessRegistry(terminator=terminator)
    registry.record(5001)

    registry.clear()

    assert registry.recorded() == ()
    assert terminator.terminated == []


def test_default_registry_is_shared() -> None:
    module = _module()

    assert (
        module.default_qq_process_registry()
        is module.default_qq_process_registry()
    )
