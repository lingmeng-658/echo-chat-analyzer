"""Behavior tests for the PySide6 GUI layer.

These tests never open a real window: Qt runs on the ``offscreen`` platform
and every facade call is served by a stub. The GUI is verified as a pure
consumer of the facade.
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 is required for the GUI layer")

from PySide6.QtCore import QDate, QThreadPool, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QSizePolicy  # noqa: E402


def _facade_module():
    return importlib.import_module("qq_chat_analyzer.application.facade")


def _presentation():
    return importlib.import_module("qq_chat_analyzer.presentation")


def _analysis_models():
    return importlib.import_module("qq_chat_analyzer.analysis.models")


@pytest.fixture(scope="session")
def qt_app():
    """One QApplication for the whole session; Qt forbids more than one."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def sources():
    module = _facade_module()
    return (
        module.SourceInfo(
            source=module.ChatSource.QQ,
            display_name="QQ",
            available=True,
        ),
        module.SourceInfo(
            source=module.ChatSource.WECHAT,
            display_name="\u5fae\u4fe1",
            available=False,
            description="\u5fae\u4fe1\u6570\u636e\u6e90\u5c1a\u672a\u914d\u7f6e\u3002",
        ),
        module.SourceInfo(
            source=module.ChatSource.LOCAL_FILE,
            display_name="\u672c\u5730\u6587\u4ef6",
            available=True,
        ),
    )


class _StaticConnectionService:
    """Return one fixed QQ connection status."""

    def __init__(self, status):
        self._status = status

    def check_status(self):
        return self._status


class StubFacade:
    """Stand in for ChatAnalyzerFacade with recorded calls."""

    def __init__(
        self,
        sources=(),
        sessions=(),
        outcome=None,
        error=None,
        connection_status=None,
        connection_status_after_connect=None,
        connection_error=None,
        connect_qq_error=None,
        setup_status=None,
        setup_error=None,
        data_root=None,
        data_roots=(),
        qq_setup_status=None,
        qq_runtime_status=None,
        qq_environment_config=None,
        message_range=None,
        history=(),
        snapshots=(),
        snapshot_storage_usage=0,
        snapshot_error=None,
        remove_snapshot_error=None,
        clear_history_error=None,
    ):
        self._sources = tuple(sources)
        self._sessions = list(sessions)
        self._outcome = outcome
        self._error = error
        self._connection_status = connection_status
        self._connection_status_after_connect = connection_status_after_connect
        self._connection_error = connection_error
        self._connect_qq_error = connect_qq_error
        self._setup_status = setup_status
        self._setup_error = setup_error
        self._data_root = data_root
        self._data_roots = list(data_roots)
        self._qq_setup_status = qq_setup_status
        self._qq_runtime_status = qq_runtime_status
        self._qq_environment_config = qq_environment_config
        self._message_range = message_range
        self._history = list(history)
        self._snapshots = list(snapshots)
        self._snapshot_storage_usage = snapshot_storage_usage
        self._snapshot_error = snapshot_error
        self._remove_snapshot_error = remove_snapshot_error
        self._clear_history_error = clear_history_error
        self.list_sessions_calls: list[object] = []
        self.get_connection_status_calls: list[object] = []
        self.get_wechat_setup_status_calls: list[object] = []
        self.setup_wechat_environment_calls: list[object] = []
        self.detect_wechat_data_root_calls: list[object] = []
        self.detect_wechat_data_roots_calls: list[object] = []
        self.acquire_wechat_db_key_calls: list[object] = []
        self.get_qq_setup_status_calls: list[object] = []
        self.get_qq_runtime_status_calls: list[object] = []
        self.get_qq_environment_config_calls: list[object] = []
        self.setup_qq_environment_calls: list[object] = []
        self.start_qq_runtime_calls: list[object] = []
        self.connect_qq_calls: list[object] = []
        self.start_qq_auth_flow_calls: list[object] = []
        self.get_qq_connection_snapshot_calls: list[object] = []
        self.shutdown_qq_runtime_calls: list[object] = []
        self.shutdown_calls: list[object] = []
        self.disconnect_qq_calls: list[object] = []
        self.disconnect_wechat_calls: list[object] = []
        self.get_session_message_range_calls: list[tuple] = []
        self.analyze_session_calls: list[tuple] = []
        self.analyze_file_calls: list[tuple] = []
        self.list_analysis_history_calls: list[object] = []
        self.clear_analysis_history_calls: list[object] = []
        self.get_analysis_history_calls: list[object] = []
        self.list_snapshots_calls: list[tuple] = []
        self.validate_snapshot_calls: list[object] = []
        self.remove_snapshot_calls: list[object] = []
        self.get_snapshot_storage_usage_calls: list[object] = []

    def list_analysis_history(self):
        self.list_analysis_history_calls.append(1)
        return tuple(self._history)

    def clear_analysis_history(self):
        self.clear_analysis_history_calls.append(1)
        if self._clear_history_error is not None:
            raise self._clear_history_error
        self._history = []

    def get_analysis_history(self, analysis_id):
        self.get_analysis_history_calls.append(analysis_id)
        return next(
            (
                record
                for record in self._history
                if getattr(record, "analysis_id", None) == analysis_id
            ),
            None,
        )

    def list_snapshots(self, source=None, session_id=None):
        self.list_snapshots_calls.append((source, session_id))
        if self._snapshot_error is not None:
            raise self._snapshot_error
        return tuple(self._snapshots)

    def validate_snapshot(self, snapshot_id):
        self.validate_snapshot_calls.append(snapshot_id)
        if self._snapshot_error is not None:
            raise self._snapshot_error
        return next(
            (
                snapshot
                for snapshot in self._snapshots
                if getattr(snapshot, "id", None) == snapshot_id
            ),
            None,
        )

    def remove_snapshot(self, snapshot_id):
        self.remove_snapshot_calls.append(snapshot_id)
        if self._remove_snapshot_error is not None:
            raise self._remove_snapshot_error
        if self._snapshot_error is not None:
            raise self._snapshot_error
        snapshot_module = importlib.import_module(
            "qq_chat_analyzer.application.chat_data_snapshot"
        )
        removed = next(
            (
                snapshot
                for snapshot in self._snapshots
                if getattr(snapshot, "id", None) == snapshot_id
            ),
            None,
        )
        self._snapshots = [
            dataclasses.replace(
                snapshot,
                payload_state=snapshot_module.SnapshotPayloadState.REMOVED,
            )
            if getattr(snapshot, "id", None) == snapshot_id
            else snapshot
            for snapshot in self._snapshots
        ]
        self._snapshot_storage_usage = 0
        return removed

    def get_snapshot_storage_usage(self):
        self.get_snapshot_storage_usage_calls.append(1)
        if self._snapshot_error is not None:
            raise self._snapshot_error
        return self._snapshot_storage_usage

    def list_sources(self):
        return self._sources

    def list_sessions(self, source):
        self.list_sessions_calls.append(source)
        if self._error is not None:
            raise self._error
        return self._sessions

    def get_connection_status(self, source):
        self.get_connection_status_calls.append(source)
        if self._connection_error is not None:
            raise self._connection_error
        if self._connection_status is None:
            return self._default_connection_status(source)
        return self._connection_status

    def get_qq_setup_status(self):
        self.get_qq_setup_status_calls.append(1)
        if self._qq_setup_status is not None:
            return self._qq_setup_status
        module = importlib.import_module(
            "qq_chat_analyzer.application.qq_setup_service"
        )
        return module.QQSetupStatus(
            state=module.QQSetupState.CONFIG_MISSING,
            configured=False,
            runtime_available=False,
            message="QQ \u5c1a\u672a\u8fde\u63a5\u3002",
            action_hint="\u8bf7\u70b9\u51fb\u300c\u8fde\u63a5QQ\u300d\u81ea\u52a8\u5b8c\u6210\u8fde\u63a5\u3002",
        )

    def get_qq_runtime_status(self):
        self.get_qq_runtime_status_calls.append(1)
        if self._qq_runtime_status is not None:
            return self._qq_runtime_status
        module = importlib.import_module("qq_chat_analyzer.application.runtime")
        return module.QQRuntimeStatus(
            state=module.QQRuntimeState.STOPPED,
            available=False,
            message="QQ \u672a\u8fde\u63a5\u3002",
            action_hint="\u8bf7\u70b9\u51fb\u300c\u8fde\u63a5QQ\u300d\u3002",
        )

    def get_qq_environment_config(self):
        self.get_qq_environment_config_calls.append(1)
        return self._qq_environment_config

    def setup_qq_environment(self, config):
        self.setup_qq_environment_calls.append(config)
        if self._setup_error is not None:
            raise self._setup_error
        return None

    def start_qq_runtime(self):
        self.start_qq_runtime_calls.append(1)
        if self._qq_runtime_status is not None:
            return self._qq_runtime_status
        module = importlib.import_module("qq_chat_analyzer.application.runtime")
        return module.QQRuntimeStatus(
            state=module.QQRuntimeState.RUNNING,
            available=True,
            message="QQ \u5df2\u8fde\u63a5\u3002",
            action_hint="",
        )

    def connect_qq(self):
        self.connect_qq_calls.append(1)
        if self._connect_qq_error is not None:
            raise self._connect_qq_error
        if self._connection_status_after_connect is not None:
            self._connection_status = self._connection_status_after_connect
        return self._qq_snapshot()

    def start_qq_auth_flow(self, progress=None):
        self.start_qq_auth_flow_calls.append(1)
        if progress is not None:
            progress("正在加载 NapCat...")
        if self._connect_qq_error is not None:
            raise self._connect_qq_error
        if self._connection_status_after_connect is not None:
            self._connection_status = self._connection_status_after_connect
        return self._qq_snapshot()

    def is_qq_qrcode_ready(self):
        return True

    def get_qq_connection_snapshot(self):
        self.get_qq_connection_snapshot_calls.append(1)
        if self._connection_error is not None:
            raise self._connection_error
        return self._qq_snapshot()

    def shutdown_qq_runtime(self):
        self.shutdown_qq_runtime_calls.append(1)

    def shutdown(self):
        self.shutdown_calls.append(1)

    def disconnect_qq(self):
        self.disconnect_qq_calls.append(1)
        if self._connection_error is not None:
            raise self._connection_error
        module = _facade_module()
        self._connection_status = module.QQConnectionStatus(
            available=False,
            qce_running=False,
            authenticated=False,
            version="",
            message="QQ 尚未连接。",
            action_hint="",
        )
        return self._qq_snapshot()

    def disconnect_wechat(self):
        self.disconnect_wechat_calls.append(1)
        if self._connection_error is not None:
            raise self._connection_error
        module = _facade_module()
        self._connection_status = module.WeChatConnectionStatus(
            available=False,
            data_found=True,
            db_key_available=False,
            runtime_available=True,
            message="等待微信登录",
            action_hint="",
        )
        return self._connection_status

    def _qq_snapshot(self):
        """Map the stubbed QQ status onto the connection lifecycle model."""
        module = _facade_module()
        status = self._connection_status
        if status is None:
            status = self._default_connection_status(module.ChatSource.QQ)
        manager = importlib.import_module(
            "qq_chat_analyzer.application.connection.qq_connection_manager"
        )
        return manager.QQConnectionManager(
            connection_service=_StaticConnectionService(status),
        ).get_snapshot()

    def get_session_message_range(self, source, session_id):
        self.get_session_message_range_calls.append((source, session_id))
        return self._message_range

    def get_wechat_setup_status(self):
        self.get_wechat_setup_status_calls.append(1)
        if self._setup_error is not None:
            raise self._setup_error
        if self._setup_status is not None:
            return self._setup_status
        module = importlib.import_module(
            "qq_chat_analyzer.application.wechat_setup_service"
        )
        return module.WeChatSetupStatus(
            state=module.WeChatSetupState.CONFIG_MISSING,
            configured=False,
            message="\u5fae\u4fe1\u73af\u5883\u672a\u51c6\u5907",
            action_hint="\u8bf7\u5148\u5b8c\u6210\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e",
        )

    def detect_wechat_data_root(self):
        self.detect_wechat_data_root_calls.append(1)
        return self._data_root

    def detect_wechat_data_roots(self):
        self.detect_wechat_data_roots_calls.append(1)
        if self._data_roots:
            return [Path(value) for value in self._data_roots]
        if self._data_root is not None:
            return [Path(self._data_root)]
        return []

    def acquire_wechat_db_key(self, progress=None):
        self.acquire_wechat_db_key_calls.append(progress)
        if self._connection_status_after_connect is not None:
            self._connection_status = self._connection_status_after_connect
        return "fictional-key-64"

    def setup_wechat_environment(self, config):
        self.setup_wechat_environment_calls.append(config)
        if self._setup_error is not None:
            raise self._setup_error
        return self._connection_status or self._default_connection_status(
            _facade_module().ChatSource.WECHAT
        )

    def _default_connection_status(self, source):
        module = _facade_module()
        if source == module.ChatSource.WECHAT:
            return module.WeChatConnectionStatus(
                available=True,
                data_found=True,
                db_key_available=True,
                runtime_available=True,
                message="\u5fae\u4fe1\u53ef\u7528",
                action_hint="",
            )
        return module.QQConnectionStatus(
            available=True,
            qce_running=True,
            authenticated=True,
            version="4.1.0",
            message="\u5df2\u8fde\u63a5",
            action_hint="",
        )

    def analyze_session(self, source, session_id, config=None, progress=None):
        self.analyze_session_calls.append((source, session_id, config))
        if progress is not None:
            progress("正在分析聊天内容...")
        if self._error is not None:
            raise self._error
        return self._outcome

    def analyze_file(self, path, config=None, progress=None):
        self.analyze_file_calls.append((path, config))
        if progress is not None:
            progress("正在分析聊天内容...")
        if self._error is not None:
            raise self._error
        return self._outcome


def _session(
    source,
    session_id: str,
    display_name: str,
    count=None,
    last_message_time=None,
):
    module = _facade_module()
    return module.SessionInfo(
        source=source,
        session_id=session_id,
        display_name=display_name,
        message_count=count,
        last_message_time=last_message_time,
    )


def _sort_index(page, value: str) -> int:
    for index in range(page._session_sort.count()):
        if page._session_sort.itemData(index) == value:
            return index
    raise AssertionError(f"missing sort mode {value}")


def _dashboard_view(*, has_data: bool = True):
    presentation = _presentation()
    if not has_data:
        return presentation.DashboardView(
            title="\u865a\u6784\u62a5\u544a",
            has_data=False,
            empty_description="\u6ca1\u6709\u6570\u636e\u3002",
        )

    return presentation.DashboardView(
        title="\u865a\u6784\u62a5\u544a",
        has_data=True,
        summary_metrics=(
            presentation.MetricCard(
                key="total_messages",
                title="\u6d88\u606f\u6570\u91cf",
                value="42",
                description="\u603b\u6570",
            ),
        ),
        charts=(
            presentation.ChartData(
                key="top_words",
                kind=presentation.ChartKind.RANKING,
                title="\u9ad8\u9891\u8bcd",
                series=(
                    presentation.ChartSeries(
                        name="\u8bcd\u9891",
                        points=(
                            presentation.ChartPoint(label="deck", value=5.0),
                            presentation.ChartPoint(label="trade", value=2.0),
                        ),
                    ),
                ),
            ),
        ),
        user_cards=(
            presentation.UserCard(
                rank=1,
                sender="Fictional-Alice",
                message_count=30,
                percentage=75.0,
                average_length=4.0,
                percentage_display="75.0%",
                average_length_display="4.0 \u5b57",
                active_period="\u5468\u4e00 09:00-09:59",
                top_words=("deck",),
            ),
        ),
        conversation_cards=(
            presentation.ConversationCard(
                conversation_id="fictional-room-1",
                message_count=42,
                participant_count=2,
                time_span="2 \u5c0f\u65f6 0 \u5206\u949f",
            ),
        ),
    )


class _StubOutcome:
    def __init__(
        self,
        view,
        *,
        history_saved=None,
        data_acquired_at=None,
        report_path=None,
    ):
        self.view = view
        self.history_saved = history_saved
        self.data_acquired_at = data_acquired_at
        self.report_path = report_path


def _analysis_page(
    qt_app,
    facade,
    executor=None,
    qq_qrcode_path=None,
    wechat_guide_image_path=None,
):
    module = importlib.import_module("qq_chat_analyzer.gui.analysis_page")
    return module.AnalysisPage(
        facade,
        executor=executor or _inline_executor(),
        qq_qrcode_path=qq_qrcode_path,
        wechat_guide_image_path=wechat_guide_image_path,
    )


def _dashboard_page(qt_app):
    module = importlib.import_module("qq_chat_analyzer.gui.dashboard_page")
    return module.DashboardPage()


def _main_window(qt_app, facade, executor=None):
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    return module.MainWindow(facade, executor=executor or _inline_executor())


def _main_window_no_executor(qt_app, facade):
    """Create MainWindow without executor, as in real GUI app.py."""
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    return module.MainWindow(facade, executor=None)


def _inline_executor():
    """Run facade calls on the calling thread.

    The GUI defaults to a real thread pool. Tests inject this instead so no
    test depends on thread scheduling or on a Qt event loop turn.
    """
    module = importlib.import_module("qq_chat_analyzer.gui.workers")
    return module.run_inline


def test_worker_forwards_analysis_progress_to_the_ui_callback() -> None:
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    received: list[str] = []

    workers.run_inline(
        lambda report: report("正在分析聊天内容..."),
        on_success=lambda _result: None,
        on_error=lambda _code, _message: None,
        on_progress=received.append,
    )

    assert received == ["正在分析聊天内容..."]


class _DeferredExecutor:
    """Capture a facade call and let the test finish it manually."""

    def __init__(self):
        self.operation = None
        self.on_success = None
        self.on_error = None
        self.on_finished = None
        self.on_progress = None
        self.submission_count = 0
        self.cancelled = False

    def __call__(
        self,
        operation,
        *,
        on_success,
        on_error,
        on_finished=None,
        on_progress=None,
    ):
        self.submission_count += 1
        self.operation = operation
        self.on_success = on_success
        self.on_error = on_error
        self.on_finished = on_finished
        self.on_progress = on_progress
        return self

    def cancel(self):
        self.cancelled = True

    def progress(self, message):
        if self.on_progress is not None:
            self.on_progress(message)

    def succeed(self, result):
        if self.on_success is not None:
            self.on_success(result)
        if self.on_finished is not None:
            self.on_finished()

    def fail(self, code, message):
        if self.on_error is not None:
            self.on_error(code, message)
        if self.on_finished is not None:
            self.on_finished()


def _drain(page):
    """Deliver zero-timer GUI work used by the synchronous test executor."""
    QApplication.processEvents()


def _settle_workers(timeout_ms: int = 5000) -> None:
    """Wait for real thread-pool work and deliver queued GUI callbacks."""
    deadline = time.monotonic() + timeout_ms / 1000
    pool = QThreadPool.globalInstance()
    while time.monotonic() < deadline:
        pool.waitForDone(100)
        QTest.qWait(20)
        QApplication.processEvents()


# ------------------------------------------------------------ initialization


