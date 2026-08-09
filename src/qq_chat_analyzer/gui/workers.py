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




def _invoke(operation: Callable[..., Any], report: Callable[[str], None] | None) -> Any:
    """Call ``operation``, passing a progress reporter only when one is wanted.

    Existing callers pass zero-argument operations, so the reporter is only
    supplied when a progress callback was registered.
    """
    if report is None:
        return operation()
    return operation(report)


class WorkerSignals(QObject):
    """Signals emitted by :class:`FacadeWorker`."""

    succeeded = Signal(object)
    failed = Signal(str, str)
    finished = Signal()
    progress = Signal(str)


class FacadeWorker(QRunnable):
    """Run one facade call off the UI thread."""

    def __init__(
        self,
        operation: Callable[..., Any],
        *,
        reports_progress: bool = False,
    ) -> None:
        super().__init__()
        self._operation = operation
        self._reports_progress = reports_progress
        self.signals = WorkerSignals()
        self.setAutoDelete(False)

    @Slot()
    def run(self) -> None:
        try:
            def _report_progress(message: str) -> None:
                _WORKER_LOGGER.info("[wechat worker] emit progress: %s", message)
                self.signals.progress.emit(message)

            result = _invoke(
                self._operation,
                _report_progress if self._reports_progress else None,
            )
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
    operation: Callable[..., Any],
    *,
    on_success: Callable[[Any], None],
    on_error: Callable[[str, str], None],
    on_finished: Callable[[], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    pool: QThreadPool | None = None,
) -> FacadeWorker:
    """Queue ``operation`` and wire its outcome to the given callbacks.

    When ``on_progress`` is given, ``operation`` is called with a reporter
    callable it can use to publish intermediate status. The reporter crosses
    back to the UI thread through a Qt signal, so callers never touch widgets
    from the worker thread.
    """
    worker = FacadeWorker(operation, reports_progress=on_progress is not None)
    worker.signals.succeeded.connect(on_success)
    worker.signals.failed.connect(on_error)
    if on_progress is not None:
        def _forward_progress(message: str) -> None:
            _WORKER_LOGGER.info("[wechat worker] forward progress: %s", message)
            on_progress(message)

        worker.signals.progress.connect(_forward_progress)
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)
    worker.signals.finished.connect(lambda: _PENDING.discard(worker))

    _PENDING.add(worker)
    (pool or QThreadPool.globalInstance()).start(worker)
    return worker


def run_inline(
    operation: Callable[..., Any],
    *,
    on_success: Callable[[Any], None],
    on_error: Callable[[str, str], None],
    on_finished: Callable[[], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Run ``operation`` on the calling thread.

    Useful for tests and for callers that need a deterministic, synchronous
    result. The failure translation is identical to :func:`submit`, so the
    surrounding page cannot tell the two apart.
    """
    try:
        result = _invoke(operation, on_progress)
    except FacadeError as error:
        on_error(error.code, error.public_message)
    except Exception:
        on_error("unexpected_error", GENERIC_ERROR_MESSAGE)
    else:
        on_success(result)
    finally:
        if on_finished is not None:
            on_finished()
