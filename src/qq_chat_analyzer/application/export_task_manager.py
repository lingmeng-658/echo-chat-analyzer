"""Lightweight application-layer management for QCE export tasks.

The QCE provider owns HTTP, polling and the raw task lifecycle. This module
only translates provider snapshots and provider failures into a stable,
user-facing task state, so a future GUI never has to read ``task_id``,
``running``/``completed`` strings, or provider exceptions itself.

Deliberate boundaries:

* No asynchronous machinery. ``wait_for_completion`` simply delegates to the
  provider's blocking ``wait_export_task``; the GUI will decide later whether
  to call it on a worker thread.
* No task logic is added to ``QQExportImportService``. This manager is a
  separate application-layer service with a narrow provider protocol.
* Provider exceptions never escape. They are converted to terminal
  ``ExportTaskStatus`` values carrying the provider's own user-facing text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..providers.qq_chat_exporter_provider import (
    ExportTaskCancelled,
    ExportTaskFailed,
    ExportTimeout,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
)


STATE_CREATED = "created"
STATE_EXPORTING = "exporting"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

MESSAGE_CREATED = "\u5bfc\u51fa\u4efb\u52a1\u5df2\u521b\u5efa\u3002"
MESSAGE_EXPORTING = "\u6b63\u5728\u5bfc\u51fa\u7fa4\u804a\u8bb0\u5f55\u3002"
MESSAGE_COMPLETED = "\u7fa4\u804a\u8bb0\u5f55\u5bfc\u51fa\u5b8c\u6210\u3002"
MESSAGE_FAILED = "\u7fa4\u804a\u8bb0\u5f55\u5bfc\u51fa\u5931\u8d25\u3002"
MESSAGE_CANCELLED = "\u5bfc\u51fa\u4efb\u52a1\u5df2\u88ab\u53d6\u6d88\u3002"
MESSAGE_UNKNOWN_ERROR = (
    "\u65e0\u6cd5\u786e\u8ba4\u5bfc\u51fa\u4efb\u52a1\u72b6\u6001\uff0c"
    "\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
)


class ExportTaskState(str, Enum):
    """User-facing lifecycle state of one export task."""

    CREATED = STATE_CREATED
    EXPORTING = STATE_EXPORTING
    COMPLETED = STATE_COMPLETED
    FAILED = STATE_FAILED
    CANCELLED = STATE_CANCELLED


@dataclass(frozen=True, slots=True)
class ExportTaskStatus:
    """User-facing snapshot of one export task.

    ``message`` is always safe to show directly. ``error`` carries optional
    detail from the provider task (for example the QCE failure reason) and is
    never a Python exception or traceback.
    """

    task_id: str
    state: ExportTaskState
    progress: int
    message: str
    error: str = ""


@runtime_checkable
class ExportTaskProvider(Protocol):
    """Minimal surface the manager needs from a QCE provider."""

    def create_export_task(
        self,
        group_code: str,
        start_time: Any = None,
        end_time: Any = None,
        session_name: str | None = None,
        output_dir: str | None = None,
    ) -> Any:  # pragma: no cover - contract only
        """Register an export task and return its initial snapshot."""
        ...

    def get_export_task(self, task_id: str) -> Any:  # pragma: no cover
        """Fetch one task snapshot."""
        ...

    def wait_export_task(
        self,
        task_id: str,
        timeout: float = 900,
        poll_interval: float = 2.0,
    ) -> Path:  # pragma: no cover - contract only
        """Block until the task settles and return the export file path."""
        ...


class ExportTaskManager:
    """Translate QCE task snapshots into :class:`ExportTaskStatus` values."""

    def __init__(self, provider: ExportTaskProvider) -> None:
        self._provider = provider
        self._task_id = ""

    @property
    def current_task_id(self) -> str:
        """Return the task created by the most recent ``start_export``."""
        return self._task_id

    def start_export(
        self,
        group_code: str,
        start_time: Any = None,
        end_time: Any = None,
        session_name: str | None = None,
        output_dir: str | None = None,
    ) -> ExportTaskStatus:
        """Ask the provider to register an export and return its status."""
        task = self._provider.create_export_task(
            group_code,
            start_time=start_time,
            end_time=end_time,
            session_name=session_name,
            output_dir=output_dir,
        )
        self._task_id = _clean_str(getattr(task, "task_id", ""))
        return ExportTaskStatus(
            task_id=self._task_id,
            state=ExportTaskState.CREATED,
            progress=0,
            message=MESSAGE_CREATED,
        )

    def get_status(self) -> ExportTaskStatus:
        """Fetch the current task snapshot and map it to a user state."""
        task_id = self._require_task_id()
        try:
            task = self._provider.get_export_task(task_id)
        except Exception as error:
            return self._failed_status(
                task_id,
                message=_public_message(error, MESSAGE_UNKNOWN_ERROR),
                error=_error_detail(error),
            )
        return self._from_task(task_id, task)

    def wait_for_completion(
        self,
        timeout: float = 900,
        poll_interval: float = 2.0,
    ) -> ExportTaskStatus:
        """Block until the provider reports a terminal task state.

        Provider failures are translated into terminal statuses instead of
        being raised, so callers always receive a ``ExportTaskStatus``.
        """
        task_id = self._require_task_id()
        try:
            self._provider.wait_export_task(
                task_id,
                timeout=timeout,
                poll_interval=poll_interval,
            )
        except ExportTaskFailed as error:
            return self._failed_status(
                task_id,
                message=_public_message(error, MESSAGE_FAILED),
                error=_error_detail(error),
            )
        except ExportTaskCancelled:
            return ExportTaskStatus(
                task_id=task_id,
                state=ExportTaskState.CANCELLED,
                progress=0,
                message=MESSAGE_CANCELLED,
            )
        except ExportTimeout as error:
            return self._failed_status(
                task_id,
                message=_public_message(error, MESSAGE_UNKNOWN_ERROR),
                error=_error_detail(error),
            )
        except Exception as error:
            return self._failed_status(
                task_id,
                message=_public_message(error, MESSAGE_UNKNOWN_ERROR),
                error=_error_detail(error),
            )
        return ExportTaskStatus(
            task_id=task_id,
            state=ExportTaskState.COMPLETED,
            progress=100,
            message=MESSAGE_COMPLETED,
        )

    # ---------------------------------------------------------------- internals

    def _from_task(self, task_id: str, task: Any) -> ExportTaskStatus:
        state = _user_state(getattr(task, "status", ""))
        progress = _optional_int(getattr(task, "progress", 0)) or 0
        message = {
            ExportTaskState.EXPORTING: MESSAGE_EXPORTING,
            ExportTaskState.COMPLETED: MESSAGE_COMPLETED,
            ExportTaskState.FAILED: MESSAGE_FAILED,
            ExportTaskState.CANCELLED: MESSAGE_CANCELLED,
        }.get(state, MESSAGE_EXPORTING)
        return ExportTaskStatus(
            task_id=task_id,
            state=state,
            progress=progress,
            message=message,
            error=_clean_str(getattr(task, "error", "")),
        )

    def _failed_status(
        self,
        task_id: str,
        *,
        message: str,
        error: str,
    ) -> ExportTaskStatus:
        return ExportTaskStatus(
            task_id=task_id,
            state=ExportTaskState.FAILED,
            progress=0,
            message=message,
            error=error,
        )

    def _require_task_id(self) -> str:
        if not self._task_id:
            raise RuntimeError("no export task has been started")
        return self._task_id


def _user_state(provider_status: str) -> ExportTaskState:
    status = provider_status.strip().lower()
    if status == STATUS_COMPLETED:
        return ExportTaskState.COMPLETED
    if status == STATUS_FAILED:
        return ExportTaskState.FAILED
    if status == STATUS_CANCELLED:
        return ExportTaskState.CANCELLED
    if status == STATUS_RUNNING:
        return ExportTaskState.EXPORTING
    return ExportTaskState.EXPORTING


def _public_message(error: Exception, fallback: str) -> str:
    message = getattr(error, "public_message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    text = str(error).strip()
    if text:
        return fallback
    return fallback


def _error_detail(error: Exception) -> str:
    value = getattr(error, "error", None)
    if isinstance(value, str):
        return value.strip()
    if isinstance(error, ExportTaskFailed):
        return error.error or ""
    return ""


def _clean_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None

