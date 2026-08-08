"""Background execution for facade calls.

Every facade call is potentially slow: listing WeChat sessions touches an
external CLI, and analysis walks the whole message set. Running those on the
Qt main thread would freeze the window, so this module moves them onto a
worker thread and reports back through signals.

The worker knows nothing about analysis. It runs a callable, then emits either
the result or a :class:`FacadeError`. That keeps every decision about *what*
to run on the page, and every decision about *how* to report failure in one
place.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ..application.facade import FacadeError


GENERIC_ERROR_MESSAGE = (
    "\u5206\u6790\u8fc7\u7a0b\u51fa\u73b0\u672a\u9884\u671f\u7684\u9519"
    "\u8bef\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
)

# Workers are kept alive until they report completion. The thread pool would
# otherwise delete a finished QRunnable together with its signal object, and
# any cross-thread callback still queued for the UI thread would be dropped.
_PENDING: set["FacadeWorker"] = set()

_WORKER_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.worker")


class WorkerSignals(QObject):
    """Signals emitted by :class:`FacadeWorker`."""

    succeeded = Signal(object)
    failed = Signal(str, str)
    finished = Signal()


class FacadeWorker(QRunnable):
    """Run one facade call off the UI thread."""

    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self._operation = operation
        self.signals = WorkerSignals()
        self.setAutoDelete(False)

    @Slot()
    def run(self) -> None:
        try:
            result = self._operation()
        except FacadeError as error:
            _WORKER_LOGGER.warning(
                "facade operation failed code=%s message=%s",
                error.code,
                error.public_message,
            )
            self.signals.failed.emit(error.code, error.public_message)
        except Exception as error:
            _WORKER_LOGGER.exception("facade operation crashed", exc_info=error)
            self.signals.failed.emit("unexpected_error", GENERIC_ERROR_MESSAGE)
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()


def submit(
    operation: Callable[[], Any],
    *,
    on_success: Callable[[Any], None],
    on_error: Callable[[str, str], None],
    on_finished: Callable[[], None] | None = None,
    pool: QThreadPool | None = None,
) -> FacadeWorker:
    """Queue ``operation`` and wire its outcome to the given callbacks."""
    worker = FacadeWorker(operation)
    worker.signals.succeeded.connect(on_success)
    worker.signals.failed.connect(on_error)
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)
    worker.signals.finished.connect(lambda: _PENDING.discard(worker))

    _PENDING.add(worker)
    (pool or QThreadPool.globalInstance()).start(worker)
    return worker


def run_inline(
    operation: Callable[[], Any],
    *,
    on_success: Callable[[Any], None],
    on_error: Callable[[str, str], None],
    on_finished: Callable[[], None] | None = None,
) -> None:
    """Run ``operation`` on the calling thread.

    Useful for tests and for callers that need a deterministic, synchronous
    result. The failure translation is identical to :func:`submit`, so the
    surrounding page cannot tell the two apart.
    """
    try:
        result = operation()
    except FacadeError as error:
        on_error(error.code, error.public_message)
    except Exception:
        on_error("unexpected_error", GENERIC_ERROR_MESSAGE)
    else:
        on_success(result)
    finally:
        if on_finished is not None:
            on_finished()