def test_main_window_builds_both_pages(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    assert window.stack.count() == 7
    assert window.windowTitle() != ""
    assert window.stack.currentIndex() == 0


def test_main_window_has_no_status_bar(qt_app, sources) -> None:
    from PySide6.QtWidgets import QStatusBar

    window = _main_window(qt_app, StubFacade(sources=sources))

    assert window.findChild(QStatusBar) is None


def test_page_has_no_bottom_hint_label(qt_app, sources) -> None:
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    assert not hasattr(page, "_hint_label")


def test_status_area_is_moved_to_header_row(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))
    status = window.analysis_page._status_label
    layout = window.centralWidget().layout()
    header = layout.itemAt(0).layout()

    assert window._title_label.text() == "余音 Echo"
    assert header is not None
    assert header.itemAt(header.count() - 1).widget() is status
    page_widgets = [
        window.analysis_page.layout().itemAt(i).widget()
        for i in range(window.analysis_page.layout().count())
    ]
    assert status not in page_widgets
    assert not hasattr(window, "_top_status_label")


def test_qq_and_wechat_share_one_moved_status_area(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))
    status = window.analysis_page._status_label

    window.show_status("等待 QQ 登录")
    assert status.text() == "等待 QQ 登录"
    window.show_status("等待微信登录")
    assert status.text() == "等待微信登录"
    assert window.analysis_page._status_label is status


def test_top_status_follows_status_changed_without_bottom_duplicate(
    qt_app,
    sources,
) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_status("等待 QQ 登录")

    assert window.analysis_page._status_label.text() == "等待 QQ 登录"


def test_main_window_uses_echo_brand_icon(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    assert window.windowIcon().isNull() is False


def test_main_window_close_cleans_up_qq_runtime(qt_app, sources) -> None:
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)

    window.close()

    deadline = time.monotonic() + 1.0
    while not facade.shutdown_qq_runtime_calls and time.monotonic() < deadline:
        time.sleep(0.005)

    assert facade.shutdown_qq_runtime_calls == [1]


def test_main_window_close_does_not_wait_for_slow_process_cleanup(
    qt_app,
    sources,
) -> None:
    cleanup_finished = threading.Event()

    class _SlowShutdownFacade(StubFacade):
        def shutdown_qq_runtime(self):
            time.sleep(0.2)
            cleanup_finished.set()

    window = _main_window(qt_app, _SlowShutdownFacade(sources=sources))

    started = time.monotonic()
    window.close()
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    assert cleanup_finished.wait(timeout=1.0)

def test_main_window_close_calls_facade_shutdown(qt_app, sources) -> None:
    """closeEvent calls facade.shutdown() in addition to QQ shutdown."""
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)

    window.close()

    deadline = time.monotonic() + 1.0
    while not facade.shutdown_calls and time.monotonic() < deadline:
        time.sleep(0.005)

    assert facade.shutdown_calls == [1]


def test_main_window_close_still_calls_qq_shutdown(qt_app, sources) -> None:
    """Original QQ runtime shutdown is preserved alongside facade.shutdown()."""
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)

    window.close()

    deadline = time.monotonic() + 1.0
    while not facade.shutdown_qq_runtime_calls and time.monotonic() < deadline:
        time.sleep(0.005)

    assert facade.shutdown_qq_runtime_calls == [1]
    assert facade.shutdown_calls == [1]


def test_main_window_close_survives_facade_shutdown_exception(qt_app, sources) -> None:
    """An exception in facade.shutdown() must not prevent window close."""
    class _ShutdownRaisesFacade(StubFacade):
        def shutdown(self):
            self.shutdown_calls.append(1)
            raise RuntimeError("simulated shutdown failure")

    facade = _ShutdownRaisesFacade(sources=sources)
    window = _main_window(qt_app, facade)

    # close() should not raise
    window.close()

    deadline = time.monotonic() + 1.0
    while not facade.shutdown_calls and time.monotonic() < deadline:
        time.sleep(0.005)

    assert facade.shutdown_calls == [1]


def test_main_window_has_minimum_size(qt_app, sources) -> None:
    """MainWindow has a reasonable minimum size set."""
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)

    minimum = window.minimumSize()
    assert minimum.width() > 0
    assert minimum.height() > 0
    assert minimum.width() >= 800
    assert minimum.height() >= 600


def test_main_window_size_stable_across_page_switches(qt_app, sources) -> None:
    """Page switching must not change the MainWindow actual size."""
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.show()
    window.resize(960, 720)

    initial = window.size()

    window.show_processing_page()
    _drain(window)
    after_processing = window.size()
    assert after_processing == initial

    window.show_analysis_page()
    _drain(window)
    after_analysis = window.size()
    assert after_analysis == initial

    # Simulate a successful outcome to reach DashboardPage
    window.show_outcome(_StubOutcome(_dashboard_view()))
    _drain(window)
    after_dashboard = window.size()
    assert after_dashboard == initial



def _connection_status(
    *,
    available: bool,
    qce_running: bool,
    authenticated: bool,
    version: str | None = None,
    message: str,
    action_hint: str,
):
    module = _facade_module()
    return module.QQConnectionStatus(
        available=available,
        qce_running=qce_running,
        authenticated=authenticated,
        version=version,
        message=message,
        action_hint=action_hint,
    )


def _wechat_connection_status(
    *,
    available: bool,
    data_found: bool,
    db_key_available: bool,
    runtime_available: bool,
    message: str,
    action_hint: str,
):
    module = _facade_module()
    return module.WeChatConnectionStatus(
        available=available,
        data_found=data_found,
        db_key_available=db_key_available,
        runtime_available=runtime_available,
        message=message,
        action_hint=action_hint,
    )


def _qq_setup_status(
    *,
    configured: bool,
    runtime_available: bool = False,
    message: str = "",
    action_hint: str = "",
):
    module = importlib.import_module(
        "qq_chat_analyzer.application.qq_setup_service"
    )
    return module.QQSetupStatus(
        state=(
            module.QQSetupState.CONFIG_READY
            if configured
            else module.QQSetupState.CONFIG_MISSING
        ),
        configured=configured,
        runtime_available=runtime_available,
        message=message,
        action_hint=action_hint,
    )


def _qq_runtime_status(
    *,
    state: str,
    message: str = "",
    action_hint: str = "",
):
    module = importlib.import_module("qq_chat_analyzer.application.runtime")
    return module.QQRuntimeStatus(
        state=module.QQRuntimeState(state),
        available=state == "running",
        message=message,
        action_hint=action_hint,
    )


def _wechat_available_sources():
    module = _facade_module()
    return (
        module.SourceInfo(
            source=module.ChatSource.QQ,
            display_name="QQ",
            available=True,
        ),
        module.SourceInfo(
            source=module.ChatSource.WECHAT,
            display_name="\u5fae\u4fe1",
            available=True,
        ),
        module.SourceInfo(
            source=module.ChatSource.LOCAL_FILE,
            display_name="\u672c\u5730\u6587\u4ef6",
            available=True,
        ),
    )


def test_analysis_page_gets_qq_status_through_the_facade(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=True,
        qce_running=True,
        authenticated=True,
        version="4.1.0",
        message="QQ \u5df2\u8fde\u63a5\u3002",
        action_hint="\u53ef\u4ee5\u5f00\u59cb\u5bfc\u51fa\u3002",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )

    page = _analysis_page(qt_app, facade)
    _drain(page)

    assert facade.get_qq_connection_snapshot_calls == []

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert facade.get_qq_connection_snapshot_calls == [1]
    assert page._status_label.isVisibleTo(page) is True
    assert "QQ \u5df2\u8fde\u63a5" in page._status_label.text()
    assert page._status_label.toolTip() == "\u53ef\u4ee5\u5f00\u59cb\u5bfc\u51fa\u3002"


def test_disconnected_qq_status_is_shown_with_an_action_hint(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=False,
        qce_running=False,
        authenticated=False,
        message="QQ \u670d\u52a1\u672a\u8fd0\u884c\u3002",
        action_hint="\u8bf7\u5148\u8fde\u63a5 QQ\u3002",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )

    page = _analysis_page(qt_app, facade)
    _drain(page)

    assert facade.get_qq_connection_snapshot_calls == []

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert facade.get_qq_connection_snapshot_calls == [1]
    assert page._status_label.isVisibleTo(page) is True
    assert "\U0001F534" in page._status_label.text()
    assert "QQ \u670d\u52a1\u672a\u8fd0\u884c\u3002" in (
        page._status_label.text()
    )
    assert page._status_label.toolTip() == "\u8bf7\u5148\u8fde\u63a5 QQ\u3002"


