"""Behavior tests for the application-layer export task manager.

No real QCE service is contacted. A stub provider replays fictional task
snapshots and exceptions so the manager's translation and state mapping are
covered without touching real chat data or tokens.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _module():
    return importlib.import_module(
        "qq_chat_analyzer.application.export_task_manager"
    )


def _provider_module():
    return importlib.import_module(
        "qq_chat_analyzer.providers.qq_chat_exporter_provider"
    )


def _task(
    task_id: str = "export-1",
    status: str = "running",
    progress: int = 0,
    error: str = "",
    file_path: str = "",
) -> object:
    provider = _provider_module()
    return provider.ExportTask(
        task_id=task_id,
        status=status,
        progress=progress,
        error=error,
        file_path=file_path,
    )


class _StubProvider:
    """Replays fictional QCE task snapshots and wait behaviour."""

    def __init__(
        self,
        *,
        snapshots: list[object] | None = None,
        get_error: Exception | None = None,
        wait_error: Exception | None = None,
        wait_path: Path | None = None,
    ) -> None:
        self._snapshots = list(snapshots or [])
        self._get_error = get_error
        self._wait_error = wait_error
        self._wait_path = wait_path
        self.create_calls = 0
        self.create_requests: list[dict[str, object]] = []
        self.get_calls = 0
        self.wait_calls = 0

    def create_export_task(
        self,
        group_code: str,
        start_time: object = None,
        end_time: object = None,
        **kwargs: object,
    ):
        self.create_calls += 1
        self.create_requests.append(
            {
                "group_code": group_code,
                "start_time": start_time,
                "end_time": end_time,
                "session_name": kwargs.get("session_name"),
            }
        )
        return _task(task_id="export-1", status="running", progress=0)

    def get_export_task(self, task_id: str):
        self.get_calls += 1
        if self._get_error is not None:
            raise self._get_error
        if self._snapshots:
            return self._snapshots.pop(0)
        return _task(task_id=task_id, status="running", progress=0)

    def wait_export_task(
        self,
        task_id: str,
        timeout: float = 900,
        poll_interval: float = 2.0,
    ):
        self.wait_calls += 1
        if self._wait_error is not None:
            raise self._wait_error
        return self._wait_path


def _manager(**provider_kwargs) -> tuple[object, _StubProvider]:
    provider = _StubProvider(**provider_kwargs)
    manager = _module().ExportTaskManager(provider)
    return manager, provider


# ------------------------------------------------------------ happy path


def test_start_export_creates_a_task_and_returns_created_status() -> None:
    manager, provider = _manager()

    status = manager.start_export("10001")

    assert provider.create_calls == 1
    assert status.state == _module().ExportTaskState.CREATED
    assert status.task_id == "export-1"
    assert status.progress == 0
    assert status.message != ""
    assert status.error == ""


def test_start_export_forwards_time_window_and_session_name() -> None:
    provider = _StubProvider()
    manager = _module().ExportTaskManager(provider)

    manager.start_export(
        "10001",
        start_time=1700000000,
        end_time=1800000000,
        session_name="fictional-session",
    )

    assert provider.create_calls == 1
    assert provider.create_requests == [
        {
            "group_code": "10001",
            "start_time": 1700000000,
            "end_time": 1800000000,
            "session_name": "fictional-session",
        }
    ]


def test_get_status_maps_running_snapshot_to_exporting() -> None:
    manager, provider = _manager(
        snapshots=[_task(status="running", progress=35)]
    )
    manager.start_export("10001")

    status = manager.get_status()

    assert provider.get_calls == 1
    assert status.task_id == "export-1"
    assert status.state == _module().ExportTaskState.EXPORTING
    assert status.progress == 35
    assert status.message != ""
    assert status.error == ""


def test_get_status_maps_completed_snapshot() -> None:
    manager, _ = _manager(
        snapshots=[_task(status="completed", progress=100)]
    )
    manager.start_export("10001")

    status = manager.get_status()

    assert status.state == _module().ExportTaskState.COMPLETED
    assert status.progress == 100


def test_get_status_maps_failed_snapshot_with_error() -> None:
    manager, _ = _manager(
        snapshots=[
            _task(status="failed", progress=42, error="napcat disconnected")
        ]
    )
    manager.start_export("10001")

    status = manager.get_status()

    assert status.state == _module().ExportTaskState.FAILED
    assert status.progress == 42
    assert status.error == "napcat disconnected"
    assert status.message != ""


def test_get_status_maps_cancelled_snapshot() -> None:
    manager, _ = _manager(snapshots=[_task(status="cancelled", progress=60)])
    manager.start_export("10001")

    status = manager.get_status()

    assert status.state == _module().ExportTaskState.CANCELLED
    assert status.progress == 60


def test_wait_for_completion_returns_completed_status(tmp_path: Path) -> None:
    export_path = tmp_path / "fictional_export.json"
    manager, provider = _manager(wait_path=export_path)
    manager.start_export("10001")

    status = manager.wait_for_completion()

    assert provider.wait_calls == 1
    assert status.state == _module().ExportTaskState.COMPLETED
    assert status.progress == 100
    assert status.task_id == "export-1"
    assert status.message != ""


# ------------------------------------------------------------- failure paths


def test_wait_for_completion_turns_task_failure_into_failed_status() -> None:
    provider_module = _provider_module()
    manager, _ = _manager(
        wait_error=provider_module.ExportTaskFailed("napcat disconnected")
    )
    manager.start_export("10001")

    status = manager.wait_for_completion()

    assert status.state == _module().ExportTaskState.FAILED
    assert status.message != ""
    assert "napcat disconnected" in status.error
    assert "Traceback" not in status.message


def test_wait_for_completion_turns_cancellation_into_cancelled_status() -> None:
    provider_module = _provider_module()
    manager, _ = _manager(
        wait_error=provider_module.ExportTaskCancelled()
    )
    manager.start_export("10001")

    status = manager.wait_for_completion()

    assert status.state == _module().ExportTaskState.CANCELLED
    assert status.message != ""
    assert status.error == ""


def test_wait_for_completion_converts_provider_timeout() -> None:
    provider_module = _provider_module()
    manager, _ = _manager(wait_error=provider_module.ExportTimeout())
    manager.start_export("10001")

    status = manager.wait_for_completion()

    assert status.state == _module().ExportTaskState.FAILED
    assert status.message != ""


# ------------------------------------------------------ provider exceptions


def test_get_status_never_leaks_provider_exception() -> None:
    class _FakeBoom(Exception):
        public_message = "\u5bfc\u51fa\u8fc7\u7a0b\u4e2d\u51fa\u73b0\u9519\u8bef\u3002"

    manager, _ = _manager(get_error=_FakeBoom("internal http failure"))
    manager.start_export("10001")

    status = manager.get_status()

    assert status.state == _module().ExportTaskState.FAILED
    assert status.message != ""
    assert "internal http failure" not in status.message
    assert "Traceback" not in status.message
    assert "ExportTask" not in status.message


def test_wait_for_completion_never_leaks_unexpected_exception() -> None:
    manager, _ = _manager(
        wait_error=RuntimeError("raw polling crash with secret detail")
    )
    manager.start_export("10001")

    status = manager.wait_for_completion()

    assert status.state == _module().ExportTaskState.FAILED
    assert "raw polling crash with secret detail" not in status.message
    assert "Traceback" not in status.message


# ------------------------------------------------------- status correctness


def test_status_model_is_frozen_and_has_required_fields() -> None:
    module = _module()
    status = module.ExportTaskStatus(
        task_id="export-1",
        state=module.ExportTaskState.CREATED,
        progress=0,
        message="\u521b\u5efa\u5b8c\u6210",
        error="",
    )

    assert {field.name for field in __import__("dataclasses").fields(status)} == {
        "task_id",
        "state",
        "progress",
        "message",
        "error",
    }
    try:
        status.message = "changed"
    except Exception as error:
        assert type(error).__name__ == "FrozenInstanceError"
    else:  # pragma: no cover - guards the immutability contract
        raise AssertionError("ExportTaskStatus should be immutable")


def test_state_enum_covers_the_required_states() -> None:
    module = _module()

    assert {
        module.ExportTaskState.CREATED,
        module.ExportTaskState.EXPORTING,
        module.ExportTaskState.COMPLETED,
        module.ExportTaskState.FAILED,
    } <= set(module.ExportTaskState)


def test_task_manager_imports_no_gui_framework() -> None:
    module = _module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    for forbidden in ("PySide", "PyQt", "tkinter", "sqlite3"):
        assert forbidden not in source