def test_selecting_qq_refreshes_the_connection_status(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=True,
        qce_running=True,
        authenticated=True,
        message="\u5df2\u8fde\u63a5\u3002",
        action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        sessions=[
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A", 12)
        ],
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert facade.get_qq_connection_snapshot_calls == [1]
    assert page._session_list.count() == 1


def test_selecting_wechat_checks_status_then_loads_sessions(qt_app) -> None:
    module = _facade_module()
    status = _wechat_connection_status(
        available=True,
        data_found=True,
        db_key_available=True,
        runtime_available=True,
        message="\u5fae\u4fe1\u6570\u636e\u5df2\u5c31\u7eea",
        action_hint="\u53ef\u4ee5\u5f00\u59cb\u9009\u62e9\u4f1a\u8bdd\u3002",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[
            _session(
                module.ChatSource.WECHAT,
                "wxid_fictional",
                "Fictional Alice",
            )
        ],
        connection_status=status,
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert facade.get_connection_status_calls[-1] == module.ChatSource.WECHAT
    assert facade.list_sessions_calls == [module.ChatSource.WECHAT]
    assert page._session_list.count() == 1
    assert page._status_label.text() == (
        "\U0001F7E2 \u5fae\u4fe1\u5df2\u8fde\u63a5\uff0c\u53ef\u4ee5\u5f00\u59cb\u5206\u6790"
    )
    assert page._wechat_connect_button.isVisibleTo(page) is False
    assert "重新连接" not in page._wechat_connect_button.text()


def test_selecting_wechat_without_ready_status_does_not_load_sessions(
    qt_app,
) -> None:
    module = _facade_module()
    status = _wechat_connection_status(
        available=False,
        data_found=False,
        db_key_available=False,
        runtime_available=False,
        message="\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e",
        action_hint="\u8bf7\u767b\u5f55\u5fae\u4fe1\u6216\u914d\u7f6e\u6570\u636e\u76ee\u5f55\u3002",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[
            _session(
                module.ChatSource.WECHAT,
                "wxid_fictional",
                "Fictional Alice",
            )
        ],
        connection_status=status,
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert facade.list_sessions_calls == []
    assert page._session_list.count() == 1
    assert "暂无会话" in page._session_list.item(0).text()
    assert page._status_label.text() == (
        "\U0001F534 \u5fae\u4fe1\u8fde\u63a5\u73af\u5883\u4e0d\u5b58\u5728"
    )
    assert page._status_label.toolTip() == (
        "\u8bf7\u767b\u5f55\u5fae\u4fe1\u6216\u914d\u7f6e\u6570\u636e\u76ee\u5f55\u3002"
    )
    assert page._analyze_button.isEnabled() is False


def test_wechat_disconnected_button_offers_connect(qt_app) -> None:
    module = _facade_module()
    status = _wechat_connection_status(
        available=False,
        data_found=False,
        db_key_available=False,
        runtime_available=False,
        message="\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e",
        action_hint="\u8bf7\u767b\u5f55\u5fae\u4fe1\u6216\u914d\u7f6e\u6570\u636e\u76ee\u5f55\u3002",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=status,
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert page._wechat_connect_button.text() == "\u8fde\u63a5\u5fae\u4fe1"


def test_wechat_status_bar_uses_unified_disconnected_text(qt_app) -> None:
    module = _facade_module()
    status = _wechat_connection_status(
        available=False,
        data_found=False,
        db_key_available=False,
        runtime_available=False,
        message="\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e",
        action_hint="\u8bf7\u767b\u5f55\u5fae\u4fe1\u6216\u914d\u7f6e\u6570\u636e\u76ee\u5f55\u3002",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=status,
    )
    page = _analysis_page(qt_app, facade)
    received: list[str] = []
    page.status_changed.connect(received.append)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert received == ["\u5fae\u4fe1\u8fde\u63a5\u73af\u5883\u4e0d\u5b58\u5728"]


def test_wechat_status_bar_stays_connected_after_session_load(qt_app) -> None:
    module = _facade_module()
    status = _wechat_connection_status(
        available=True,
        data_found=True,
        db_key_available=True,
        runtime_available=True,
        message="\u5fae\u4fe1\u6570\u636e\u6e90\u53ef\u7528",
        action_hint="\u53ef\u4ee5\u5f00\u59cb\u9009\u62e9\u4f1a\u8bdd\u3002",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[
            _session(
                module.ChatSource.WECHAT,
                "wxid_fictional",
                "Fictional Alice",
            )
        ],
        connection_status=status,
    )
    page = _analysis_page(qt_app, facade)
    received: list[str] = []
    page.status_changed.connect(received.append)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert received == ["\u5fae\u4fe1\u5df2\u8fde\u63a5\uff0c\u53ef\u4ee5\u5f00\u59cb\u5206\u6790"]
    assert not any("\u52a0\u8f7d\u4f1a\u8bdd" in text for text in received)


def test_wechat_connecting_uses_unified_status(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(sources=_wechat_available_sources())

    def deferred(operation, **kwargs) -> None:
        return None

    page = _analysis_page(qt_app, facade, deferred)
    received: list[str] = []
    page.status_changed.connect(received.append)

    page._start_wechat_connect(
        module.WeChatEnvironmentConfig(data_root="D:/fake_root")
    )

    assert page._status_label.text() == "\u6b63\u5728\u8fde\u63a5\u5fae\u4fe1..."
    assert received == ["\u6b63\u5728\u8fde\u63a5\u5fae\u4fe1..."]


def test_wechat_connect_progress_keeps_unified_status(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(sources=_wechat_available_sources())

    def deferred(operation, **kwargs) -> None:
        return None

    page = _analysis_page(qt_app, facade, deferred)
    received: list[str] = []
    page.status_changed.connect(received.append)
    page._start_wechat_connect(
        module.WeChatEnvironmentConfig(data_root="D:/fake_root")
    )

    page._handle_wechat_connect_progress("\u6b63\u5728\u7b49\u5f85\u5fae\u4fe1\u767b\u5f55...")

    assert page._status_label.text() == "\u7b49\u5f85\u5fae\u4fe1\u767b\u5f55"
    assert received == ["\u6b63\u5728\u8fde\u63a5\u5fae\u4fe1..."]


def test_wechat_connect_progress_shows_database_read_stage(qt_app) -> None:
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)

    page._handle_wechat_connect_progress("\u6b63\u5728\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u5e93...")

    assert page._status_label.text() == "\u6b63\u5728\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u5e93..."


def test_wechat_connect_failure_surfaces_a_user_message(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)
    received: list[str] = []
    page.status_changed.connect(received.append)

    page._handle_wechat_connect_error(
        "key_timeout",
        "\u767b\u5f55\u8d85\u65f6\uff0c\u8bf7\u91cd\u65b0\u5c1d\u8bd5\u3002",
    )

    assert page._status_label.text() == (
        "\U0001F534 Key \u83b7\u53d6\u5931\u8d25"
    )
    assert received == ["\u767b\u5f55\u8d85\u65f6\uff0c\u8bf7\u91cd\u65b0\u5c1d\u8bd5\u3002"]


def test_wechat_key_failure_does_not_claim_echo_needs_reinstall(qt_app) -> None:
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)

    page._handle_wechat_connect_error(
        "wechat_key_timeout",
        "Key \u83b7\u53d6\u8d85\u65f6\uff0c\u8bf7\u5728\u5fae\u4fe1\u767b\u5f55\u65f6\u91cd\u8bd5\u3002",
    )

    visible = page._status_label.text()
    assert "Key \u83b7\u53d6\u5931\u8d25" in visible
    assert "\u91cd\u65b0\u5b89\u88c5" not in visible


def test_wechat_hook_failure_keeps_the_classified_reason(qt_app) -> None:
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)

    page._handle_wechat_connect_error(
        "wechat_hook_failed",
        "\u5fae\u4fe1 Hook \u5931\u8d25\uff0c\u5f53\u524d\u5fae\u4fe1\u8fdb\u7a0b\u53ef\u80fd\u4e0d\u517c\u5bb9\u3002",
    )

    assert "Hook \u5931\u8d25" in (page._status_label.toolTip() or "")
    assert "\u83b7\u53d6\u6743\u9650\u65f6\u5931\u8d25" in page._status_label.text()


def test_selecting_qq_without_ready_status_does_not_load_sessions(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=False,
        qce_running=False,
        authenticated=False,
        message="QQ \u6570\u636e\u6e90\u4e0d\u53ef\u7528",
        action_hint="\u8bf7\u5148\u8fde\u63a5 QQ\u3002",
    )
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert facade.list_sessions_calls == []
    assert page._session_list.count() == 1
    assert "暂无会话" in page._session_list.item(0).text()


def test_clicking_qq_source_button_checks_status_without_opening_dialog(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=False,
        qce_running=False,
        authenticated=False,
        message="QQ \u6570\u636e\u6e90\u4e0d\u53ef\u7528",
        action_hint="\u8bf7\u70b9\u51fb\u300c\u8fde\u63a5QQ\u300d\u81ea\u52a8\u5b8c\u6210\u8fde\u63a5\u3002",
    )
    facade = StubFacade(sources=sources, connection_status=status)
    page = _analysis_page(qt_app, facade)
    _drain(page)

    assert facade.get_qq_connection_snapshot_calls == []

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert facade.get_qq_connection_snapshot_calls == [1]
    assert not hasattr(page, "_qq_setup_dialog")
    assert page._qq_connect_button.isVisibleTo(page) is True


def test_qq_not_ready_shows_connect_button_instead_of_auto_dialog(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=False,
        qce_running=False,
        authenticated=False,
        message="QQ \u6570\u636e\u6e90\u4e0d\u53ef\u7528",
        action_hint="\u8bf7\u70b9\u51fb\u300c\u8fde\u63a5QQ\u300d\u81ea\u52a8\u5b8c\u6210\u8fde\u63a5\u3002",
    )
    facade = StubFacade(sources=sources, connection_status=status)
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert not hasattr(page, "_qq_setup_dialog")
    assert page._qq_connect_button.isVisibleTo(page) is True
    assert "\u8fde\u63a5QQ" in page._qq_connect_button.text()
    assert page._qq_connect_button.isEnabled() is True
    assert facade.list_sessions_calls == []


def test_clicking_qq_connect_calls_the_facade(qt_app, sources) -> None:
    module = _facade_module()
    status = _connection_status(
        available=True,
        qce_running=True,
        authenticated=True,
        message="QQ \u5df2\u8fde\u63a5\u3002",
        action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        sessions=[
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A")
        ],
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)
    page._qq_connect_button.click()
    _drain(page)
    QTest.qWait(600)

    assert facade.start_qq_auth_flow_calls == [1]
    assert page._session_list.count() == 1


def test_qq_connect_hides_backend_terms_behind_user_stage(qt_app, sources) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    facade = StubFacade(sources=sources)
    page = _analysis_page(qt_app, facade, executor=executor)
    page.select_source(module.ChatSource.QQ)
    _drain(page)

    page._qq_connect_button.click()
    executor.progress("正在加载 NapCat...")

    assert "正在启动QQ连接环境" in page._status_label.text()
    assert "NapCat" not in page._status_label.text()
    assert "权限确认窗口" in page._qq_login_guide_label.text()


def test_qq_connect_progress_does_not_duplicate_footer_status(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    page = _analysis_page(qt_app, StubFacade(sources=sources), executor=executor)
    page.select_source(module.ChatSource.QQ)
    _drain(page)
    emitted = []
    page.status_changed.connect(emitted.append)

    page._qq_connect_button.click()
    executor.progress("正在加载 NapCat...")

    assert "正在启动QQ连接环境" in page._status_label.text()
    assert "正在启动QQ连接环境" in emitted
    assert not hasattr(page, "_hint_label")


def test_qq_connect_progress_updates_top_status(qt_app, sources) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    window = _main_window(
        qt_app,
        StubFacade(sources=sources),
        executor=executor,
    )
    page = window.analysis_page
    page.select_source(module.ChatSource.QQ)
    _drain(page)

    page._qq_connect_button.click()
    executor.progress("正在加载 NapCat...")

    assert "正在启动QQ连接环境" in page._status_label.text()


@pytest.mark.parametrize(
    ("code", "title"),
    [
        ("qq_runtime_missing", "QQ连接环境启动失败"),
        ("qq_auth_failed", "QQ登录失败"),
        ("qce_start_failed", "QQ连接服务启动失败"),
    ],
)
def test_qq_connection_errors_keep_the_real_stage(qt_app, sources, code, title) -> None:
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    page._handle_qq_connect_error(code, "请重试")

    assert title in page._status_label.text()


@pytest.mark.parametrize(
    ("code", "title"),
    [
        ("wechat_not_running", "微信未启动"),
        ("wechat_waiting_login", "等待微信登录"),
        ("wechat_key_timeout", "Key 获取失败"),
    ],
)
def test_wechat_connection_errors_keep_the_real_stage(qt_app, code, title) -> None:
    page = _analysis_page(qt_app, StubFacade(sources=_wechat_available_sources()))

    page._handle_wechat_connect_error(code, "请重试")

    assert title in page._status_label.text()


def test_ready_qq_through_the_real_worker_has_no_reconnect_action(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=True,
        qce_running=True,
        authenticated=True,
        message="QQ \u5df2\u8fde\u63a5\u3002",
        action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        sessions=[
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A")
        ],
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    page = _analysis_page(qt_app, facade, executor=workers.submit)
    page.show()

    page._source_buttons[module.ChatSource.QQ].click()
    _settle_workers()

    assert facade.start_qq_auth_flow_calls == []
    assert page._session_list.count() == 1
    assert "\u5df2\u8fde\u63a5" in page._status_label.text()

    assert page._session_list.count() == 1
    assert "\u5df2\u8fde\u63a5" in page._status_label.text()
    assert page._qq_connect_button.isVisibleTo(page) is False
    assert facade.start_qq_auth_flow_calls == []


def test_qq_connect_accepts_a_string_source_value(qt_app, sources) -> None:
    module = _facade_module()
    facade = StubFacade(sources=sources)
    page = _analysis_page(qt_app, facade)

    page.select_source(module.ChatSource.QQ.value)
    _drain(page)
    page._qq_connect_button.click()
    _drain(page)

    assert facade.start_qq_auth_flow_calls == [1]


def test_qq_configured_but_not_connected_shows_connect_button(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=False,
        qce_running=False,
        authenticated=False,
        message="QQ \u672a\u8fde\u63a5\u3002",
        action_hint="\u8bf7\u70b9\u51fb\u300c\u8fde\u63a5QQ\u300d\u3002",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="stopped"),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._qq_connect_button.isVisibleTo(page) is True
    assert page._qq_connect_button.isEnabled() is True
    assert "\u8fde\u63a5QQ" in page._qq_connect_button.text()
    assert facade.list_sessions_calls == []


def test_qq_setup_dialog_prefills_effective_config(qt_app) -> None:
    module = _facade_module()
    dialog_module = importlib.import_module(
        "qq_chat_analyzer.gui.qq_setup_dialog"
    )
    config = module.QQEnvironmentConfig(
        runtime_directory=Path("D:/fake_runtime"),
        qce_path=Path("D:/fake_qce_server.exe"),
        base_url="http://127.0.0.1:40653",
    )

    dialog = dialog_module.QQSetupDialog(config=config)

    assert dialog._runtime_dir_edit.text() == str(Path("D:/fake_runtime"))
    assert dialog._qce_path_edit.text() == str(Path("D:/fake_qce_server.exe"))
    assert dialog._base_url_edit.text() == "http://127.0.0.1:40653"


def test_qq_ready_hides_connect_action_and_loads_sessions(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    status = _connection_status(
        available=True,
        qce_running=True,
        authenticated=True,
        message="QQ \u5df2\u8fde\u63a5\u3002",
        action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        sessions=[
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A")
        ],
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._qq_connect_button.isVisibleTo(page) is False
    assert "重新连接" not in page._qq_connect_button.text()
    assert facade.list_sessions_calls == [module.ChatSource.QQ]
    assert page._session_list.count() == 1


def test_qq_connect_failure_shows_user_safe_message(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    error = module.FacadeError(
        code="qq_connect_failed",
        public_message=(
            "\u65e0\u6cd5\u8fde\u63a5 QQ \u6570\u636e\u6e90\uff0c"
            "\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
        ),
        source=module.ChatSource.QQ,
    )
    facade = StubFacade(
        sources=sources,
        connect_qq_error=error,
        connection_status=_connection_status(
            available=False,
            qce_running=False,
            authenticated=False,
            message="QQ \u672a\u8fde\u63a5\u3002",
            action_hint="",
        ),
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="stopped"),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)
    page._qq_connect_button.click()
    _drain(page)
    QTest.qWait(600)

    assert facade.start_qq_auth_flow_calls == [1]
    assert "QQ \u8fde\u63a5\u5931\u8d25" in page._status_label.text()
    assert (
        "\u65e0\u6cd5\u8fde\u63a5 QQ \u6570\u636e\u6e90"
        in (page._status_label.toolTip() or "")
    )
    assert "Traceback" not in (page._status_label.toolTip() or "")
    assert facade.list_sessions_calls == []


def test_qq_connect_unavailable_status_is_not_silent(qt_app, sources) -> None:
    module = _facade_module()
    status = _connection_status(
        available=False,
        qce_running=False,
        authenticated=False,
        message="\u65e0\u6cd5\u8fde\u63a5 QQ\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002",
        action_hint=(
            "QQ \u6570\u636e\u6e90\u6682\u4e0d\u53ef\u7528\uff0c"
            "\u8bf7\u786e\u8ba4\u5e94\u7528\u5b89\u88c5\u5b8c\u6574\u540e\u91cd\u8bd5\u3002"
        ),
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=False,
            runtime_available=False,
        ),
        qq_runtime_status=_qq_runtime_status(state="stopped"),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)
    page._qq_connect_button.click()
    _drain(page)
    QTest.qWait(600)

    assert facade.start_qq_auth_flow_calls == [1]
    assert "\u65e0\u6cd5\u8fde\u63a5 QQ" in page._status_label.text()
    assert "QQ \u6570\u636e\u6e90\u6682\u4e0d\u53ef\u7528" in (
        page._status_label.toolTip() or ""
    )


def test_qq_connect_remains_clickable_when_no_runtime_detected(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = StubFacade(sources=sources)
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._qq_connect_button.isEnabled() is True
    page._qq_connect_button.click()
    _drain(page)

    assert facade.start_qq_auth_flow_calls == [1]


def test_qq_connect_offers_cancel_while_connecting(qt_app, sources) -> None:
    module = _facade_module()
    status = _connection_status(
        available=True,
        qce_running=True,
        authenticated=True,
        message="QQ \u5df2\u8fde\u63a5\u3002",
        action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    executor = _DeferredExecutor()
    page = _analysis_page(qt_app, facade, executor=executor)

    page.select_source(module.ChatSource.QQ)
    _drain(page)
    page._qq_connect_button.click()

    assert executor.operation is not None
    assert page._qq_connect_button.isEnabled() is True
    assert page._qq_connect_button.text() == "取消连接"
    assert (
        "\u6b63\u5728\u51c6\u5907QQ\u8fde\u63a5\u73af\u5883\uff0c\u8bf7\u7a0d\u5019"
        in page._status_label.text()
    )

    executor.succeed(facade._qq_snapshot())
    _drain(page)
    QTest.qWait(600)

    assert page._qq_connect_button.isEnabled() is True
    assert page._qq_connect_button.isVisibleTo(page) is False
    assert "重新连接" not in page._qq_connect_button.text()


def test_wechat_connection_error_blocks_session_loading_without_leaks(
    qt_app,
) -> None:
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[_session(_facade_module().ChatSource.WECHAT, "wxid", "Fictional")],
        connection_error=RuntimeError("raw provider failure"),
    )
    page = _analysis_page(qt_app, facade)
    received: list[tuple[str, str]] = []
    page.analysis_failed.connect(lambda code, msg: received.append((code, msg)))
    _drain(page)

    page.select_source(_facade_module().ChatSource.WECHAT)
    _drain(page)

    assert facade.list_sessions_calls == []
    assert page._session_list.count() == 1
    assert "暂无会话" in page._session_list.item(0).text()
    assert received == []
    assert page._status_label.text() == "\u65e0\u6cd5\u786e\u8ba4\u8fde\u63a5\u72b6\u6001\u3002"
    assert "raw provider failure" not in page._status_label.text()


def test_wechat_unconfigured_keeps_advanced_setup_hidden(qt_app) -> None:
    module = _facade_module()
    status = _wechat_connection_status(
        available=False,
        data_found=False,
        db_key_available=False,
        runtime_available=False,
        message="\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e\u76ee\u5f55\u3002",
        action_hint="\u8bf7\u5b8c\u6210\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e\u3002",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=status,
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert page._wechat_setup_button.isVisibleTo(page) is False
    assert page._wechat_connect_button.isVisibleTo(page) is True


def test_clicking_wechat_setup_calls_facade(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page._wechat_setup_button.click()

    assert facade.get_wechat_setup_status_calls == [1]
    assert page._wechat_setup_dialog is not None


def test_clicking_wechat_connect_completes_without_uncaught_error(
    qt_app,
) -> None:
    module = _facade_module()
    ready = _wechat_connection_status(
        available=True,
        data_found=True,
        db_key_available=True,
        runtime_available=True,
        message="\u5fae\u4fe1\u6570\u636e\u6e90\u53ef\u7528",
        action_hint="",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[
            _session(
                module.ChatSource.WECHAT,
                "wxid_fictional",
                "Fictional Alice",
            )
        ],
        connection_status=ready,
        data_root="D:/fake_xwechat_files",
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page._wechat_connect_button.click()
    _drain(page)

    assert facade.detect_wechat_data_roots_calls
    assert facade.setup_wechat_environment_calls == [
        module.WeChatEnvironmentConfig(
            data_root=Path("D:/fake_xwechat_files")
        )
    ]
    assert len(facade.acquire_wechat_db_key_calls) == 1
    assert page._wechat_connect_button.isEnabled() is True
    assert "\u5fae\u4fe1\u5df2\u8fde\u63a5" in page._status_label.text()


def test_key_success_then_database_failure_shows_database_stage(
    qt_app,
) -> None:
    module = _facade_module()
    ready = _wechat_connection_status(
        available=True,
        data_found=True,
        db_key_available=True,
        runtime_available=True,
        message="\u5fae\u4fe1\u6570\u636e\u6e90\u53ef\u7528",
        action_hint="",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=ready,
        data_root="D:/fake_xwechat_files",
        error=module.FacadeError(
            code="query_failed",
            public_message="\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u5e93\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5\u3002",
            source=module.ChatSource.WECHAT,
        ),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    facade.list_sessions_calls.clear()
    page._wechat_connect_button.click()
    _drain(page)

    assert facade.acquire_wechat_db_key_calls
    assert facade.list_sessions_calls == [module.ChatSource.WECHAT]
    assert "\u6570\u636e\u5e93\u8bfb\u53d6\u5931\u8d25" in page._status_label.text()
    assert "\u5fae\u4fe1\u672a\u8fde\u63a5" not in page._status_label.text()


def test_wechat_session_load_failure_shows_session_stage(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        error=module.FacadeError(
            code="wechat_session_load_failed",
            public_message="\u5fae\u4fe1\u4f1a\u8bdd\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5\u3002",
            source=module.ChatSource.WECHAT,
        ),
    )
    page = _analysis_page(qt_app, facade)
    page._selected_source = module.ChatSource.WECHAT

    page._load_sessions(module.ChatSource.WECHAT)
    _drain(page)

    assert "\u4f1a\u8bdd\u52a0\u8f7d\u5931\u8d25" in page._status_label.text()


def test_clicking_wechat_connect_without_detected_root_opens_setup(
    qt_app,
) -> None:
    module = _facade_module()
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page._wechat_connect_button.click()
    _drain(page)

    assert page._wechat_setup_dialog is not None
    assert facade.setup_wechat_environment_calls == []


def test_wechat_guide_shows_status_confirmation(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=_wechat_connection_status(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message="\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e",
            action_hint="\u8bf7\u767b\u5f55\u5fae\u4fe1\u6216\u914d\u7f6e\u6570\u636e\u76ee\u5f55\u3002",
        ),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert page._wechat_guide_label.isVisibleTo(page) is True
    assert page._wechat_guide_key_label.isVisibleTo(page) is True
    assert page._wechat_guide_note_label.isVisibleTo(page) is True
    assert "正在准备微信连接" in page._wechat_guide_label.text()
    assert "请确保微信电脑版已安装" not in page._wechat_guide_label.text()
    assert "如需查看微信数据目录" not in page._wechat_guide_label.text()
    assert "请进入微信，余音会捕捉登录这一刻的“声音”" in (
        page._wechat_guide_key_label.text()
    )
    assert "请保持微信停留在登录界面" not in page._wechat_guide_key_label.text()
    assert "\u4e0d\u4e0a\u4f20" not in page._wechat_guide_key_label.text()
    assert "\u4e0d\u4fdd\u5b58" not in page._wechat_guide_key_label.text()
    assert "等待微信登录" in page._wechat_guide_note_label.text()
    assert "\u4e0d\u4e0a\u4f20" in page._wechat_guide_note_label.text()
    assert "\u4e0d\u4fdd\u5b58" in page._wechat_guide_note_label.text()
    assert "LCA" not in page._wechat_guide_key_label.text()


def test_wechat_critical_login_hint_is_plain_text_with_wrap(
    qt_app,
) -> None:
    page = _analysis_page(
        qt_app,
        StubFacade(sources=_wechat_available_sources()),
    )
    module = importlib.import_module("qq_chat_analyzer.gui.analysis_page")

    assert page._wechat_guide_label.wordWrap() is True
    assert page._wechat_guide_key_label.wordWrap() is True
    assert page._wechat_guide_note_label.wordWrap() is True
    assert page._wechat_guide_label.sizePolicy().horizontalPolicy() == (
        QSizePolicy.Policy.Expanding
    )
    assert page._wechat_guide_key_label.sizePolicy().horizontalPolicy() == (
        QSizePolicy.Policy.Expanding
    )
    assert page._wechat_guide_note_label.sizePolicy().horizontalPolicy() == (
        QSizePolicy.Policy.Expanding
    )
    warning_text = module._WECHAT_GUIDE_WARNING
    assert "请进入微信，余音会捕捉登录这一刻的“声音”" in warning_text
    assert "请保持微信停留在登录界面" not in warning_text
    assert "<br>" not in warning_text
    assert "<span" not in warning_text
    note_text = module._WECHAT_GUIDE_NOTE
    assert "\u4e0d\u4e0a\u4f20" in note_text
    assert "\u4e0d\u4fdd\u5b58" in note_text
    assert "<br>" not in note_text
    assert "<span" not in note_text


def test_wechat_auto_detected_root_continues_connect(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        data_root="D:/fake_xwechat_files",
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page._wechat_connect_button.click()
    _drain(page)

    assert facade.detect_wechat_data_roots_calls == [1]
    assert getattr(page, "_wechat_setup_dialog", None) is None
    assert facade.setup_wechat_environment_calls == [
        module.WeChatEnvironmentConfig(
            data_root=Path("D:/fake_xwechat_files")
        )
    ]


def test_wechat_multiple_roots_offer_choice(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        data_roots=[
            Path("D:/xwechat_files/wxid_first"),
            Path("D:/xwechat_files/wxid_second"),
        ],
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page._wechat_connect_button.click()
    _drain(page)

    assert "\u591a\u4e2a" in page._status_label.text()
    assert page._wechat_setup_dialog is not None
    dialog = page._wechat_setup_dialog
    assert dialog._use_data_roots is True
    assert dialog._data_root_combo is not None
    assert dialog._data_root_combo.count() == 2
    assert facade.setup_wechat_environment_calls == []


def test_wechat_not_detected_shows_directory_help(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page._wechat_connect_button.click()
    _drain(page)

    assert "\u672a\u81ea\u52a8\u8bc6\u522b\u5230\u5fae\u4fe1\u5b58\u50a8\u4f4d\u7f6e" in (
        page._status_label.text()
    )
    assert page._wechat_setup_dialog is not None
    dialog = page._wechat_setup_dialog
    assert "如果未能自动识别微信数据目录" in dialog._hint_label.text()
    assert "填写完成后，请退出微信到未登录界面" in dialog._hint_label.text()
    assert "\u5982\u679c\u672a\u80fd\u81ea\u52a8\u8bc6\u522b\u5fae\u4fe1\u6570\u636e\u76ee\u5f55" in (
        page._wechat_guide_label.text()
    )
    assert "\u5b58\u50a8\u4f4d\u7f6e" in page._wechat_guide_label.text()
    assert "\u586b\u5199\u5b8c\u6210\u540e\uff0c\u8bf7\u9000\u51fa\u5fae\u4fe1\u5230\u672a\u767b\u5f55\u754c\u9762" in (
        page._wechat_guide_label.text()
    )


def test_saving_wechat_environment_refreshes_status(qt_app) -> None:
    module = _facade_module()
    ready = _wechat_connection_status(
        available=True,
        data_found=True,
        db_key_available=True,
        runtime_available=True,
        message="\u5fae\u4fe1\u6570\u636e\u6e90\u53ef\u7528\uff0c\u53ef\u4ee5\u5f00\u59cb\u5206\u6790\u3002",
        action_hint="",
    )
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=ready,
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    status_calls_before = len(facade.get_connection_status_calls)
    config = module.WeChatEnvironmentConfig(
        data_root="D:/fake_root",
        db_key="fictional-key",
    )

    page.save_wechat_environment(config)
    _drain(page)

    assert facade.setup_wechat_environment_calls == [config]
    assert len(facade.get_connection_status_calls) == status_calls_before + 1
    assert "\u5fae\u4fe1\u5df2\u8fde\u63a5" in page._status_label.text()


def test_wechat_setup_failure_shows_user_prompt(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        setup_error=module.FacadeError(
            "wechat_config_write_failed",
            "\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e\u4fdd\u5b58\u5931\u8d25\uff0c"
            "\u8bf7\u68c0\u67e5\u5199\u5165\u6743\u9650\u540e\u91cd\u8bd5\u3002",
            source=module.ChatSource.WECHAT,
        ),
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page.save_wechat_environment(module.WeChatEnvironmentConfig())
    _drain(page)

    assert "\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e\u4fdd\u5b58\u5931\u8d25" in (
        page._status_label.toolTip() or ""
    )
    assert "Traceback" not in (page._status_label.toolTip() or "")


def test_analysis_page_lists_sources_from_the_facade(qt_app, sources) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    buttons = page._source_buttons

    assert len(buttons) == 2
    assert buttons[module.ChatSource.QQ].isEnabled() is True
    assert module.ChatSource.WECHAT in buttons
    assert module.ChatSource.LOCAL_FILE not in buttons


def test_unavailable_sources_are_disabled_with_a_reason(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    wechat_button = page._source_buttons[module.ChatSource.WECHAT]

    assert wechat_button.isEnabled() is False
    assert wechat_button.toolTip() != ""


def test_dashboard_page_starts_empty(qt_app) -> None:
    page = _dashboard_page(qt_app)

    assert page._user_table.rowCount() == 0
    assert page._word_list.count() == 0
    assert page._empty_label.isVisibleTo(page) is True


# ------------------------------------------------------------------ sessions


def test_selecting_a_source_loads_sessions_through_the_facade(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A", 12),
            _session(module.ChatSource.QQ, "10002", "\u865a\u6784\u7fa4 B"),
        ],
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert facade.list_sessions_calls == [module.ChatSource.QQ]
    assert page._session_list.count() == 2
    assert page._session_list.item(0).text() == "\u865a\u6784\u7fa4 A"


def test_session_ids_are_stored_but_never_displayed(qt_app, sources) -> None:
    module = importlib.import_module("qq_chat_analyzer.gui.analysis_page")
    facade_module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[
            _session(
                facade_module.ChatSource.QQ,
                "secret-id-10001",
                "\u865a\u6784\u7fa4 A",
            )
        ],
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)

    page.select_source(facade_module.ChatSource.QQ)
    _drain(page)
    item = page._session_list.item(0)

    assert item.text() == "\u865a\u6784\u7fa4 A"
    assert "secret-id-10001" not in item.text()
    assert item.data(module.SESSION_ID_ROLE) == "secret-id-10001"


def test_local_file_source_shows_no_session_list(qt_app, sources) -> None:
    module = _facade_module()
    facade = StubFacade(sources=sources)
    page = _analysis_page(qt_app, facade)

    page.select_source(module.ChatSource.LOCAL_FILE)
    _drain(page)

    assert facade.list_sessions_calls == []
    assert page._session_list.count() == 0


def test_empty_session_list_is_reported(qt_app, sources) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources, sessions=[]))

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._session_list.count() == 1
    assert "没有找到可分析的聊天记录" in page._session_list.item(0).text()


def test_session_count_shows_in_session_box_for_qq(qt_app, sources) -> None:
    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=sources,
            sessions=[
                _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A"),
                _session(module.ChatSource.QQ, "10002", "\u865a\u6784\u7fa4 B"),
                _session(module.ChatSource.QQ, "10003", "\u865a\u6784\u7fa4 C"),
            ],
        ),
    )

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert "\u4f1a\u8bdd\u5217\u8868\uff083\uff09" in page._session_box.title()


def test_session_count_shows_in_session_box_for_wechat(qt_app, sources) -> None:
    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=sources,
            sessions=[
                _session(module.ChatSource.WECHAT, "wxid_a", "\u865a\u6784\u5bf9\u8bdd A"),
                _session(module.ChatSource.WECHAT, "wxid_b", "\u865a\u6784\u5bf9\u8bdd B"),
            ],
        ),
    )

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert "\u4f1a\u8bdd\u5217\u8868\uff082\uff09" in page._session_box.title()


def test_session_count_resets_to_zero_for_empty_and_refresh(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    page._populate_sessions(
        [
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A"),
            _session(module.ChatSource.QQ, "10002", "\u865a\u6784\u7fa4 B"),
        ]
    )
    assert "\u4f1a\u8bdd\u5217\u8868\uff082\uff09" in page._session_box.title()

    page._populate_sessions([])
    assert "\u4f1a\u8bdd\u5217\u8868\uff080\uff09" in page._session_box.title()

    page._populate_sessions(
        [_session(module.ChatSource.QQ, "10003", "\u865a\u6784\u7fa4 C")]
    )
    assert "\u4f1a\u8bdd\u5217\u8868\uff081\uff09" in page._session_box.title()


def test_session_count_appears_only_in_session_box(qt_app, sources) -> None:
    from PySide6.QtWidgets import QLabel

    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=sources,
            sessions=[
                _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A"),
                _session(module.ChatSource.QQ, "10002", "\u865a\u6784\u7fa4 B"),
            ],
        ),
    )
    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert "\u4f1a\u8bdd\u5217\u8868\uff082\uff09" in page._session_box.title()
    label_texts = [
        label.text()
        for label in page.findChildren(QLabel)
        if label.text()
    ]
    assert all("\u4e2a\u4f1a\u8bdd" not in text for text in label_texts)


def test_session_search_filters_display_names(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[
            _session(module.ChatSource.WECHAT, "wxid_a", "Alice"),
            _session(module.ChatSource.WECHAT, "wxid_b", "Board Game"),
            _session(module.ChatSource.WECHAT, "wxid_c", "Alice's Study Room"),
        ],
    )
    page = _analysis_page(qt_app, facade)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page._session_search.setText("alice")

    assert page._session_list.count() == 2
    assert [page._session_list.item(i).text() for i in range(2)] == [
        "Alice",
        "Alice's Study Room",
    ]

    page._session_search.setText("board")

    assert page._session_list.count() == 1
    assert page._session_list.item(0).text() == "Board Game"


def test_session_sort_modes_reorder_the_list(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[
            _session(
                module.ChatSource.WECHAT,
                "wxid_old",
                "Alpha",
                count=50,
                last_message_time=100,
            ),
            _session(
                module.ChatSource.WECHAT,
                "wxid_new",
                "Beta",
                count=1,
                last_message_time=300,
            ),
            _session(
                module.ChatSource.WECHAT,
                "wxid_mid",
                "Gamma",
                count=30,
                last_message_time=200,
            ),
        ],
    )
    page = _analysis_page(qt_app, facade)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    def names():
        return [
            page._session_list.item(i).text()
            for i in range(page._session_list.count())
        ]

    assert names() == ["Beta", "Gamma", "Alpha"]

    page._session_sort.setCurrentIndex(
        _sort_index(page, "message_count")
    )
    assert names() == ["Alpha", "Gamma", "Beta"]

    page._session_sort.setCurrentIndex(_sort_index(page, "name"))
    assert names() == ["Alpha", "Beta", "Gamma"]


def test_wechat_session_without_messages_is_disabled_and_not_analyzable(
    qt_app,
) -> None:
    module = _facade_module()
    sessions = [
        module.SessionInfo(
            source=module.ChatSource.WECHAT,
            session_id="wxid_no_messages",
            display_name="No messages",
            message_available=False,
            unavailable_reason="\u8be5\u4f1a\u8bdd\u6ca1\u6709\u53ef\u5206\u6790\u6d88\u606f",
        )
    ]
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=sessions,
    )
    page = _analysis_page(qt_app, facade)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    item = page._session_list.item(0)
    assert not (item.flags() & Qt.ItemFlag.ItemIsEnabled)
    assert "\u8be5\u4f1a\u8bdd\u6ca1\u6709\u53ef\u5206\u6790\u6d88\u606f" in item.toolTip()
    assert page._analyze_button.isEnabled() is False

    page.start_analysis()
    _drain(page)

    assert facade.analyze_session_calls == []


# ------------------------------------------------------------------ analysis


def test_analyze_button_stays_disabled_until_a_session_is_chosen(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)

    assert page._analyze_button.isEnabled() is False

    page.select_source(module.ChatSource.QQ)
    _drain(page)
    page._session_list.setCurrentRow(0)

    assert page._analyze_button.isEnabled() is True


def test_analysis_controls_hidden_until_sessions_are_loaded(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=sources,
            sessions=[],
            connection_status=_connection_status(
                available=False,
                qce_running=False,
                authenticated=False,
                message="QQ \u672a\u8fde\u63a5\u3002",
                action_hint="\u8bf7\u5148\u8fde\u63a5 QQ\u3002",
            ),
        ),
    )

    assert page._analysis_range_box.isVisibleTo(page) is False
    assert page._analyze_button.isVisibleTo(page) is False

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._analysis_range_box.isVisibleTo(page) is False
    assert page._analyze_button.isVisibleTo(page) is False


def test_analysis_controls_visible_after_qq_sessions_load(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=sources,
            sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        ),
    )

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._analysis_range_box.isVisibleTo(page) is True
    assert page._analyze_button.isVisibleTo(page) is True


def test_analysis_controls_visible_after_wechat_sessions_load(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=sources,
            sessions=[
                _session(module.ChatSource.WECHAT, "wxid_a", "\u865a\u6784\u5bf9\u8bdd")
            ],
        ),
    )

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert page._analysis_range_box.isVisibleTo(page) is True
    assert page._analyze_button.isVisibleTo(page) is True


def test_analysis_controls_hidden_after_connection_failure(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=sources,
            sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        ),
    )
    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._analysis_range_box.isVisibleTo(page) is True

    page._show_disconnected_session_placeholder(module.ChatSource.QQ)

    assert page._analysis_range_box.isVisibleTo(page) is False
    assert page._analyze_button.isVisibleTo(page) is False


def test_analysis_controls_hidden_when_switching_source(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=sources,
            sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        ),
    )
    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._analysis_range_box.isVisibleTo(page) is True

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    page._show_unconnected_session_placeholder()

    assert page._analysis_range_box.isVisibleTo(page) is False
    assert page._analyze_button.isVisibleTo(page) is False


def test_start_analysis_calls_analyze_session(qt_app, sources) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        outcome=_StubOutcome(_dashboard_view()),
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)
    page.select_source(module.ChatSource.QQ)
    _drain(page)
    page._session_list.setCurrentRow(0)

    page.start_analysis()
    _drain(page)

    assert len(facade.analyze_session_calls) == 1
    source, session_id, config = facade.analyze_session_calls[0]
    assert source == module.ChatSource.QQ
    assert session_id == "10001"
    assert config is not None
    assert facade.analyze_file_calls == []


def test_start_analysis_calls_analyze_file_for_local_files(
    qt_app,
    sources,
    tmp_path: Path,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        outcome=_StubOutcome(_dashboard_view()),
    )
    page = _analysis_page(qt_app, facade)
    export = tmp_path / "fictional.json"
    export.write_text("{}", encoding="utf-8")

    page.select_source(module.ChatSource.LOCAL_FILE)
    page.set_selected_file(export)
    page.start_analysis()
    _drain(page)

    assert len(facade.analyze_file_calls) == 1
    assert facade.analyze_file_calls[0][0] == export
    assert facade.analyze_session_calls == []


def test_start_analysis_does_nothing_without_a_selection(
    qt_app,
    sources,
) -> None:
    facade = StubFacade(sources=sources)
    page = _analysis_page(qt_app, facade)

    page.start_analysis()
    _drain(page)

    assert facade.analyze_session_calls == []
    assert facade.analyze_file_calls == []


def test_analysis_scope_defaults_to_all(qt_app, sources) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    config = page.build_config()

    assert page._scope_all.isChecked() is True
    assert page._custom_range_widget.isHidden() is True
    assert config.scope_mode is module.AnalysisScopeMode.ALL
    assert config.start_time is None
    assert config.end_time is None


@pytest.mark.parametrize(
    ("control_name", "expected_mode"),
    [
        ("_scope_last_year", "LAST_YEAR"),
        ("_scope_last_six_months", "LAST_SIX_MONTHS"),
    ],
)
def test_relative_scope_selection_reaches_the_config(
    qt_app,
    sources,
    control_name,
    expected_mode,
) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    getattr(page, control_name).setChecked(True)
    config = page.build_config()

    assert config.scope_mode is getattr(module.AnalysisScopeMode, expected_mode)
    assert config.start_time is None
    assert config.end_time is None
    assert page._custom_range_widget.isHidden() is True


def test_custom_scope_shows_dates_and_reaches_the_config(qt_app, sources) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    page._scope_custom.setChecked(True)
    page._start_date.setDate(QDate(2026, 2, 11))
    page._end_date.setDate(QDate(2026, 8, 11))
    config = page.build_config()

    assert page._custom_range_widget.isHidden() is False
    assert config.scope_mode is module.AnalysisScopeMode.CUSTOM
    assert config.start_time == "2026-02-11"
    assert config.end_time == "2026-08-11"


def test_custom_scope_uses_session_message_range(qt_app) -> None:
    from datetime import datetime

    module = _facade_module()
    session_id = "wxid_time_range"
    start = 1704067200
    end = 1704153600
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[
            _session(
                module.ChatSource.WECHAT,
                session_id,
                "Fictional Room",
                1,
            )
        ],
        message_range=(start, end),
    )
    page = _analysis_page(qt_app, facade)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)
    page._session_list.setCurrentRow(0)
    _drain(page)
    page._scope_custom.setChecked(True)

    assert facade.get_session_message_range_calls == [
        (module.ChatSource.WECHAT, session_id)
    ]
    assert page._start_date.date().toPython() == datetime.fromtimestamp(
        start
    ).date()
    assert page._end_date.date().toPython() == datetime.fromtimestamp(
        end
    ).date()


def test_qq_selection_initializes_time_range_from_session_messages(
    qt_app,
    sources,
) -> None:
    from datetime import datetime

    module = _facade_module()
    session_id = "10001"
    start = 1704067200
    end = 1704153600
    facade = StubFacade(
        sources=sources,
        sessions=[
            _session(
                module.ChatSource.QQ,
                session_id,
                "Fictional Group",
            )
        ],
        message_range=(start, end),
    )
    page = _analysis_page(qt_app, facade)

    page.select_source(module.ChatSource.QQ)
    _drain(page)
    page._session_list.setCurrentRow(0)
    _drain(page)
    page._scope_custom.setChecked(True)

    assert facade.get_session_message_range_calls == [
        (module.ChatSource.QQ, session_id)
    ]
    assert page._start_date.date().toPython() == datetime.fromtimestamp(
        start
    ).date()
    assert page._end_date.date().toPython() == datetime.fromtimestamp(
        end
    ).date()


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            "invalid_analysis_scope",
            "开始日期不能晚于结束日期，请重新选择。",
        ),
        (
            "no_messages_in_scope",
            "当前时间范围内没有可分析的聊天记录。",
        ),
    ],
)
def test_scope_errors_show_the_reason_and_restore_analysis_controls(
    qt_app,
    sources,
    code,
    message,
) -> None:
    module = _facade_module()
    sessions = [_session(module.ChatSource.QQ, "10001", "Fictional Group")]
    facade = StubFacade(
        sources=sources,
        sessions=sessions,
        error=module.FacadeError(code=code, public_message=message),
    )
    page = _analysis_page(qt_app, facade)
    page._selected_source = module.ChatSource.QQ
    page._populate_sessions(sessions)
    page._session_list.setCurrentRow(0)
    failures = []
    page.analysis_failed.connect(lambda error_code, text: failures.append((error_code, text)))
    if code == "invalid_analysis_scope":
        page._scope_custom.setChecked(True)
        page._start_date.setDate(QDate(2026, 8, 12))
        page._end_date.setDate(QDate(2026, 8, 11))

    page.start_analysis()
    _drain(page)

    assert failures == [(code, message)]
    assert page._analysis_running is False
    assert page._analyze_button.isEnabled() is True


# ----------------------------------------------------------------- dashboard


def test_dashboard_renders_every_section(qt_app) -> None:
    page = _dashboard_page(qt_app)

    page.render_view(_dashboard_view())

    assert page._title_label.text() == "\u865a\u6784\u62a5\u544a"
    assert page._user_table.rowCount() == 1
    assert page._user_table.item(0, 1).text() == "Fictional-Alice"
    assert page._user_table.item(0, 3).text() == "75.0%"
    assert page._word_list.count() == 2
    assert "deck" in page._word_list.item(0).text()
    assert page._conversation_table.rowCount() == 1
    assert page._conversation_table.item(0, 3).text() == "2 \u5c0f\u65f6 0 \u5206\u949f"
    assert page._metrics_layout.count() == 1


def test_dashboard_shows_the_empty_state(qt_app) -> None:
    page = _dashboard_page(qt_app)

    page.render_view(_dashboard_view(has_data=False))

    assert page._user_table.rowCount() == 0
    assert page._word_list.count() == 0
    assert page._empty_label.text() == "\u6ca1\u6709\u6570\u636e\u3002"


def test_dashboard_tolerates_a_missing_view(qt_app) -> None:
    page = _dashboard_page(qt_app)

    page.render_view(None)

    assert page._user_table.rowCount() == 0


def test_dashboard_rerender_replaces_previous_content(qt_app) -> None:
    page = _dashboard_page(qt_app)

    page.render_view(_dashboard_view())
    page.render_view(_dashboard_view())

    assert page._user_table.rowCount() == 1
    assert page._metrics_layout.count() == 1


def test_successful_analysis_no_longer_switches_to_the_dashboard(
    qt_app,
    sources,
    tmp_path,
) -> None:
    """A successful legacy analysis opens Echo and never lands on Dashboard."""
    from qq_chat_analyzer.gui.main_window import (
        ANALYSIS_PAGE_INDEX,
        DASHBOARD_PAGE_INDEX,
    )
    module = _facade_module()
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened: list[Path] = []
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "虚构群")],
        outcome=_StubOutcome(_dashboard_view(), report_path=report_path),
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    window = _main_window(qt_app, facade)
    window._report_opener = lambda path: opened.append(path) or True
    window.analysis_page.select_source(module.ChatSource.QQ)
    _drain(window.analysis_page)
    window.analysis_page._session_list.setCurrentRow(0)

    window.analysis_page.start_analysis()
    _drain(window.analysis_page)

    assert window.stack.currentIndex() == ANALYSIS_PAGE_INDEX
    assert window.stack.currentIndex() != DASHBOARD_PAGE_INDEX
    assert opened == [report_path.resolve()]


def test_show_outcome_without_report_path_stays_recoverable(
    qt_app,
    sources,
) -> None:
    """Success without a report path never crashes and avoids Dashboard."""
    from qq_chat_analyzer.gui.main_window import DASHBOARD_PAGE_INDEX

    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_outcome(_dashboard_view())

    assert window.stack.currentIndex() != DASHBOARD_PAGE_INDEX
    assert window.analysis_page._status_label.text() == "分析完成"
    assert not window._open_echo_button.isVisibleTo(window)


def test_successful_outcome_saves_report_and_opens_echo(
    qt_app,
    sources,
    tmp_path,
) -> None:
    """MainWindow keeps the report path and reuses the existing opener."""
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened: list[Path] = []
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: opened.append(path) or True

    window.show_outcome(
        _StubOutcome(_dashboard_view(), report_path=report_path)
    )

    assert window._current_report_path == report_path.resolve()
    assert window._open_echo_button.isVisibleTo(window)
    assert window._open_echo_button.isEnabled()
    assert opened == [report_path.resolve()]


def test_echo_entry_reopens_the_latest_outcome_report_path(
    qt_app,
    sources,
    tmp_path,
) -> None:
    first_path = tmp_path / "first-report.html"
    second_path = tmp_path / "second-report.html"
    first_path.write_text("<html>first</html>", encoding="utf-8")
    second_path.write_text("<html>second</html>", encoding="utf-8")
    opened: list[Path] = []
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: opened.append(path) or True

    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=first_path))
    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=second_path))
    assert opened == [first_path.resolve(), second_path.resolve()]
    window._open_echo_button.click()

    assert opened == [
        first_path.resolve(),
        second_path.resolve(),
        second_path.resolve(),
    ]


def test_default_echo_opener_uses_windows_file_association(
    qt_app,
    tmp_path,
    monkeypatch,
) -> None:
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    report_path = (tmp_path / "echo-report.html").resolve()
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened_paths = []
    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(
        module.os,
        "startfile",
        lambda path: opened_paths.append(path),
        raising=False,
    )

    assert module._open_report_path(report_path) is True
    assert opened_paths == [str(report_path)]


def test_default_echo_opener_uses_local_file_url_outside_windows(
    qt_app,
    tmp_path,
    monkeypatch,
) -> None:
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    report_path = (tmp_path / "echo-report.html").resolve()
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened_urls = []
    monkeypatch.setattr(module.os, "name", "posix")
    monkeypatch.setattr(
        module.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url) or True,
    )

    assert module._open_report_path(report_path) is True
    assert len(opened_urls) == 1
    assert opened_urls[0].isLocalFile()
    assert opened_urls[0].toLocalFile() == str(report_path).replace("\\", "/")


def test_missing_report_and_failed_analysis_leave_echo_entry_unavailable(
    qt_app,
    sources,
    tmp_path,
    monkeypatch,
) -> None:
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True
    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=report_path))

    window.show_processing_page()
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *_args: None)
    window.show_error("fictional_failure", "虚构分析失败")

    assert not window._open_echo_button.isVisibleTo(window)
    assert not window._open_echo_button.isEnabled()

    report_path.unlink()
    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=report_path))

    assert not window._open_echo_button.isVisibleTo(window)
    assert not window._open_echo_button.isEnabled()


def test_echo_open_failure_is_recoverable_and_does_not_crash(
    qt_app,
    sources,
    tmp_path,
) -> None:
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX

    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")

    def _failing_opener(path):
        raise OSError("fictional open failure")

    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = _failing_opener
    window.navigate_to_qq()
    _drain(window)

    window.show_outcome(
        _StubOutcome(_dashboard_view(), report_path=report_path)
    )

    assert window._current_report_path == report_path.resolve()
    assert "无法打开" in window.analysis_page._status_label.text()
    assert window._open_echo_button.isVisibleTo(window)
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX


@pytest.mark.parametrize(
    ("history_saved", "expected_status"),
    [
        (True, "分析已保存"),
        (False, "分析完成，但历史记录保存失败。"),
        (None, "分析完成"),
    ],
)
def test_show_outcome_reports_history_save_status_after_success(
    qt_app,
    sources,
    history_saved,
    expected_status,
) -> None:
    from qq_chat_analyzer.gui.main_window import DASHBOARD_PAGE_INDEX

    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_outcome(
        _StubOutcome(_dashboard_view(), history_saved=history_saved)
    )

    assert window.stack.currentIndex() != DASHBOARD_PAGE_INDEX
    assert window.analysis_page._status_label.text() == expected_status


def test_show_outcome_appends_snapshot_acquisition_time_to_existing_status(
    qt_app,
    sources,
) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            history_saved=True,
            data_acquired_at=datetime(
                2026,
                8,
                11,
                12,
                30,
                tzinfo=timezone.utc,
            ),
        )
    )

    assert window.analysis_page._status_label.text() == (
        "分析已保存"
        " · 数据获取时间："
        "2026-08-11 12:30+00:00"
    )

def test_analysis_enters_processing_page_and_rejects_second_start(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window.analysis_page._selected_source = module.ChatSource.QQ
    window.analysis_page._populate_sessions(facade._sessions)
    window.analysis_page._session_list.setCurrentRow(0)
    executor.submission_count = 0

    window.analysis_page.start_analysis()
    window.analysis_page.start_analysis()

    assert window.stack.currentIndex() == 3
    assert window.processing_status_label.text()
    assert window.analysis_page.isEnabled() is False
    assert executor.submission_count == 0
    QApplication.processEvents()
    assert executor.submission_count == 1
    assert window.analysis_page._analysis_running is True


def test_analysis_progress_is_forwarded_to_the_processing_page(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "虚构群")],
    )
    window = _main_window(qt_app, facade, executor=executor)
    page = window.analysis_page
    page._selected_source = module.ChatSource.QQ
    page._populate_sessions(facade._sessions)
    page._session_list.setCurrentRow(0)

    page.start_analysis()
    QApplication.processEvents()
    executor.progress("正在处理消息...")

    assert window.processing_status_label.text() == "正在处理消息..."
    assert page.isEnabled() is False
    assert page._analysis_running is True


def test_connecting_qq_locks_sources_and_cancel_restores_selection(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    facade = StubFacade(sources=sources)
    page = _analysis_page(qt_app, facade, executor=executor)
    page._selected_source = module.ChatSource.QQ

    page.connect_qq()

    assert all(not button.isEnabled() for button in page._source_buttons.values())
    assert page._qq_connect_button.text() == "取消连接"

    page.cancel_connection()

    assert executor.cancelled is True
    assert page._source_buttons[module.ChatSource.QQ].isEnabled() is True
    assert page._source_buttons[module.ChatSource.WECHAT].isEnabled() is False
    assert page._qq_connect_button.text() == "连接QQ"
    assert "已取消" in page._status_label.text()


def test_connecting_wechat_locks_sources_and_cancel_restores_selection(
    qt_app,
) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade, executor=executor)
    page._selected_source = module.ChatSource.WECHAT

    page._start_wechat_connect(
        module.WeChatEnvironmentConfig(data_root="D:/fictional_wechat")
    )
    assert page._wechat_connect_button.text() == "取消连接"
    assert all(not button.isEnabled() for button in page._source_buttons.values())

    page.cancel_connection()

    assert executor.cancelled is True
    assert page._wechat_connect_button.text() == "连接微信"
    assert all(button.isEnabled() for button in page._source_buttons.values())


def test_cancel_analysis_returns_to_selection_and_releases_all_locks(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "虚构群")],
    )
    window = _main_window(qt_app, facade, executor=executor)
    page = window.analysis_page
    page._selected_source = module.ChatSource.QQ
    page._populate_sessions(facade._sessions)
    page._session_list.setCurrentRow(0)

    page.start_analysis()
    QApplication.processEvents()
    assert window._cancel_analysis_button.isHidden() is False

    window._cancel_analysis_button.click()

    assert executor.cancelled is True
    assert window.stack.currentIndex() == 6
    assert page._analysis_running is False
    assert page.isEnabled() is True
    assert page._session_list.isEnabled() is True


def test_failed_analysis_returns_to_selection_and_releases_lock(
    qt_app,
    sources,
    monkeypatch,
) -> None:
    module = _facade_module()
    main_window_module = importlib.import_module(
        "qq_chat_analyzer.gui.main_window"
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        lambda *args: None,
    )
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.WECHAT, "room-1", "\u865a\u6784\u4f1a\u8bdd")],
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window.analysis_page._selected_source = module.ChatSource.WECHAT
    window.analysis_page._populate_sessions(facade._sessions)
    window.analysis_page._session_list.setCurrentRow(0)
    window.analysis_page.start_analysis()
    _drain(window.analysis_page)

    assert executor.operation is not None
    executor.operation(lambda _message: None)
    assert facade.analyze_session_calls[0][0] == module.ChatSource.WECHAT
    executor.fail("fictional_failure", "\u865a\u6784\u5206\u6790\u5931\u8d25")

    assert window.stack.currentIndex() == 6
    assert window.analysis_page._analysis_running is False
    assert window.analysis_page._analyze_button.isEnabled() is True
    assert "\u865a\u6784\u5206\u6790\u5931\u8d25" in (
        window.analysis_page._status_label.text()
    )


# -------------------------------------------------------------------- errors


def test_facade_errors_surface_as_public_messages(qt_app, sources) -> None:
    module = _facade_module()
    error = module.FacadeError(
        code="wechat_export_unavailable",
        public_message="\u5fae\u4fe1\u5bfc\u51fa\u4e0d\u53ef\u7528\u3002",
    )
    facade = StubFacade(
        sources=sources,
        error=error,
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)
    received: list[tuple[str, str]] = []
    page.analysis_failed.connect(lambda code, msg: received.append((code, msg)))

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert received == [
        ("wechat_export_unavailable", "\u5fae\u4fe1\u5bfc\u51fa\u4e0d\u53ef\u7528\u3002")
    ]


def test_unexpected_errors_never_leak_a_traceback(qt_app, sources) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        error=RuntimeError("boom internal"),
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    page = _analysis_page(qt_app, facade)
    received: list[tuple[str, str]] = []
    page.analysis_failed.connect(lambda code, msg: received.append((code, msg)))

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert len(received) == 1
    code, message = received[0]
    assert code == "unexpected_error"
    assert "boom internal" not in message
    assert "Traceback" not in message


# -------------------------------------------------------------------- layering


def test_gui_never_imports_analysis_or_provider_internals() -> None:
    gui_directory = SRC_ROOT / "qq_chat_analyzer" / "gui"
    forbidden = (
        "from ..providers",
        "from ..parser",
        "from ..wechat_parser",
        "from ..analyzer",
        "from ..tokenizer",
        "from ..cleaner",
        "import sqlite3",
    )

    for module_path in gui_directory.glob("*.py"):
        source = module_path.read_text(encoding="utf-8")
        if module_path.name == "app.py":
            continue
        for marker in forbidden:
            assert marker not in source, f"{module_path.name} imports {marker}"


def test_gui_pages_do_not_compute_statistics() -> None:
    gui_directory = SRC_ROOT / "qq_chat_analyzer" / "gui"

    for name in ("analysis_page.py", "dashboard_page.py", "main_window.py"):
        source = (gui_directory / name).read_text(encoding="utf-8")
        for marker in ("Counter(", "statistics.", "sum(", "sorted("):
            assert marker not in source, f"{name} computes {marker}"


def test_gui_modules_never_import_providers_or_parsers() -> None:
    gui_directory = SRC_ROOT / "qq_chat_analyzer" / "gui"
    forbidden = (
        "from ..providers",
        "from ..parser",
        "from ..wechat_parser",
        "from ..qq_chat_exporter_adapter",
        "from ..wechat_db_adapter",
        "from ..wechat_cli_adapter",
        "import sqlite3",
    )

    for module_path in gui_directory.glob("*.py"):
        if module_path.name == "app.py":
            continue
        source = module_path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{module_path.name} imports {marker}"


def test_gui_pages_only_import_the_facade_from_application() -> None:
    gui_directory = SRC_ROOT / "qq_chat_analyzer" / "gui"

    for name in (
        "analysis_page.py",
        "dashboard_page.py",
        "main_window.py",
        "wechat_setup_dialog.py",
    ):
        source = (gui_directory / name).read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("from ..application"):
                assert "facade" in stripped, f"{name} imports {stripped}"


# ------------------------------------------------------------- read-only


def test_user_table_is_not_editable(qt_app) -> None:
    from PySide6.QtWidgets import QAbstractItemView

    page = _dashboard_page(qt_app)

    assert (
        page._user_table.editTriggers()
        == QAbstractItemView.EditTrigger.NoEditTriggers
    )


def test_conversation_table_is_not_editable(qt_app) -> None:
    from PySide6.QtWidgets import QAbstractItemView

    page = _dashboard_page(qt_app)

    assert (
        page._conversation_table.editTriggers()
        == QAbstractItemView.EditTrigger.NoEditTriggers
    )


def test_word_list_is_not_editable(qt_app) -> None:
    from PySide6.QtWidgets import QAbstractItemView

    page = _dashboard_page(qt_app)

    assert (
        page._word_list.editTriggers()
        == QAbstractItemView.EditTrigger.NoEditTriggers
    )


def test_report_widgets_stay_read_only_after_rendering(qt_app) -> None:
    from PySide6.QtWidgets import QAbstractItemView

    page = _dashboard_page(qt_app)
    page.render_view(_dashboard_view())

    for widget in (page._user_table, page._conversation_table, page._word_list):
        assert (
            widget.editTriggers()
            == QAbstractItemView.EditTrigger.NoEditTriggers
        )


def test_report_widgets_still_allow_selection(qt_app) -> None:
    from PySide6.QtWidgets import QAbstractItemView

    page = _dashboard_page(qt_app)

    for widget in (page._user_table, page._conversation_table, page._word_list):
        assert (
            widget.selectionMode()
            != QAbstractItemView.SelectionMode.NoSelection
        )


def _page_module():
    return importlib.import_module("qq_chat_analyzer.gui.analysis_page")


def _connected_prefix():
    return _page_module()._CONNECTED_PREFIX


def _disconnected_prefix():
    return _page_module()._DISCONNECTED_PREFIX


def _qq_snapshot(state, message="", action_hint="", version=None):
    """Build one QQ ConnectionSnapshot in a given lifecycle state."""
    connection = importlib.import_module(
        "qq_chat_analyzer.application.connection"
    )
    return connection.ConnectionSnapshot(
        state=connection.ConnectionState(state),
        source="qq",
        message=message,
        action_hint=action_hint,
        version=version,
    )


class _SnapshotFacade(StubFacade):
    """Return one fixed QQ snapshot regardless of the underlying status."""

    def __init__(self, snapshot, **kwargs):
        super().__init__(**kwargs)
        self._snapshot = snapshot

    def set_snapshot(self, snapshot):
        self._snapshot = snapshot

    def _qq_snapshot(self):
        return self._snapshot


class _ConnectWaitingAuthFacade(_SnapshotFacade):
    """Return a fixed status snapshot but a WAITING_AUTH connect result."""

    def __init__(self, status_snapshot, connect_snapshot, **kwargs):
        super().__init__(status_snapshot, **kwargs)
        self._connect_snapshot = connect_snapshot

    def start_qq_auth_flow(self, progress=None):
        self.start_qq_auth_flow_calls.append(1)
        return self._connect_snapshot


class _GatedQRFacade(_ConnectWaitingAuthFacade):
    """Simulate a fresh auth session that gates the QR file until it changes."""

    def __init__(self, status_snapshot, connect_snapshot, **kwargs):
        super().__init__(status_snapshot, connect_snapshot, **kwargs)
        self.qr_ready = False

    def is_qq_qrcode_ready(self):
        return self.qr_ready


def _qq_page_in_state(qt_app, sources, snapshot):
    module = _facade_module()
    facade = _SnapshotFacade(snapshot, sources=sources)
    page = _analysis_page(qt_app, facade)
    _drain(page)
    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)
    return page


def test_disconnected_source_shows_session_placeholder(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("disconnected"),
    )

    assert page._session_list.count() == 1
    item = page._session_list.item(0)
    assert "暂无会话" in item.text()
    assert "连接数据源后，这里会显示聊天记录" in item.text()
    assert not (item.flags() & Qt.ItemFlag.ItemIsSelectable)


def test_connecting_source_shows_loading_placeholder(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("starting"),
    )

    assert page._session_list.count() == 1
    assert "正在连接数据源" in page._session_list.item(0).text()


def test_connected_source_replaces_placeholder_with_sessions(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = _SnapshotFacade(
        _qq_snapshot("connected"),
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "虚构群聊")],
    )
    page = _analysis_page(qt_app, facade)
    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._session_list.count() == 1
    assert page._session_list.item(0).text() == "虚构群聊"


def test_connected_empty_source_shows_real_empty_state(qt_app, sources) -> None:
    facade = _SnapshotFacade(
        _qq_snapshot("connected"),
        sources=sources,
        sessions=[],
    )
    page = _analysis_page(qt_app, facade)
    page.select_source(_facade_module().ChatSource.QQ)
    _drain(page)

    assert page._session_list.count() == 1
    assert "没有找到可分析的聊天记录" in page._session_list.item(0).text()


def test_disconnected_state_invites_the_user_to_connect(
    qt_app,
    sources,
) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("disconnected", message="QQ \u5c1a\u672a\u8fde\u63a5\u3002"),
    )

    assert page._qq_connect_button.isVisibleTo(page) is True
    assert page._qq_connect_button.isEnabled() is True
    assert "\u8fde\u63a5QQ" == page._qq_connect_button.text()
    assert page._session_list.count() == 1
    assert "暂无会话" in page._session_list.item(0).text()


def test_qq_status_text_is_not_duplicated_in_status_bar(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    message = "QQ \u5c1a\u672a\u8fde\u63a5\u3002"
    action_hint = "\u8bf7\u70b9\u51fb\u300c\u8fde\u63a5QQ\u300d\u81ea\u52a8\u5b8c\u6210\u8fde\u63a5\u3002"
    status = _connection_status(
        available=False,
        qce_running=False,
        authenticated=False,
        message=message,
        action_hint=action_hint,
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
    )
    page = _analysis_page(qt_app, facade)
    received: list[str] = []
    page.status_changed.connect(received.append)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert not hasattr(page, "_hint_label")
    assert received == [message]
    assert action_hint not in received


def test_qq_session_count_is_not_duplicated_in_status_bar(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    ready = _connection_status(
        available=True,
        qce_running=True,
        authenticated=True,
        message="QQ \u5df2\u8fde\u63a5\u3002",
        action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=ready,
        sessions=[
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A"),
        ],
    )
    page = _analysis_page(qt_app, facade)
    received: list[str] = []
    page.status_changed.connect(received.append)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert "\u5171 1 \u4e2a\u4f1a\u8bdd\u3002" not in received


def test_starting_state_reports_progress_and_disables_the_button(
    qt_app,
    sources,
) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("starting"),
    )

    assert page._qq_connect_button.isEnabled() is False
    assert "\u542f\u52a8" in page._status_label.text()


def test_initializing_state_reports_progress_and_disables_the_button(
    qt_app,
    sources,
) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("initializing"),
    )

    assert page._qq_connect_button.isEnabled() is False
    assert "\u521d\u59cb\u5316" in page._status_label.text()


def test_waiting_auth_state_asks_the_user_to_log_in(
    qt_app,
    sources,
) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("waiting_auth"),
    )

    text = page._status_label.text()
    assert "\u767b\u5f55" in text
    assert _disconnected_prefix() not in text
    assert page._qq_connect_button.isEnabled() is True


def test_waiting_auth_is_visually_distinct_from_disconnected(
    qt_app,
    sources,
) -> None:
    waiting = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("waiting_auth"),
    )._status_label.text()
    disconnected = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("disconnected"),
    )._status_label.text()

    assert waiting != disconnected


def test_waiting_auth_state_shows_login_guide(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("waiting_auth"),
    )

    assert page._qq_login_guide_label.isVisibleTo(page) is True
    text = page._qq_login_guide_label.text()
    assert "等待QQ登录" in text
    assert "请扫码登录QQ" in text
    assert "QQ主窗口可能不会正常显示" in text
    assert "不要手动启动QQ" not in text
    lowered = text.lower()
    for forbidden in ("QCE", "NapCat", "API", "token", "runtime"):
        assert forbidden.lower() not in lowered


def test_connected_state_hides_login_guide(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("connected"),
    )

    assert page._qq_login_guide_label.isVisibleTo(page) is False
    assert page._qq_login_guide_label.text() == ""


def test_error_state_shows_a_user_safe_message(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("error", message="\u65e0\u6cd5\u8fde\u63a5 QQ\u3002"),
    )

    assert _disconnected_prefix() in page._status_label.text()
    assert "\u65e0\u6cd5\u8fde\u63a5 QQ\u3002" in page._status_label.text()
    assert page._qq_connect_button.isEnabled() is True
    assert page._qq_connect_button.text() == "重新开始"


def test_qq_error_status_label_uses_error_color(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("error", message="无法连接 QQ。"),
    )

    assert "#c2410c" in page._status_label.styleSheet()


def test_qq_connected_status_label_uses_normal_style(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("connected"),
    )

    assert "#c2410c" not in page._status_label.styleSheet()


def test_connected_state_loads_sessions(qt_app, sources) -> None:
    module = _facade_module()
    facade = _SnapshotFacade(
        _qq_snapshot("connected", message="QQ \u5df2\u8fde\u63a5\u3002"),
        sources=sources,
        sessions=[
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A", 12)
        ],
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)
    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert _connected_prefix() in page._status_label.text()
    assert page._qq_connect_button.isVisibleTo(page) is False
    assert "重新连接" not in page._qq_connect_button.text()
    assert page._session_list.count() == 1


def test_every_lifecycle_state_renders_a_message(qt_app, sources) -> None:
    """No state may leave the user staring at an empty status label."""
    for state in (
        "disconnected",
        "initializing",
        "starting",
        "waiting_auth",
        "connected",
        "error",
    ):
        page = _qq_page_in_state(qt_app, sources, _qq_snapshot(state))
        assert page._status_label.text().strip(), state


def test_waiting_auth_state_starts_automatic_refresh(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("waiting_auth"),
    )

    assert page._qq_status_timer.isActive() is True


def _write_qrcode_png(path: Path) -> None:
    from PySide6.QtGui import QPixmap

    pixmap = QPixmap(8, 8)
    pixmap.fill(Qt.GlobalColor.black)
    assert pixmap.save(str(path)) is True


def test_waiting_auth_state_shows_the_qrcode_png(
    qt_app,
    sources,
    tmp_path: Path,
) -> None:
    module = _facade_module()
    qr_path = tmp_path / "qrcode.png"
    _write_qrcode_png(qr_path)
    facade = _SnapshotFacade(_qq_snapshot("waiting_auth"), sources=sources)
    page = _analysis_page(qt_app, facade, qq_qrcode_path=qr_path)
    _drain(page)

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert page._qq_qrcode_label.isVisibleTo(page) is True
    assert page._qq_qrcode_label.pixmap() is not None
    assert page._qq_qrcode_label.pixmap().isNull() is False


def test_waiting_auth_hides_stale_qrcode_until_session_file_is_fresh(
    qt_app,
    sources,
    tmp_path: Path,
) -> None:
    module = _facade_module()
    qr_path = tmp_path / "qrcode.png"
    _write_qrcode_png(qr_path)
    facade = _GatedQRFacade(
        _qq_snapshot("waiting_auth"),
        _qq_snapshot("waiting_auth"),
        sources=sources,
    )
    page = _analysis_page(qt_app, facade, qq_qrcode_path=qr_path)
    _drain(page)

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert page._qq_qrcode_label.isVisibleTo(page) is False

    _write_qrcode_png(qr_path)
    facade.qr_ready = True
    page._poll_qq_status()
    _drain(page)

    assert page._qq_qrcode_label.isVisibleTo(page) is True
    assert page._qq_qrcode_label.pixmap() is not None


def test_waiting_auth_without_qrcode_keeps_it_hidden(
    qt_app,
    sources,
    tmp_path: Path,
) -> None:
    module = _facade_module()
    facade = _SnapshotFacade(_qq_snapshot("waiting_auth"), sources=sources)
    page = _analysis_page(
        qt_app,
        facade,
        qq_qrcode_path=tmp_path / "missing.png",
    )
    _drain(page)

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert page._qq_qrcode_label.isVisibleTo(page) is False


def test_connected_state_hides_the_qrcode(
    qt_app,
    sources,
    tmp_path: Path,
) -> None:
    module = _facade_module()
    qr_path = tmp_path / "qrcode.png"
    _write_qrcode_png(qr_path)
    facade = _SnapshotFacade(_qq_snapshot("connected"), sources=sources)
    page = _analysis_page(qt_app, facade, qq_qrcode_path=qr_path)
    _drain(page)

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert page._qq_qrcode_label.isVisibleTo(page) is False


def test_login_refresh_hides_qrcode_after_connected(
    qt_app,
    sources,
    tmp_path: Path,
) -> None:
    module = _facade_module()
    qr_path = tmp_path / "qrcode.png"
    _write_qrcode_png(qr_path)
    facade = _SnapshotFacade(_qq_snapshot("waiting_auth"), sources=sources)
    page = _analysis_page(qt_app, facade, qq_qrcode_path=qr_path)
    _drain(page)

    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert page._qq_qrcode_label.isVisibleTo(page) is True
    assert page._qq_login_guide_label.isVisibleTo(page) is True

    facade.set_snapshot(
        _qq_snapshot("connected", message="QQ \u5df2\u8fde\u63a5\u3002")
    )
    page._poll_qq_status()

    assert page._qq_qrcode_label.isVisibleTo(page) is False
    assert page._qq_login_guide_label.isVisibleTo(page) is False


def test_connected_state_stops_automatic_refresh(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("connected"),
    )

    assert page._qq_status_timer.isActive() is False


def test_disconnected_state_does_not_start_automatic_refresh(
    qt_app,
    sources,
) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("disconnected"),
    )

    assert page._qq_status_timer.isActive() is False


def test_switching_away_from_qq_stops_automatic_refresh(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("waiting_auth"),
    )

    assert page._qq_status_timer.isActive() is True

    page.select_source(module.ChatSource.LOCAL_FILE)

    assert page._qq_status_timer.isActive() is False


def test_automatic_refresh_detects_login_and_loads_sessions(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = _SnapshotFacade(
        _qq_snapshot("waiting_auth"),
        sources=sources,
        sessions=[
            _session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4 A", 12)
        ],
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)
    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert page._qq_status_timer.isActive() is True
    assert page._session_list.count() == 1
    assert "正在连接数据源" in page._session_list.item(0).text()

    facade.set_snapshot(
        _qq_snapshot("connected", message="QQ \u5df2\u8fde\u63a5\u3002")
    )
    page._poll_qq_status()

    assert page._qq_status_timer.isActive() is False
    assert _connected_prefix() in page._status_label.text()
    assert page._session_list.count() == 1


def test_connect_result_waiting_auth_starts_automatic_refresh(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = _ConnectWaitingAuthFacade(
        _qq_snapshot("disconnected"),
        _qq_snapshot("waiting_auth"),
        sources=sources,
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)
    page._source_buttons[module.ChatSource.QQ].click()
    _drain(page)

    assert page._qq_status_timer.isActive() is False

    page._qq_connect_button.click()
    QTest.qWait(600)

    assert facade.start_qq_auth_flow_calls == [1]
    assert page._qq_status_timer.isActive() is True
    assert "\u767b\u5f55" in page._status_label.text()


def test_switching_sources_clears_previous_sessions_and_status(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[_session(module.ChatSource.QQ, "10001", "QQ 虚构群")],
    )
    page = _analysis_page(qt_app, facade)
    page.show()

    page.select_source(module.ChatSource.QQ)
    _drain(page)
    assert page._session_list.item(0).text() == "QQ 虚构群"

    facade._sessions = []
    facade._connection_status = _wechat_connection_status(
        available=False,
        data_found=False,
        db_key_available=False,
        runtime_available=False,
        message="微信尚未连接",
        action_hint="请开始微信连接流程。",
    )
    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert page._selected_source is module.ChatSource.WECHAT
    assert page._sessions == []
    assert "QQ 虚构群" not in page._session_list.item(0).text()
    assert "QQ" not in page._status_label.text()
    assert page._session_search.text() == ""

    facade._sessions = [_session(module.ChatSource.QQ, "10002", "新 QQ 会话")]
    facade._connection_status = _connection_status(
        available=True,
        qce_running=True,
        authenticated=True,
        message="QQ 已连接。",
        action_hint="",
    )
    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert page._selected_source is module.ChatSource.QQ
    assert page._session_list.item(0).text() == "新 QQ 会话"
    assert "微信" not in page._status_label.text()


def test_non_ready_source_never_shows_cached_real_sessions(qt_app, sources) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources))
    page._selected_source = module.ChatSource.QQ
    page._populate_sessions([_session(module.ChatSource.QQ, "10001", "旧会话")])

    page._show_qq_status(_qq_snapshot("starting"), True)

    assert page._session_list.count() == 1
    assert page._session_list.item(0).text() == "正在连接数据源..."
    assert "旧会话" not in page._session_list.item(0).text()


@pytest.mark.parametrize("source", ["qq", "wechat"])
def test_non_ready_sources_hide_the_entire_session_container(
    qt_app,
    source: str,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=(
            _connection_status(
                available=False,
                qce_running=False,
                authenticated=False,
                message="QQ 未连接。",
                action_hint="请开始连接。",
            )
            if source == "qq"
            else _wechat_connection_status(
                available=False,
                data_found=False,
                db_key_available=False,
                runtime_available=False,
                message="微信未连接。",
                action_hint="请开始连接。",
            )
        ),
    )
    page = _analysis_page(qt_app, facade)
    page.show()

    page.select_source(module.ChatSource(source))
    _drain(page)

    assert page._session_box.isVisibleTo(page) is False


@pytest.mark.parametrize("source", ["qq", "wechat"])
def test_ready_sources_show_session_container_after_real_sessions_load(
    qt_app,
    source: str,
) -> None:
    module = _facade_module()
    selected = module.ChatSource(source)
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[_session(selected, "fictional-session", "虚构会话")],
        connection_status=(
            _connection_status(
                available=True,
                qce_running=True,
                authenticated=True,
                message="QQ 已连接。",
                action_hint="",
            )
            if source == "qq"
            else _wechat_connection_status(
                available=True,
                data_found=True,
                db_key_available=True,
                runtime_available=True,
                message="微信已连接。",
                action_hint="",
            )
        ),
    )
    page = _analysis_page(qt_app, facade)
    page.show()

    page.select_source(selected)
    _drain(page)

    assert page._session_box.isVisibleTo(page) is True
    assert page._session_list.item(0).text() == "虚构会话"


def test_return_to_source_selection_clears_connection_view(qt_app, sources) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "虚构群")],
    )
    page = _analysis_page(qt_app, facade)
    page.show()
    page.select_source(module.ChatSource.QQ)
    _drain(page)

    page._return_source_button.click()

    assert page._selected_source is None
    assert all(not button.isChecked() for button in page._source_buttons.values())
    assert page._status_label.text() == ""
    assert page._status_label.isVisibleTo(page) is False
    assert page._qq_connect_button.isVisibleTo(page) is False
    assert page._wechat_connect_button.isVisibleTo(page) is False
    assert page._session_list.item(0).text() == (
        "暂无会话\n连接数据源后，这里会显示聊天记录"
    )
    assert page._source_buttons[module.ChatSource.WECHAT].isEnabled() is False


def test_return_to_source_selection_cancels_without_stopping_qq(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    facade = StubFacade(sources=sources)
    page = _analysis_page(qt_app, facade, executor=executor)
    page._selected_source = module.ChatSource.QQ
    page.connect_qq()

    page.return_to_source_selection()

    executor.progress("正在加载 QQ...")
    executor.succeed(facade._qq_snapshot())
    QTest.qWait(600)

    assert executor.cancelled is True
    assert facade.shutdown_qq_runtime_calls == []
    assert page._selected_source is None
    assert page._status_label.text() == ""


def test_qq_connect_shows_first_run_permission_hint(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    executor = _DeferredExecutor()
    page = _analysis_page(qt_app, StubFacade(sources=sources), executor=executor)
    page._selected_source = module.ChatSource.QQ

    page.connect_qq()

    text = page._qq_login_guide_label.text()
    assert page._qq_login_guide_label.isVisibleTo(page) is True
    assert "权限确认窗口" in text
    assert "内置的 QQ 数据读取组件" in text
    assert "请允许它运行" in text
    assert "仅在本机处理" not in text


def test_wechat_guide_image_load_failure_is_safe(qt_app, tmp_path: Path) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=_wechat_connection_status(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message="微信尚未连接",
            action_hint="请开始微信连接流程。",
        ),
    )
    page = _analysis_page(
        qt_app,
        facade,
        wechat_guide_image_path=tmp_path / "missing.png",
    )
    page.show()

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert page._wechat_guide_image_label.isVisibleTo(page) is False
    assert "请进入微信，余音会捕捉登录这一刻的“声音”" in (
        page._wechat_guide_key_label.text()
    )


def test_wechat_waiting_page_shows_bundled_guide_image(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=_wechat_connection_status(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message="微信尚未连接",
            action_hint="请开始微信连接流程。",
        ),
    )
    page = _analysis_page(
        qt_app,
        facade,
        wechat_guide_image_path=PROJECT_ROOT / "wechat_login_guide.png",
    )
    page.show()

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert page._wechat_guide_image_label.isVisibleTo(page) is True
    assert page._wechat_guide_image_label.pixmap().isNull() is False

def test_wechat_guide_text_has_no_html_tags(qt_app) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=_wechat_connection_status(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message="微信尚未连接",
            action_hint="请开始微信连接流程。",
        ),
    )
    page = _analysis_page(qt_app, facade)
    page.show()

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    texts = [
        page._wechat_guide_label.text(),
        page._wechat_guide_key_label.text(),
        page._wechat_guide_note_label.text(),
    ]
    for text in texts:
        assert "<br" not in text
        assert "<span" not in text
        assert ">" not in text
    assert "正在准备微信连接" in texts[0]
    assert "等待微信登录" in texts[2]
    assert (
        "请进入微信，余音会捕捉登录这一刻的“声音”"
        in texts[1]
    )
    assert "\u4e0d\u4e0a\u4f20" in texts[2]


def test_wechat_guide_uses_horizontal_layout(qt_app) -> None:
    from PySide6.QtWidgets import QHBoxLayout

    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=_wechat_connection_status(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message="微信尚未连接",
            action_hint="请开始微信连接流程。",
        ),
    )
    page = _analysis_page(
        qt_app,
        facade,
        wechat_guide_image_path=PROJECT_ROOT / "wechat_login_guide.png",
    )
    page.show()
    page.resize(900, 700)

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    assert isinstance(page._wechat_guide_row, QHBoxLayout)
    assert page._wechat_guide_row.indexOf(page._wechat_guide_image_label) >= 0
    image_left = page._wechat_guide_image_label.x()
    guide_left = page._wechat_guide_label.x()
    assert image_left < guide_left
    assert page._wechat_guide_image_label.width() <= 160
    assert (
        page._wechat_guide_label.width()
        > page._wechat_guide_image_label.width()
    )


def test_wechat_guide_image_keeps_aspect_ratio(qt_app) -> None:
    from PySide6.QtGui import QPixmap

    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        connection_status=_wechat_connection_status(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message="微信尚未连接",
            action_hint="请开始微信连接流程。",
        ),
    )
    page = _analysis_page(
        qt_app,
        facade,
        wechat_guide_image_path=PROJECT_ROOT / "wechat_login_guide.png",
    )
    page.show()

    page.select_source(module.ChatSource.WECHAT)
    _drain(page)

    pixmap = page._wechat_guide_image_label.pixmap()
    assert pixmap is not None
    assert pixmap.isNull() is False
    width = pixmap.width()
    height = pixmap.height()
    assert width > 0 and height > 0
    original = QPixmap(str(PROJECT_ROOT / "wechat_login_guide.png"))
    original_ratio = original.width() / original.height()
    scaled_ratio = width / height
    assert abs(original_ratio - scaled_ratio) < 0.01




def test_connection_failure_offers_restart_instead_of_reconnect(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    page = _analysis_page(qt_app, StubFacade(sources=sources))
    page._selected_source = module.ChatSource.QQ

    page._handle_qq_connect_error("qq_connect_failed", "请检查后重试。")

    assert page._qq_connect_button.text() == "重新开始"
    assert "重新连接" not in page._qq_connect_button.text()


def test_ready_sources_hide_reconnect_actions(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("connected"),
    )

    assert page._qq_connect_button.isVisibleTo(page) is False
    assert "重新连接" not in page._qq_connect_button.text()
    assert page._return_source_button.isVisibleTo(page) is True


def test_ready_session_search_remains_available_when_no_name_matches(
    qt_app,
) -> None:
    module = _facade_module()
    page = _analysis_page(
        qt_app,
        StubFacade(
            sources=_wechat_available_sources(),
            sessions=[_session(module.ChatSource.WECHAT, "room-1", "Alice")],
        ),
    )
    page.select_source(module.ChatSource.WECHAT)

    page._session_search.setText("missing")

    assert page._session_search.isEnabled() is True
    assert "没有匹配的会话" in page._session_list.item(0).text()

# ---------------------------------------------------------------- GUI-2: Home + Navigation

def test_main_window_starts_at_home_page(qt_app, sources) -> None:
    """MainWindow starts with HomePage visible."""
    from qq_chat_analyzer.gui.main_window import HOME_PAGE_INDEX
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    assert window.stack.currentIndex() == HOME_PAGE_INDEX
    # home_page is the current (top) page in the stack


def test_home_page_has_three_entry_buttons(qt_app, sources) -> None:
    """HomePage has QQ, WeChat, and local data buttons."""
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    page = window.home_page
    from PySide6.QtWidgets import QPushButton
    buttons = page.findChildren(QPushButton)
    labels = {b.text() for b in buttons}
    assert "QQ" in labels
    assert "\u5fae\u4fe1" in labels
    assert "\u672c\u5730\u6570\u636e" in labels


def test_click_qq_navigates_to_analysis_page_with_qq_source(qt_app, sources) -> None:
    """Clicking QQ on HomePage navigates to AnalysisPage with QQ preselected."""
    from qq_chat_analyzer.gui.main_window import ANALYSIS_PAGE_INDEX
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.navigate_to_qq()
    _drain(window)
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
def test_click_wechat_navigates_to_analysis_page_with_wechat_source(qt_app, sources) -> None:
    """Clicking WeChat on HomePage navigates to AnalysisPage with WeChat preselected."""
    from qq_chat_analyzer.gui.main_window import ANALYSIS_PAGE_INDEX
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.navigate_to_wechat()
    _drain(window)
    from qq_chat_analyzer.gui.main_window import WECHAT_WORKSPACE_INDEX
    assert window.stack.currentIndex() == WECHAT_WORKSPACE_INDEX
    from qq_chat_analyzer.gui.main_window import WECHAT_WORKSPACE_INDEX
    assert window.stack.currentIndex() == WECHAT_WORKSPACE_INDEX
    """Clicking local data on HomePage navigates to LocalDataPage."""
    from qq_chat_analyzer.gui.main_window import LOCAL_DATA_PAGE_INDEX
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)
    assert window.stack.currentIndex() == LOCAL_DATA_PAGE_INDEX
    # local_data_page is the current (top) page in the stack


def test_local_data_page_has_back_to_home_button(qt_app, sources) -> None:
    """LocalDataPage has a button that returns to HomePage."""
    from qq_chat_analyzer.gui.main_window import HOME_PAGE_INDEX
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)
    window.local_data_page._back_button.click()
    _drain(window)
    assert window.stack.currentIndex() == HOME_PAGE_INDEX


def test_analysis_page_can_return_to_home_from_home_button(qt_app, sources) -> None:
    """The home button in the header returns to HomePage from AnalysisPage."""
    from qq_chat_analyzer.gui.main_window import HOME_PAGE_INDEX
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.show_analysis_page()
    _drain(window)
    window.show()
    _drain(window)
    assert window._home_button.isVisible() is True
    window._home_button.click()
    _drain(window)
    assert window.stack.currentIndex() == HOME_PAGE_INDEX



def test_home_button_hidden_on_home_page(qt_app, sources) -> None:
    """Home button is hidden when on HomePage."""
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    assert window._home_button.isVisible() is False


def test_page_switch_does_not_change_window_size_with_home_page(qt_app, sources) -> None:
    """Switching pages does not resize the window (incl. HomePage)."""
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.show()
    window.resize(960, 720)
    initial = window.size()
    window.show_analysis_page()
    _drain(window)
    assert window.size() == initial
    window.show_local_data_page()
    _drain(window)
    assert window.size() == initial
    window.show_home_page()
    _drain(window)
    assert window.size() == initial


def test_processing_page_still_works_after_navigation_change(qt_app, sources) -> None:
    """Start analysis still switches to ProcessingPage."""
    from qq_chat_analyzer.gui.main_window import PROCESSING_PAGE_INDEX
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "虚构群")],
        qq_setup_status=_qq_setup_status(configured=True, runtime_available=True),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    page = window.analysis_page
    page._selected_source = module.ChatSource.QQ
    page._populate_sessions(facade._sessions)
    page._session_list.setCurrentRow(0)
    page.start_analysis()
    _drain(page)
    assert window.stack.currentIndex() == PROCESSING_PAGE_INDEX


def test_dashboard_page_remains_available_outside_success_path(qt_app, sources) -> None:
    """DashboardPage stays instantiable but is no longer the success page."""
    from qq_chat_analyzer.gui.main_window import (
        ANALYSIS_PAGE_INDEX,
        DASHBOARD_PAGE_INDEX,
    )
    module = _facade_module()
    view = _dashboard_view()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "虚构群")],
        outcome=_StubOutcome(view),
        qq_setup_status=_qq_setup_status(configured=True, runtime_available=True),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    window = _main_window(qt_app, facade)
    window.analysis_page.select_source(module.ChatSource.QQ)
    _drain(window.analysis_page)
    window.analysis_page._session_list.setCurrentRow(0)
    window.analysis_page.start_analysis()
    _drain(window.analysis_page)
    assert window.stack.currentIndex() == ANALYSIS_PAGE_INDEX
    assert window.stack.currentIndex() != DASHBOARD_PAGE_INDEX
    assert window.dashboard_page is not None

# ----------------------------------------------------------------

# ----------------------------------------------------------------
# GUI-3 stabilization: restore GUI-2 workspace behavior equivalence
# ----------------------------------------------------------------

def test_qq_workspace_uses_snapshot_facade_api(qt_app, sources) -> None:
    """QQ status flows through facade.get_qq_connection_snapshot()."""
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    module = _facade_module()
    status = module.QQConnectionStatus(
        available=False, qce_running=False, authenticated=False,
        version="", message="QQ 尚未连接。", action_hint="",
    )
    facade = StubFacade(sources=sources, connection_status=status)
    window = _main_window(qt_app, facade)
    window.navigate_to_qq()
    _drain(window)

    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
    assert facade.get_qq_connection_snapshot_calls
    assert facade.get_connection_status_calls == []
    assert "QQ" in window.qq_workspace._status_label.text()
    assert window.qq_workspace._qq_connect_button.isVisibleTo(window) is True
    assert window.qq_workspace.session_panel._sessions_ready is False


def test_wechat_workspace_uses_connection_status_facade_api(
    qt_app, sources
) -> None:
    """WeChat status flows through facade.get_connection_status(WECHAT)."""
    from qq_chat_analyzer.gui.main_window import WECHAT_WORKSPACE_INDEX
    module = _facade_module()
    status = module.WeChatConnectionStatus(
        available=False, data_found=False, db_key_available=False,
        runtime_available=False, message="微信尚未连接。", action_hint="",
    )
    facade = StubFacade(sources=sources, connection_status=status)
    window = _main_window(qt_app, facade)
    window.navigate_to_wechat()
    _drain(window)

    assert window.stack.currentIndex() == WECHAT_WORKSPACE_INDEX
    assert facade.get_connection_status_calls == [module.ChatSource.WECHAT]
    assert "微信" in window.wechat_workspace._status_label.text()
    assert window.wechat_workspace._wechat_connect_button.isVisibleTo(window) is True
    assert window.wechat_workspace.session_panel._sessions_ready is False


def test_qq_workspace_shows_connect_button_when_disconnected(
    qt_app, sources
) -> None:
    """QQ disconnected status shows the connect action and no sessions."""
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    module = _facade_module()
    status = module.QQConnectionStatus(
        available=False, qce_running=False, authenticated=False,
        version="", message="QQ 服务未运行。", action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        sessions=[_session(module.ChatSource.QQ, "10001", "虚构群")],
    )
    window = _main_window(qt_app, facade)
    window.navigate_to_qq()
    _drain(window)

    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
    assert window.qq_workspace._qq_connect_button.isVisibleTo(window) is True
    assert window.qq_workspace._qq_connect_button.isEnabled()
    assert window.qq_workspace.session_panel._sessions_ready is False


def test_wechat_workspace_shows_connect_button_when_disconnected(
    qt_app, sources
) -> None:
    """WeChat disconnected status shows the connect action and no sessions."""
    from qq_chat_analyzer.gui.main_window import WECHAT_WORKSPACE_INDEX
    module = _facade_module()
    status = module.WeChatConnectionStatus(
        available=False, data_found=False, db_key_available=False,
        runtime_available=False, message="微信环境未配置。", action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        sessions=[_session(module.ChatSource.WECHAT, "20001", "测试群")],
    )
    window = _main_window(qt_app, facade)
    window.navigate_to_wechat()
    _drain(window)

    assert window.stack.currentIndex() == WECHAT_WORKSPACE_INDEX
    assert window.wechat_workspace._wechat_connect_button.isVisibleTo(window) is True
    assert window.wechat_workspace._wechat_connect_button.isEnabled()
    assert window.wechat_workspace.session_panel._sessions_ready is False


def test_qq_workspace_disconnect_returns_to_disconnected(
    qt_app, sources
) -> None:
    """Connected QQ workspace offers logout and returns to disconnected."""
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    module = _facade_module()
    connected = module.QQConnectionStatus(
        available=True,
        qce_running=True,
        authenticated=True,
        version="4.1.0",
        message="QQ 已连接。",
        action_hint="",
    )
    facade = StubFacade(sources=sources, connection_status=connected)
    window = _main_window(qt_app, facade)
    window.navigate_to_qq()
    _drain(window)

    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
    assert window.qq_workspace._qq_disconnect_button.isVisibleTo(window) is True
    assert window.qq_workspace._qq_connect_button.isVisibleTo(window) is False

    window.qq_workspace._qq_disconnect_button.click()
    _drain(window)

    assert facade.disconnect_qq_calls == [1]
    assert window.qq_workspace._qq_connect_button.isVisibleTo(window) is True
    assert window.qq_workspace._qq_disconnect_button.isVisibleTo(window) is False


def test_wechat_workspace_disconnect_returns_to_disconnected(
    qt_app, sources
) -> None:
    """Connected WeChat workspace offers logout and returns to disconnected."""
    from qq_chat_analyzer.gui.main_window import WECHAT_WORKSPACE_INDEX
    module = _facade_module()
    connected = module.WeChatConnectionStatus(
        available=True,
        data_found=True,
        db_key_available=True,
        runtime_available=True,
        message="微信已连接。",
        action_hint="",
    )
    facade = StubFacade(sources=sources, connection_status=connected)
    window = _main_window(qt_app, facade)
    window.navigate_to_wechat()
    _drain(window)

    assert window.stack.currentIndex() == WECHAT_WORKSPACE_INDEX
    assert window.wechat_workspace._wechat_disconnect_button.isVisibleTo(window) is True
    assert window.wechat_workspace._wechat_connect_button.isVisibleTo(window) is False

    window.wechat_workspace._wechat_disconnect_button.click()
    _drain(window)

    assert facade.disconnect_wechat_calls == [1]
    assert window.wechat_workspace._wechat_connect_button.isVisibleTo(window) is True
    assert window.wechat_workspace._wechat_disconnect_button.isVisibleTo(window) is False


def test_qq_connection_does_not_crash_without_explicit_executor(
    qt_app, sources
) -> None:
    """QQ connect works when MainWindow was created without an executor."""
    module = _facade_module()
    status = module.QQConnectionStatus(
        available=False, qce_running=False, authenticated=False,
        version="", message="QQ 尚未连接。", action_hint="",
    )
    facade = StubFacade(sources=sources, connection_status=status)
    window = _main_window_no_executor(qt_app, facade)
    window.navigate_to_qq()
    _drain(window)

    window.qq_workspace._qq_connect_button.click()
    _drain(window)

    assert window.qq_workspace._connection_task is not None


def test_wechat_connection_does_not_crash_without_explicit_executor(
    qt_app, sources
) -> None:
    """WeChat connect opens setup when MainWindow has no executor."""
    module = _facade_module()
    status = module.WeChatConnectionStatus(
        available=False, data_found=False, db_key_available=False,
        runtime_available=False, message="微信尚未连接。", action_hint="",
    )
    facade = StubFacade(sources=sources, connection_status=status)
    window = _main_window_no_executor(qt_app, facade)
    window.navigate_to_wechat()
    _drain(window)

    window.wechat_workspace._wechat_connect_button.click()
    _drain(window)

    assert hasattr(window.wechat_workspace, "_wechat_setup_dialog")


def test_session_panel_populates_sessions_without_crash(qt_app, sources) -> None:
    """The shared panel renders sessions and becomes ready."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    facade = StubFacade(sources=sources)
    panel = SessionAnalysisPanel()
    panel.configure(facade, module.ChatSource.WECHAT)
    sessions = [
        _session(module.ChatSource.WECHAT, "wx1", "测试会话1", 10),
        _session(module.ChatSource.WECHAT, "wx2", "测试会话2", 5),
    ]
    panel.populate_sessions(sessions)

    assert panel._session_list.count() == 2
    assert panel._sessions_ready is True


def test_session_panel_empty_source_shows_real_empty_state(
    qt_app, sources
) -> None:
    """An empty session list renders a non-interactive empty state."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    panel = SessionAnalysisPanel()
    panel.configure(StubFacade(sources=sources), module.ChatSource.WECHAT)

    panel.populate_sessions([])

    assert panel._sessions_ready is True
    assert panel._session_list.count() == 1
    assert "没有找到" in panel._session_list.item(0).text()
    assert panel._analyze_button.isEnabled() is False


def test_session_panel_disables_sessions_without_messages(
    qt_app, sources
) -> None:
    """Sessions without analyzable messages stay disabled."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    sessions = [
        module.SessionInfo(
            source=module.ChatSource.WECHAT,
            session_id="wx1",
            display_name="有消息",
            message_count=5,
        ),
        module.SessionInfo(
            source=module.ChatSource.WECHAT,
            session_id="wx2",
            display_name="无消息",
            message_count=0,
            message_available=False,
            unavailable_reason="该会话没有可分析消息",
        ),
    ]
    panel = SessionAnalysisPanel()
    panel.configure(StubFacade(sources=sources), module.ChatSource.WECHAT)
    panel.populate_sessions(sessions)

    panel._session_list.setCurrentRow(1)
    assert panel._analyze_button.isEnabled() is False
    panel._session_list.setCurrentRow(0)
    assert panel._analyze_button.isEnabled() is True


def test_session_panel_selection_requests_message_range(qt_app, sources) -> None:
    """Selecting a session fetches its real message range through the facade."""
    from datetime import datetime

    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    session_id = "wx_time_range"
    start = 1704067200
    end = 1704153600
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.WECHAT, session_id, "测试会话", 10)],
        message_range=(start, end),
    )
    panel = SessionAnalysisPanel()
    panel.configure(facade, module.ChatSource.WECHAT, executor=_inline_executor())
    panel.populate_sessions(facade._sessions)
    panel._session_list.setCurrentRow(0)
    _drain(panel)
    panel._scope_custom.setChecked(True)

    assert facade.get_session_message_range_calls == [
        (module.ChatSource.WECHAT, session_id)
    ]
    assert panel._start_date.date().toPython() == datetime.fromtimestamp(
        start
    ).date()
    assert panel._end_date.date().toPython() == datetime.fromtimestamp(end).date()


def test_qq_workspace_full_chain_connect_sessions_analyze(
    qt_app, sources, tmp_path
) -> None:
    """QQ workspace keeps the GUI-2 connect -> sessions -> analyze chain."""
    from qq_chat_analyzer.gui.main_window import (
        DASHBOARD_PAGE_INDEX,
        PROCESSING_PAGE_INDEX,
        QQ_WORKSPACE_INDEX,
    )
    module = _facade_module()
    qq_module = importlib.import_module("qq_chat_analyzer.gui.qq_workspace")
    qq_module._QQ_CONNECT_MIN_DISPLAY_MS = 0
    disconnected = module.QQConnectionStatus(
        available=False, qce_running=False, authenticated=False,
        version="", message="QQ 尚未连接。", action_hint="",
    )
    connected = module.QQConnectionStatus(
        available=True, qce_running=True, authenticated=True,
        version="4.1.0", message="已连接", action_hint="",
    )
    report_path = tmp_path / "echo-qq.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened: list[Path] = []
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "q1", "QQ群1", 100)],
        outcome=_StubOutcome(_dashboard_view(), report_path=report_path),
        connection_status=disconnected,
        connection_status_after_connect=connected,
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window._report_opener = lambda path: opened.append(path) or True
    window.navigate_to_qq()
    _drain(window)

    # status -> disconnected
    assert executor.operation is not None
    executor.operation()
    executor.succeed(facade.get_qq_connection_snapshot())
    assert window.qq_workspace._qq_connect_button.isVisibleTo(window) is True
    assert window.qq_workspace.session_panel._sessions_ready is False

    # connect/auth operation with progress
    window.qq_workspace._qq_connect_button.click()
    executor.on_progress("等待QQ登录")
    assert window.qq_workspace._qq_login_guide_label.isVisibleTo(window) is True
    executor.operation(lambda _message: None)
    assert facade.start_qq_auth_flow_calls
    executor.succeed(facade.get_qq_connection_snapshot())
    _drain(window)

    # connected -> list_sessions(QQ)
    executor.operation()
    executor.succeed(facade._sessions)
    assert facade.list_sessions_calls == [module.ChatSource.QQ]
    assert window.qq_workspace.session_panel._sessions_ready is True
    assert window.qq_workspace.session_panel._session_list.count() == 1

    # select session + custom scope -> analyze_session -> processing -> dashboard
    window.qq_workspace.session_panel._session_list.setCurrentRow(0)
    window.qq_workspace.session_panel._scope_custom.setChecked(True)
    window.qq_workspace.session_panel._start_date.setDate(QDate(2024, 1, 1))
    window.qq_workspace.session_panel._end_date.setDate(QDate(2024, 12, 31))
    window.qq_workspace.session_panel.start_analysis()
    _drain(window.qq_workspace.session_panel)
    assert window.stack.currentIndex() == PROCESSING_PAGE_INDEX

    executor.operation(lambda _message: None)
    assert facade.analyze_session_calls
    source, session_id, config = facade.analyze_session_calls[0]
    assert source == module.ChatSource.QQ
    assert session_id == "q1"
    assert config.scope_mode is module.AnalysisScopeMode.CUSTOM
    assert config.start_time == "2024-01-01"
    assert config.end_time == "2024-12-31"
    executor.succeed(_StubOutcome(_dashboard_view(), report_path=report_path))
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
    assert window.stack.currentIndex() != DASHBOARD_PAGE_INDEX
    assert opened == [report_path.resolve()]
    assert window._open_echo_button.isVisibleTo(window)


def test_wechat_workspace_full_chain_connect_sessions_analyze(
    qt_app, sources, tmp_path
) -> None:
    """WeChat workspace keeps the GUI-2 connect -> sessions -> analyze chain."""
    from qq_chat_analyzer.gui.main_window import (
        DASHBOARD_PAGE_INDEX,
        PROCESSING_PAGE_INDEX,
        WECHAT_WORKSPACE_INDEX,
    )
    module = _facade_module()
    disconnected = module.WeChatConnectionStatus(
        available=False, data_found=True, db_key_available=False,
        runtime_available=True, message="等待微信登录", action_hint="",
    )
    connected = module.WeChatConnectionStatus(
        available=True, data_found=True, db_key_available=True,
        runtime_available=True, message="微信已连接", action_hint="",
    )
    report_path = tmp_path / "echo-wechat.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened: list[Path] = []
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.WECHAT, "wx1", "测试会话1", 10)],
        outcome=_StubOutcome(_dashboard_view(), report_path=report_path),
        connection_status=disconnected,
        connection_status_after_connect=connected,
        data_roots=["D:/fictional_wechat"],
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window._report_opener = lambda path: opened.append(path) or True
    window.navigate_to_wechat()
    _drain(window)

    # status -> disconnected
    executor.operation()
    executor.succeed(disconnected)
    assert window.wechat_workspace._wechat_connect_button.isVisibleTo(window) is True
    assert window.wechat_workspace.session_panel._sessions_ready is False

    # one-click connect: detect root -> save environment + key -> connected
    window.wechat_workspace._wechat_connect_button.click()
    assert facade.detect_wechat_data_roots_calls
    executor.on_progress("等待微信登录")
    assert "等待微信登录" in window.wechat_workspace._status_label.text()
    executor.operation(lambda _message: None)
    assert facade.setup_wechat_environment_calls
    assert facade.acquire_wechat_db_key_calls
    executor.succeed(connected)
    _drain(window)

    # connected -> list_sessions(WECHAT)
    executor.operation()
    executor.succeed(facade._sessions)
    assert facade.list_sessions_calls == [module.ChatSource.WECHAT]
    assert window.wechat_workspace.session_panel._sessions_ready is True
    assert window.wechat_workspace.session_panel._session_list.count() == 1

    # select session + analyze -> processing -> dashboard
    window.wechat_workspace.session_panel._session_list.setCurrentRow(0)
    window.wechat_workspace.session_panel.start_analysis()
    _drain(window.wechat_workspace.session_panel)
    assert window.stack.currentIndex() == PROCESSING_PAGE_INDEX

    executor.operation(lambda _message: None)
    assert facade.analyze_session_calls
    source, session_id, config = facade.analyze_session_calls[0]
    assert source == module.ChatSource.WECHAT
    assert session_id == "wx1"
    assert config.scope_mode is module.AnalysisScopeMode.ALL
    executor.succeed(_StubOutcome(_dashboard_view(), report_path=report_path))
    assert window.stack.currentIndex() == WECHAT_WORKSPACE_INDEX
    assert window.stack.currentIndex() != DASHBOARD_PAGE_INDEX
    assert opened == [report_path.resolve()]
    assert window._open_echo_button.isVisibleTo(window)


def test_workspace_analysis_failure_returns_to_workspace(
    qt_app, sources, monkeypatch
) -> None:
    """A failed workspace analysis returns to its workspace, not the legacy page."""
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    main_window_module = importlib.import_module(
        "qq_chat_analyzer.gui.main_window"
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "warning", lambda *args: None
    )
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "q1", "QQ群1", 100)],
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window._report_opener = lambda path: opened.append(path) or True
    window.navigate_to_qq()
    _drain(window)
    executor.operation()
    executor.succeed(facade.get_qq_connection_snapshot())
    executor.operation()
    executor.succeed(facade._sessions)

    window.qq_workspace.session_panel._session_list.setCurrentRow(0)
    window.qq_workspace.session_panel.start_analysis()
    _drain(window.qq_workspace.session_panel)
    executor.operation(lambda _message: None)
    executor.fail("fictional_failure", "虚构分析失败")

    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
    assert "虚构分析失败" in window.analysis_page._status_label.text()


def test_workspace_cancel_analysis_returns_to_workspace(
    qt_app, sources
) -> None:
    """Cancelling workspace analysis returns to the same workspace."""
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "q1", "QQ群1", 100)],
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window._report_opener = lambda path: opened.append(path) or True
    window.navigate_to_qq()
    _drain(window)
    executor.operation()
    executor.succeed(facade.get_qq_connection_snapshot())
    executor.operation()
    executor.succeed(facade._sessions)

    window.qq_workspace.session_panel._session_list.setCurrentRow(0)
    window.qq_workspace.session_panel.start_analysis()
    _drain(window.qq_workspace.session_panel)
    assert executor.cancelled is False

    window._cancel_analysis_button.click()

    assert executor.cancelled is True
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
    assert window.qq_workspace.session_panel._analysis_running is False

# ----------------------------------------------------------------
# GUI-5: WeChat data path auto-detection on workspace entry
# ----------------------------------------------------------------

def test_wechat_workspace_auto_detects_single_root_when_not_configured(
    qt_app, sources
) -> None:
    """No saved path and one candidate: auto-use it and continue connecting."""
    module = _facade_module()
    missing = module.WeChatConnectionStatus(
        available=False, data_found=False, db_key_available=False,
        runtime_available=False, message="未找到微信数据位置。", action_hint="",
    )
    connected = module.WeChatConnectionStatus(
        available=True, data_found=True, db_key_available=True,
        runtime_available=True, message="微信已连接", action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=missing,
        connection_status_after_connect=connected,
        sessions=[_session(module.ChatSource.WECHAT, "wx1", "测试会话1", 10)],
        data_roots=["D:/fictional_wechat"],
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window.navigate_to_wechat()
    _drain(window)

    assert facade.detect_wechat_data_roots_calls == []
    executor.operation()
    executor.succeed(missing)

    # Auto-detection ran and submitted the one-click connect operation.
    assert facade.detect_wechat_data_roots_calls
    assert executor.operation is not None
    executor.operation(lambda _message: None)
    assert facade.setup_wechat_environment_calls
    assert facade.acquire_wechat_db_key_calls
    executor.succeed(connected)
    _drain(window)

    executor.operation()
    executor.succeed(facade._sessions)
    assert window.wechat_workspace.session_panel._sessions_ready is True
    assert window.wechat_workspace.session_panel._session_list.count() == 1


def test_wechat_workspace_auto_detection_keeps_saved_path_flow_when_key_missing(
    qt_app, sources
) -> None:
    """A valid saved path keeps the existing flow; no auto-detection."""
    module = _facade_module()
    status = module.WeChatConnectionStatus(
        available=False, data_found=True, db_key_available=False,
        runtime_available=True, message="等待微信登录", action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        sessions=[_session(module.ChatSource.WECHAT, "wx1", "测试会话1", 10)],
        data_roots=["D:/fictional_wechat"],
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window.navigate_to_wechat()
    _drain(window)

    executor.operation()
    executor.succeed(status)

    assert facade.detect_wechat_data_roots_calls == []
    assert window.wechat_workspace._connection_task is None
    assert window.wechat_workspace._wechat_connect_button.isVisibleTo(window) is True
    assert not hasattr(window.wechat_workspace, "_wechat_setup_dialog")


def test_wechat_workspace_auto_detection_opens_choice_for_multiple_roots(
    qt_app, sources
) -> None:
    """Multiple candidates open the existing selection dialog."""
    module = _facade_module()
    status = module.WeChatConnectionStatus(
        available=False, data_found=False, db_key_available=False,
        runtime_available=False, message="未找到微信数据位置。", action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        data_roots=["D:/wechat_one", "D:/wechat_two"],
    )
    window = _main_window(qt_app, facade)
    window.navigate_to_wechat()
    _drain(window)

    assert facade.detect_wechat_data_roots_calls
    dialog = window.wechat_workspace._wechat_setup_dialog
    assert dialog is not None
    assert dialog._use_data_roots is True
    assert dialog._data_root_combo.count() == 2
    assert facade.setup_wechat_environment_calls == []


def test_wechat_workspace_auto_detection_opens_manual_setup_when_no_candidates(
    qt_app, sources
) -> None:
    """No candidates open the existing manual setup dialog."""
    module = _facade_module()
    status = module.WeChatConnectionStatus(
        available=False, data_found=False, db_key_available=False,
        runtime_available=False, message="未找到微信数据位置。", action_hint="",
    )
    facade = StubFacade(
        sources=sources,
        connection_status=status,
        data_roots=[],
    )
    window = _main_window(qt_app, facade)
    window.navigate_to_wechat()
    _drain(window)

    assert facade.detect_wechat_data_roots_calls
    dialog = window.wechat_workspace._wechat_setup_dialog
    assert dialog is not None
    assert dialog._use_data_roots is False
    assert facade.setup_wechat_environment_calls == []

# ---------------------------------------------------------------
# GUI-6: Local Data page
# ---------------------------------------------------------------

def _gui_history_record(
    analysis_id,
    source="wechat",
    session_name="测试会话",
    analysis_scope="all",
    scope_start=None,
    scope_end=None,
):
    history_module = importlib.import_module(
        "qq_chat_analyzer.application.report_history"
    )
    return history_module.AnalysisHistoryRecord(
        analysis_id=analysis_id,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        source=source,
        session_name=session_name,
        message_count=42,
        analysis_scope=analysis_scope,
        scope_start=scope_start,
        scope_end=scope_end,
    )


def _gui_snapshot(
    snapshot_id,
    size=2048,
    source=None,
    *,
    session_name="虚构群",
    payload_state=None,
):
    snapshot_module = importlib.import_module(
        "qq_chat_analyzer.application.chat_data_snapshot"
    )
    return snapshot_module.ChatDataSnapshot(
        id=snapshot_id,
        source=source or snapshot_module.ChatDataSource.QQ,
        session_id="room-1",
        session_name=session_name,
        session_type="group",
        acquired_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        data_size_bytes=size,
        storage_format="qce_json",
        storage_path=f"data/snapshots/qq/{snapshot_id}/export.json",
        payload_state=(
            payload_state
            or snapshot_module.SnapshotPayloadState.AVAILABLE
        ),
    )


def test_local_data_page_renders_history_and_snapshots(
    qt_app,
    sources,
) -> None:
    from qq_chat_analyzer.gui.main_window import LOCAL_DATA_PAGE_INDEX

    facade = StubFacade(
        sources=sources,
        history=[_gui_history_record("h1")],
        snapshots=[_gui_snapshot("snap-1")],
        snapshot_storage_usage=2048,
    )
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)

    assert window.stack.currentIndex() == LOCAL_DATA_PAGE_INDEX
    assert window.local_data_page._history_table.rowCount() == 1
    assert window.local_data_page._snapshot_table.rowCount() == 1
    assert "2" in window.local_data_page._usage_label.text()
    assert facade.list_analysis_history_calls
    assert facade.list_snapshots_calls
    assert facade.get_snapshot_storage_usage_calls


def test_local_data_page_empty_state(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))
    window.show_local_data_page()
    _drain(window)

    assert window.local_data_page._history_table.rowCount() == 0
    assert window.local_data_page._snapshot_table.rowCount() == 0
    assert window.local_data_page._history_empty_label.isVisibleTo(window)
    assert window.local_data_page._snapshot_empty_label.isVisibleTo(window)


def test_local_data_page_delete_snapshot(qt_app, sources) -> None:
    facade = StubFacade(
        sources=sources,
        snapshots=[_gui_snapshot("snap-1")],
    )
    window = _main_window(qt_app, facade)
    window.local_data_page._confirm_delete = lambda: True
    window.show_local_data_page()
    _drain(window)

    window.local_data_page._snapshot_table.selectRow(0)
    window.local_data_page._delete_snapshot_button.click()
    _drain(window)

    assert facade.remove_snapshot_calls == ["snap-1"]


def test_delete_confirmation_dialog_has_expected_copy(qt_app) -> None:
    from PySide6.QtWidgets import QMessageBox

    page_module = importlib.import_module("qq_chat_analyzer.gui.local_data_page")
    dialog = page_module._delete_confirmation_dialog()

    assert dialog.windowTitle() == "确认删除"
    assert "确定要删除所选快照吗？" in dialog.text()
    assert "删除后将无法恢复。" in dialog.text()
    buttons = {button.text(): button for button in dialog.buttons()}
    assert "删除" in buttons
    assert "取消" in buttons


def test_local_data_delete_asks_for_confirmation(qt_app, sources) -> None:
    facade = StubFacade(
        sources=sources,
        snapshots=[_gui_snapshot("snap-1")],
    )
    window = _main_window(qt_app, facade)
    prompts: list[bool] = []
    window.local_data_page._confirm_delete = lambda: prompts.append(1) or True
    window.show_local_data_page()
    _drain(window)

    window.local_data_page._snapshot_table.selectRow(0)
    window.local_data_page._delete_snapshot_button.click()
    _drain(window)

    assert prompts == [1]
    assert facade.remove_snapshot_calls == ["snap-1"]


def test_local_data_delete_cancel_does_not_remove(qt_app, sources) -> None:
    facade = StubFacade(
        sources=sources,
        snapshots=[_gui_snapshot("snap-1")],
    )
    window = _main_window(qt_app, facade)
    window.local_data_page._confirm_delete = lambda: False
    window.show_local_data_page()
    _drain(window)

    window.local_data_page._snapshot_table.selectRow(0)
    window.local_data_page._delete_snapshot_button.click()
    _drain(window)

    assert facade.remove_snapshot_calls == []
    assert window.local_data_page._snapshot_table.rowCount() == 1


def test_local_data_delete_success_refreshes_and_hides_snapshot(
    qt_app,
    sources,
) -> None:
    facade = StubFacade(
        sources=sources,
        snapshots=[_gui_snapshot("snap-1")],
        snapshot_storage_usage=2048,
    )
    window = _main_window(qt_app, facade)
    window.local_data_page._confirm_delete = lambda: True
    window.show_local_data_page()
    _drain(window)
    assert window.local_data_page._snapshot_table.rowCount() == 1

    window.local_data_page._snapshot_table.selectRow(0)
    window.local_data_page._delete_snapshot_button.click()
    _drain(window)

    assert facade.remove_snapshot_calls == ["snap-1"]
    assert window.local_data_page._snapshot_table.rowCount() == 0
    assert window.local_data_page._snapshot_empty_label.isVisibleTo(window) is True
    assert "0 B" in window.local_data_page._usage_label.text()
    assert len(facade.list_snapshots_calls) >= 2


def test_local_data_delete_failure_shows_public_message(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        snapshots=[_gui_snapshot("snap-1")],
        remove_snapshot_error=module.FacadeError(
            code="snapshot_delete_failed",
            public_message="删除快照失败，请重试。",
        ),
    )
    window = _main_window(qt_app, facade)
    window.local_data_page._confirm_delete = lambda: True
    window.show_local_data_page()
    _drain(window)

    window.local_data_page._snapshot_table.selectRow(0)
    window.local_data_page._delete_snapshot_button.click()
    _drain(window)

    assert window.local_data_page._status_label.text() == "删除快照失败，请重试。"
    assert window.local_data_page._snapshot_table.rowCount() == 1


def test_local_data_history_scope_uses_user_facing_labels(
    qt_app,
    sources,
) -> None:
    facade = StubFacade(
        sources=sources,
        history=[
            _gui_history_record("h-all", analysis_scope="all"),
            _gui_history_record("h-six", analysis_scope="last-six-month"),
            _gui_history_record("h-real-six", analysis_scope="last_six_months"),
            _gui_history_record("h-year", analysis_scope="last_year"),
            _gui_history_record(
                "h-custom",
                analysis_scope="custom",
                scope_start=datetime(2026, 1, 1).date(),
                scope_end=datetime(2026, 6, 30).date(),
            ),
        ],
    )
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)

    table = window.local_data_page._history_table
    assert table.rowCount() == 5
    scopes = [table.item(row, 4).text() for row in range(table.rowCount())]
    assert scopes == [
        "全部消息",
        "最近六个月",
        "最近六个月",
        "最近一年",
        "2026-01-01 至 2026-06-30",
    ]


def test_local_data_tables_use_fixed_readable_column_widths(
    qt_app,
    sources,
) -> None:
    facade = StubFacade(
        sources=sources,
        history=[_gui_history_record("h1")],
        snapshots=[_gui_snapshot("snap-1")],
    )
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)

    history = window.local_data_page._history_table
    assert history.columnWidth(0) >= 150
    assert history.columnWidth(2) >= 200
    assert history.columnWidth(4) >= 180
    snapshot = window.local_data_page._snapshot_table
    assert snapshot.columnWidth(0) >= 150
    assert snapshot.columnWidth(1) >= 200

    assert history.textElideMode() == Qt.TextElideMode.ElideNone
    assert snapshot.textElideMode() == Qt.TextElideMode.ElideNone


def test_local_data_snapshot_table_hides_source_and_session_id(
    qt_app,
    sources,
) -> None:
    facade = StubFacade(
        sources=sources,
        snapshots=[_gui_snapshot("snap-2")],
    )
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)

    table = window.local_data_page._snapshot_table
    headers = [
        table.horizontalHeaderItem(column).text()
        for column in range(table.columnCount())
    ]
    assert table.columnCount() == 5
    assert headers == ["时间", "会话", "消息数", "大小", "状态"]
    assert "来源" not in headers

    values = [table.item(0, column).text() for column in range(5)]
    assert "虚构群" in values
    assert "room-1" not in values
    assert values[4] == "可用"


def test_local_data_snapshot_unknown_name_and_removed_state(
    qt_app,
    sources,
) -> None:
    snapshot_module = importlib.import_module(
        "qq_chat_analyzer.application.chat_data_snapshot"
    )
    facade = StubFacade(
        sources=sources,
        snapshots=[
            _gui_snapshot("snap-3", session_name=None),
            _gui_snapshot(
                "snap-4",
                session_name="旧会话",
                payload_state=snapshot_module.SnapshotPayloadState.REMOVED,
            ),
        ],
    )
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)

    table = window.local_data_page._snapshot_table
    assert table.rowCount() == 1
    assert table.item(0, 1).text() == "未知会话"
    all_texts = [
        table.item(row, column).text()
        for row in range(table.rowCount())
        for column in range(table.columnCount())
    ]
    assert "旧会话" not in all_texts
    assert "已删除" not in all_texts
    assert "room-1" not in all_texts
    assert "SnapshotPayloadState" not in all_texts


def test_local_data_page_error_shows_public_message(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        snapshot_error=module.FacadeError(
            code="snapshot_list_failed",
            public_message="快照列表读取失败。",
        ),
    )
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)

    assert window.local_data_page._status_label.text() == "快照列表读取失败。"

def test_local_data_clear_history_button_is_visible(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))
    window.show_local_data_page()
    _drain(window)

    assert window.local_data_page._clear_history_button.isVisibleTo(window) is True


def test_clear_history_confirmation_dialog_has_expected_copy(qt_app) -> None:
    from PySide6.QtWidgets import QMessageBox

    page_module = importlib.import_module("qq_chat_analyzer.gui.local_data_page")
    dialog = page_module._clear_history_confirmation_dialog()

    assert dialog.windowTitle() == "确认删除"
    assert "确定删除全部 Echo 历史记录吗？" in dialog.text()
    assert "删除后无法恢复。" in dialog.text()
    buttons = {button.text(): button for button in dialog.buttons()}
    assert "删除" in buttons
    assert "取消" in buttons


def test_local_data_clear_history_cancel_does_not_delete(
    qt_app,
    sources,
) -> None:
    facade = StubFacade(
        sources=sources,
        history=[_gui_history_record("h1")],
    )
    window = _main_window(qt_app, facade)
    window.local_data_page._confirm_clear_history = lambda: False
    window.show_local_data_page()
    _drain(window)

    window.local_data_page._clear_history_button.click()
    _drain(window)

    assert facade.clear_analysis_history_calls == []
    assert window.local_data_page._history_table.rowCount() == 1


def test_local_data_clear_history_confirm_empties_list(
    qt_app,
    sources,
) -> None:
    facade = StubFacade(
        sources=sources,
        history=[_gui_history_record("h1")],
    )
    window = _main_window(qt_app, facade)
    window.local_data_page._confirm_clear_history = lambda: True
    window.show_local_data_page()
    _drain(window)

    window.local_data_page._clear_history_button.click()
    _drain(window)

    assert facade.clear_analysis_history_calls == [1]
    assert window.local_data_page._history_table.rowCount() == 0
    assert window.local_data_page._history_empty_label.isVisibleTo(window) is True


def test_local_data_clear_history_failure_shows_public_message(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        history=[_gui_history_record("h1")],
        clear_history_error=module.FacadeError(
            code="history_clear_failed",
            public_message="无法清空 Echo 历史记录，请稍后重试。",
        ),
    )
    window = _main_window(qt_app, facade)
    window.local_data_page._confirm_clear_history = lambda: True
    window.show_local_data_page()
    _drain(window)

    window.local_data_page._clear_history_button.click()
    _drain(window)

    assert window.local_data_page._status_label.text() == (
        "无法清空 Echo 历史记录，请稍后重试。"
    )
    assert window.local_data_page._history_table.rowCount() == 1


def test_qq_connect_error_snapshot_keeps_workspace_usable(
    qt_app, sources
) -> None:
    """An ERROR snapshot from the auth flow renders restart, never crashes."""
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX

    models = importlib.import_module(
        "qq_chat_analyzer.application.connection.models"
    )
    error_snapshot = models.ConnectionSnapshot(
        state=models.ConnectionState.ERROR,
        source="qq",
        message="QQ 连接异常。",
        action_hint="请重试",
    )
    facade = StubFacade(sources=sources)
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window.navigate_to_qq()
    _drain(window)

    executor.operation()
    executor.succeed(facade.get_qq_connection_snapshot())

    window.qq_workspace._qq_connect_button.click()
    executor.operation(lambda _message: None)
    assert facade.start_qq_auth_flow_calls == [1]
    executor.succeed(error_snapshot)
    _drain(window)

    assert window.qq_workspace._qq_connect_in_flight is False
    assert window.qq_workspace._qq_connect_button.text() == "重新开始"
    assert window.qq_workspace._status_label.text()
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX


def test_waiting_auth_timeout_enters_error_state(qt_app, sources) -> None:
    module = importlib.import_module("qq_chat_analyzer.gui.qq_workspace")
    facade = _SnapshotFacade(_qq_snapshot("waiting_auth"), sources=sources)
    workspace = module.QQWorkspace(facade, executor=_inline_executor())

    workspace._show_qq_status(
        _qq_snapshot("waiting_auth"),
        load_sessions_on_ready=False,
    )
    assert workspace._qq_status_timer.isActive() is True

    workspace._qq_waiting_auth_since = module.time.monotonic() - 121
    workspace._poll_qq_status()

    assert workspace._qq_status_timer.isActive() is False
    assert "等待超时" in workspace._status_label.text()
    assert workspace._qq_connect_button.text() == "重新开始"
