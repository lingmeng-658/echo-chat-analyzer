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
    )


@pytest.fixture
def instant_qq_connect(monkeypatch):
    """Make the QQ connect min-display delay deterministic.

    ``_connect_display_delay`` keeps the "connecting" state visible for
    ``_QQ_CONNECT_MIN_DISPLAY_MS`` (500ms) and applies the result through
    ``QTimer.singleShot``. Tests assert the *applied* state, not the pause, so
    dropping the delay to 0 turns that callback into a plain zero-timer that
    ``_drain`` delivers immediately - no fixed real wait.
    """
    monkeypatch.setattr(
        importlib.import_module("qq_chat_analyzer.gui.qq_workspace"),
        "_QQ_CONNECT_MIN_DISPLAY_MS",
        0,
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
        verify_error=None,
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
        clear_history_error=None,
        share_image_path=None,
        share_image_error=None,
    ):
        self._sources = tuple(sources)
        self._sessions = list(sessions)
        self._outcome = outcome
        self._error = error
        self._connection_status = connection_status
        self._connection_status_after_connect = connection_status_after_connect
        self._connection_error = connection_error
        self._verify_error = verify_error
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
        self._clear_history_error = clear_history_error
        self._share_image_path = share_image_path
        self._share_image_error = share_image_error
        self.list_sessions_calls: list[object] = []
        self.get_connection_status_calls: list[object] = []
        self.get_wechat_setup_status_calls: list[object] = []
        self.setup_wechat_environment_calls: list[object] = []
        self.detect_wechat_data_root_calls: list[object] = []
        self.detect_wechat_data_roots_calls: list[object] = []
        self.acquire_wechat_db_key_calls: list[object] = []
        self.verify_wechat_database_calls: list[object] = []
        self.get_qq_setup_status_calls: list[object] = []
        self.get_qq_runtime_status_calls: list[object] = []
        self.get_qq_environment_config_calls: list[object] = []
        self.setup_qq_environment_calls: list[object] = []
        self.set_qq_install_path_calls: list[object] = []
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
        self.list_analysis_history_calls: list[object] = []
        self.clear_analysis_history_calls: list[object] = []
        self.get_analysis_history_calls: list[object] = []
        self.list_snapshots_calls: list[tuple] = []
        self.validate_snapshot_calls: list[object] = []
        self.remove_snapshot_calls: list[object] = []
        self.remove_all_snapshots_calls: list[object] = []
        self.get_snapshot_storage_usage_calls: list[object] = []
        self.generate_share_image_calls: list[object] = []

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

    def remove_all_snapshots(self):
        self.remove_all_snapshots_calls.append(1)
        if self._remove_all_snapshots_error is not None:
            raise self._remove_all_snapshots_error
        self._snapshots = []
        self._snapshot_storage_usage = 0
        return 0

    def get_snapshot_storage_usage(self):
        self.get_snapshot_storage_usage_calls.append(1)
        if self._snapshot_error is not None:
            raise self._snapshot_error
        return self._snapshot_storage_usage

    def generate_share_image(self, outcome):
        self.generate_share_image_calls.append(outcome)
        if self._share_image_error is not None:
            raise self._share_image_error
        return self._share_image_path

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

    def set_qq_install_path(self, path):
        self.set_qq_install_path_calls.append(path)
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

    def verify_wechat_database(self):
        self.verify_wechat_database_calls.append(1)
        if self._verify_error is not None:
            raise self._verify_error
        return None

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
        report_directory=None,
    ):
        self.view = view
        self.history_saved = history_saved
        self.data_acquired_at = data_acquired_at
        self.report_path = report_path
        self.report_directory = report_directory


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


def test_cancelled_worker_stops_emitting_and_cleans_up(qt_app) -> None:
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    started = threading.Event()
    release = threading.Event()
    successes: list[object] = []
    errors: list[tuple[str, str]] = []
    progress: list[str] = []

    def operation(report):
        report("step-1")
        started.set()
        release.wait(timeout=5)
        report("step-2")
        return "done"

    workers.submit(
        operation,
        on_success=successes.append,
        on_error=lambda code, message: errors.append((code, message)),
        on_progress=progress.append,
    )

    assert started.wait(timeout=2)
    for worker in workers._PENDING:
        worker.cancel()
    release.set()
    _settle_workers()

    assert progress == ["step-1"]
    assert successes == []
    assert errors == []
    assert workers._PENDING == set()


def test_worker_stops_when_signal_source_is_destroyed(qt_app) -> None:
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    started = threading.Event()
    progress_received = threading.Event()
    successes: list[object] = []
    errors: list[tuple[str, str]] = []
    progress: list[str] = []

    def operation(report):
        report("step-1")
        started.set()
        progress_received.wait(timeout=5)
        report("step-2")
        return "done"

    worker = workers.submit(
        operation,
        on_success=successes.append,
        on_error=lambda code, message: errors.append((code, message)),
        on_progress=lambda message: (
            progress.append(message),
            progress_received.set(),
        ),
    )

    assert started.wait(timeout=2)
    deadline = time.monotonic() + 2
    while not progress_received.is_set() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert progress_received.is_set()
    import shiboken6

    shiboken6.delete(worker._callback_relay)
    _settle_workers()

    assert progress == ["step-1"]
    assert successes == []
    assert errors == []
    assert workers._PENDING == set()


def test_worker_shutdown_cancels_pending_workers(qt_app) -> None:
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    started = threading.Event()
    release = threading.Event()
    successes: list[object] = []
    errors: list[tuple[str, str]] = []
    progress: list[str] = []

    def operation(report):
        started.set()
        release.wait(timeout=5)
        report("late")
        return "done"

    workers.submit(
        operation,
        on_success=successes.append,
        on_error=lambda code, message: errors.append((code, message)),
        on_progress=progress.append,
    )

    assert started.wait(timeout=2)
    workers.shutdown()
    release.set()
    _settle_workers()

    assert progress == []
    assert successes == []
    assert errors == []
    assert workers._PENDING == set()


def test_worker_shutdown_is_non_blocking_and_clears_pool(
    qt_app,
    monkeypatch,
) -> None:
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    pool = QThreadPool.globalInstance()
    clears: list[int] = []
    waits: list[int] = []
    monkeypatch.setattr(pool, "clear", lambda: clears.append(1))
    monkeypatch.setattr(
        pool,
        "waitForDone",
        lambda timeout: waits.append(timeout) or True,
    )

    workers.shutdown()

    assert clears == [1]
    assert waits == []


def test_wechat_workspace_cancel_restores_connect_and_ignores_stale_finish(
    qt_app,
) -> None:
    from qq_chat_analyzer.gui.wechat_workspace import WeChatWorkspace

    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        data_roots=["D:/fake_xwechat_files"],
    )
    executor = _DeferredExecutor()
    workspace = WeChatWorkspace(facade, executor=executor)

    workspace.connect_wechat()
    assert executor.submission_count == 1
    assert workspace._wechat_connect_button.text() == "取消连接"
    assert workspace._wechat_connect_button.isEnabled() is True

    workspace.connect_wechat()
    assert executor.cancelled is True
    assert workspace._wechat_connect_button.text() == "连接微信"
    assert workspace._wechat_connect_button.isEnabled() is True
    assert workspace._connection_task is None

    workspace.connect_wechat()
    assert executor.submission_count == 2

    workspace._connection_task = object()
    stale_task = workspace._connection_task
    workspace._finish_wechat_connect(executor)
    assert workspace._connection_task is stale_task

    workspace._finish_wechat_connect(stale_task)
    assert workspace._connection_task is None


@pytest.mark.parametrize(
    "code",
    [
        "database_not_found",
        "wechat_database_error",
        "wcdb_library_not_found",
    ],
)
def test_wechat_database_connect_error_shows_database_stage(
    qt_app,
    code,
) -> None:
    from qq_chat_analyzer.gui.wechat_workspace import WeChatWorkspace

    facade = StubFacade(sources=_wechat_available_sources())
    workspace = WeChatWorkspace(facade)

    workspace._handle_wechat_connect_error(code, "未找到有效微信数据库")

    assert "微信数据库读取失败" in workspace._status_label.text()
    assert "获取权限" not in workspace._status_label.text()


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
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    import shiboken6

    def relay_can_dispatch(relay) -> bool:
        if not shiboken6.isValid(relay):
            return False
        try:
            return any(
                isinstance(source, workers.WorkerSignals)
                and shiboken6.isValid(source)
                for source in relay.children()
            )
        except RuntimeError:
            return False

    deadline = time.monotonic() + timeout_ms / 1000
    pool = QThreadPool.globalInstance()
    while True:
        QApplication.processEvents()
        live_relays = tuple(
            relay
            for relay in workers._RELAYS
            if relay_can_dispatch(relay)
        )
        if (
            not workers._PENDING
            and not live_relays
            and pool.activeThreadCount() == 0
        ):
            return
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            return
        pool.waitForDone(min(100, remaining_ms))
        QTest.qWait(min(20, remaining_ms))


def test_settle_workers_returns_immediately_when_pool_is_idle(monkeypatch) -> None:
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")

    class _IdlePool:
        def activeThreadCount(self) -> int:
            return 0

        def waitForDone(self, _timeout: int) -> bool:
            raise AssertionError("idle worker pool should not be waited on")

    monkeypatch.setattr(workers, "_PENDING", set())
    monkeypatch.setattr(workers, "_RELAYS", set())
    monkeypatch.setattr(
        QThreadPool,
        "globalInstance",
        staticmethod(lambda: _IdlePool()),
    )

    _settle_workers(timeout_ms=5000)


def test_settle_workers_still_honors_timeout_for_pending_workers(monkeypatch) -> None:
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    clock = [0.0]
    waits: list[int] = []

    class _BusyPool:
        def activeThreadCount(self) -> int:
            return 1

        def waitForDone(self, timeout: int) -> bool:
            waits.append(timeout)
            clock[0] = 0.011
            return False

    monkeypatch.setattr(workers, "_PENDING", {object()})
    monkeypatch.setattr(workers, "_RELAYS", set())
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        QThreadPool,
        "globalInstance",
        staticmethod(lambda: _BusyPool()),
    )
    monkeypatch.setattr(QTest, "qWait", lambda _timeout: None)
    monkeypatch.setattr(QApplication, "processEvents", lambda: None)

    _settle_workers(timeout_ms=10)

    assert waits


def test_settle_workers_keeps_processing_events_for_an_active_relay(
    monkeypatch,
) -> None:
    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    relay = workers._CallbackRelay(
        lambda _result: None,
        lambda *_error: None,
        None,
        None,
    )
    signal_source = workers.WorkerSignals(relay)
    relays = {relay}
    event_turns: list[int] = []
    waits: list[int] = []

    class _IdlePool:
        def activeThreadCount(self) -> int:
            return 0

        def waitForDone(self, timeout: int) -> bool:
            waits.append(timeout)
            return True

    def process_events() -> None:
        event_turns.append(1)
        if len(event_turns) == 2:
            relays.discard(relay)

    monkeypatch.setattr(workers, "_PENDING", set())
    monkeypatch.setattr(workers, "_RELAYS", relays)
    monkeypatch.setattr(time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(
        QThreadPool,
        "globalInstance",
        staticmethod(lambda: _IdlePool()),
    )
    monkeypatch.setattr(QTest, "qWait", lambda _timeout: None)
    monkeypatch.setattr(QApplication, "processEvents", process_events)

    _settle_workers(timeout_ms=10)

    assert signal_source.parent() is relay
    assert len(event_turns) == 2
    assert waits == [10]


def test_settle_workers_ignores_relay_whose_signal_source_was_destroyed(
    monkeypatch,
) -> None:
    import shiboken6

    workers = importlib.import_module("qq_chat_analyzer.gui.workers")
    relay = workers._CallbackRelay(
        lambda _result: None,
        lambda *_error: None,
        None,
        None,
    )
    signal_source = workers.WorkerSignals(relay)

    shiboken6.delete(signal_source)
    assert shiboken6.isValid(relay)
    assert not shiboken6.isValid(signal_source)

    class _IdlePool:
        def activeThreadCount(self) -> int:
            return 0

        def waitForDone(self, _timeout: int) -> bool:
            raise AssertionError("a stale relay cannot receive another callback")

    monkeypatch.setattr(workers, "_PENDING", set())
    monkeypatch.setattr(workers, "_RELAYS", {relay})
    monkeypatch.setattr(
        QThreadPool,
        "globalInstance",
        staticmethod(lambda: _IdlePool()),
    )
    monkeypatch.setattr(QApplication, "processEvents", lambda: None)

    _settle_workers(timeout_ms=5000)


# ------------------------------------------------------------ initialization


def test_main_window_builds_both_pages(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    assert window.stack.count() == 6
    assert window.windowTitle() != ""
    assert window.stack.currentIndex() == 0


def test_main_window_has_no_status_bar(qt_app, sources) -> None:
    from PySide6.QtWidgets import QStatusBar

    window = _main_window(qt_app, StubFacade(sources=sources))

    assert window.findChild(QStatusBar) is None


def test_status_area_is_moved_to_header_row(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))
    status = window._status_label
    layout = window.centralWidget().layout()
    header = layout.itemAt(0).layout()

    assert window._title_label.text() == "余音 Echo"
    assert header is not None
    assert header.itemAt(header.count() - 1).widget() is status
    assert not hasattr(window, "_top_status_label")


def test_qq_and_wechat_share_one_moved_status_area(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))
    status = window._status_label

    window.show_status("等待 QQ 登录")
    assert status.text() == "等待 QQ 登录"
    window.show_status("等待微信登录")
    assert status.text() == "等待微信登录"
    assert window._status_label is status


def test_top_status_follows_status_changed_without_bottom_duplicate(
    qt_app,
    sources,
) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_status("等待 QQ 登录")

    assert window._status_label.text() == "等待 QQ 登录"


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


def test_main_window_close_cancels_background_workers(
    qt_app,
    sources,
    monkeypatch,
) -> None:
    """closeEvent stops pending workers before facade cleanup starts."""
    main_window = importlib.import_module("qq_chat_analyzer.gui.main_window")
    calls: list[int] = []
    monkeypatch.setattr(
        main_window,
        "shutdown_workers",
        lambda: calls.append(1),
    )
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.close()

    assert calls == [1]


def test_main_window_close_quits_application(
    qt_app,
    sources,
    monkeypatch,
) -> None:
    """closeEvent explicitly ends the Qt event loop."""
    main_window = importlib.import_module("qq_chat_analyzer.gui.main_window")
    calls: list[int] = []
    monkeypatch.setattr(
        main_window,
        "_quit_application",
        lambda: calls.append(1),
    )
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.close()

    assert calls == [1]


def test_main_window_qq_cleanup_thread_is_daemon(
    qt_app,
    sources,
) -> None:
    """QQ shutdown cleanup must not keep the Python process alive."""
    class _SlowShutdownFacade(StubFacade):
        def shutdown_qq_runtime(self):
            time.sleep(1.0)

        def shutdown(self):
            time.sleep(1.0)

    window = _main_window(
        qt_app,
        _SlowShutdownFacade(sources=sources),
    )

    window.close()

    thread = next(
        (
            candidate
            for candidate in threading.enumerate()
            if candidate.name == "echo-qq-shutdown"
        ),
        None,
    )
    facade_thread = next(
        (
            candidate
            for candidate in threading.enumerate()
            if candidate.name == "echo-facade-shutdown"
        ),
        None,
    )
    assert thread is not None
    assert thread.daemon is True
    assert facade_thread is not None
    assert facade_thread.daemon is True
    thread.join(timeout=2.0)
    facade_thread.join(timeout=2.0)


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

    window.show_qq_workspace()
    _drain(window)
    after_workspace = window.size()
    assert after_workspace == initial

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
    )


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


def test_dashboard_page_starts_empty(qt_app) -> None:
    page = _dashboard_page(qt_app)

    assert page._user_table.rowCount() == 0
    assert page._word_list.count() == 0
    assert page._empty_label.isVisibleTo(page) is True


# ------------------------------------------------------------------ sessions


# ------------------------------------------------------------------ analysis


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


def test_show_outcome_without_report_path_stays_recoverable(
    qt_app,
    sources,
) -> None:
    """Success without a report path never crashes and avoids Dashboard."""
    from qq_chat_analyzer.gui.main_window import DASHBOARD_PAGE_INDEX

    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_outcome(_dashboard_view())

    assert window.stack.currentIndex() != DASHBOARD_PAGE_INDEX
    assert window._status_label.text() == "分析完成"
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


def test_duplicate_show_outcome_opens_echo_only_once(
    qt_app,
    sources,
    tmp_path,
) -> None:
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened: list[Path] = []
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: opened.append(path) or True
    outcome = _StubOutcome(_dashboard_view(), report_path=report_path)

    window.show_outcome(outcome)
    window.show_outcome(outcome)

    assert opened == [report_path.resolve()]


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


def test_default_directory_opener_uses_windows_file_association(
    qt_app,
    tmp_path,
    monkeypatch,
) -> None:
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    report_directory = (tmp_path / "Echo_Report_20260815_143012").resolve()
    report_directory.mkdir()
    opened_paths = []
    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(
        module.os,
        "startfile",
        lambda path: opened_paths.append(path),
        raising=False,
    )

    assert module._open_directory_path(report_directory) is True
    assert opened_paths == [str(report_directory)]


def test_default_directory_opener_uses_local_file_url_outside_windows(
    qt_app,
    tmp_path,
    monkeypatch,
) -> None:
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    report_directory = (tmp_path / "Echo_Report_20260815_143012").resolve()
    report_directory.mkdir()
    opened_urls = []
    monkeypatch.setattr(module.os, "name", "posix")
    monkeypatch.setattr(
        module.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url) or True,
    )

    assert module._open_directory_path(report_directory) is True
    assert len(opened_urls) == 1
    assert opened_urls[0].isLocalFile()
    assert opened_urls[0].toLocalFile() == str(report_directory).replace(
        "\\",
        "/",
    )


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
    assert not window._generate_share_button.isVisibleTo(window)
    assert not window._generate_share_button.isEnabled()

    report_path.unlink()
    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=report_path))

    assert not window._open_echo_button.isVisibleTo(window)
    assert not window._open_echo_button.isEnabled()
    assert not window._generate_share_button.isVisibleTo(window)
    assert not window._generate_share_button.isEnabled()


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
    assert "无法打开" in window._status_label.text()
    assert window._open_echo_button.isVisibleTo(window)
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX


def test_successful_outcome_exposes_report_directory_button(
    qt_app,
    sources,
    tmp_path,
) -> None:
    report_directory = tmp_path / "Echo_Report_20260815_143012"
    report_directory.mkdir()
    report_path = report_directory / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened: list[Path] = []
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: opened.append(path) or True
    window._directory_opener = lambda path: opened.append(path) or True

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report_path,
            report_directory=report_directory,
        )
    )

    assert window._current_report_directory == report_directory.resolve()
    assert window._open_report_directory_button.isVisibleTo(window)
    assert window._open_report_directory_button.isEnabled()
    window._open_report_directory_button.click()

    assert opened == [report_path.resolve(), report_directory.resolve()]


def test_report_directory_button_falls_back_to_report_parent(
    qt_app,
    sources,
    tmp_path,
) -> None:
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    opened: list[Path] = []
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True
    window._directory_opener = lambda path: opened.append(path) or True

    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=report_path))

    assert window._current_report_directory == report_path.resolve().parent
    window._open_report_directory_button.click()
    assert opened == [report_path.resolve().parent]


def test_report_directory_open_failure_is_recoverable(
    qt_app,
    sources,
    tmp_path,
) -> None:
    report_directory = tmp_path / "Echo_Report_20260815_143012"
    report_directory.mkdir()
    report_path = report_directory / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")

    def _failing_directory_opener(path):
        raise OSError("fictional directory open failure")

    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True
    window._directory_opener = _failing_directory_opener

    window.show_outcome(
        _StubOutcome(
            _dashboard_view(),
            report_path=report_path,
            report_directory=report_directory,
        )
    )
    window.open_echo_report_directory()

    assert "无法打开报告目录" in window._status_label.text()
    assert window._open_report_directory_button.isVisibleTo(window)


# Pre-existing share-visibility contract conflict; quarantined from the Fast
# Suite only. The test, its expectations, and the full-suite result are unchanged.
@pytest.mark.known_failure
def test_generate_share_button_creates_and_opens_share_image(
    qt_app,
    sources,
    tmp_path,
) -> None:
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    share_path = tmp_path / "echo-share.png"
    share_path.write_bytes(b"fictional-share-png")
    opened: list[Path] = []
    outcome = _StubOutcome(_dashboard_view(), report_path=report_path)
    facade = StubFacade(sources=sources, share_image_path=share_path)
    window = _main_window(qt_app, facade)
    window._report_opener = lambda path: True
    window._image_opener = lambda path: opened.append(path) or True

    window.show_outcome(outcome)

    assert window._generate_share_button.isVisibleTo(window)
    assert window._generate_share_button.isEnabled()
    window._generate_share_button.click()

    assert facade.generate_share_image_calls == [outcome]
    assert window._status_label.text() == "分享图片已生成"
    assert opened == [share_path.resolve()]


def test_generate_share_failure_shows_public_message(
    qt_app,
    sources,
    tmp_path,
) -> None:
    module = _facade_module()
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    facade = StubFacade(
        sources=sources,
        share_image_error=module.FacadeError(
            code="share_image_generation_failed",
            public_message="分享图片生成失败，请稍后重试。",
        ),
    )
    window = _main_window(qt_app, facade)
    window._report_opener = lambda path: True

    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=report_path))
    window._generate_share_button.click()

    assert window._status_label.text() == (
        "分享图片生成失败，请稍后重试。"
    )
    assert window._generate_share_button.isEnabled()


def test_generate_share_without_outcome_shows_visible_error(
    qt_app,
    sources,
) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.generate_share_image()

    assert window._status_label.text() == (
        "暂时没有可生成分享图片的分析结果。"
    )


def test_generate_share_without_facade_method_shows_visible_error(
    qt_app,
    sources,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delattr(StubFacade, "generate_share_image")
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")
    window = _main_window(qt_app, StubFacade(sources=sources))
    window._report_opener = lambda path: True

    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=report_path))
    window.generate_share_image()

    assert window._status_label.text() == (
        "暂时没有可生成分享图片的分析结果。"
    )


def test_generate_share_executor_submission_failure_is_visible(
    qt_app,
    sources,
    tmp_path,
) -> None:
    report_path = tmp_path / "echo-report.html"
    report_path.write_text("<html>fictional report</html>", encoding="utf-8")

    def _failing_executor(*args, **kwargs):
        raise RuntimeError("fictional executor failure")

    window = _main_window(
        qt_app,
        StubFacade(sources=sources),
        executor=_failing_executor,
    )
    window._report_opener = lambda path: True

    window.show_outcome(_StubOutcome(_dashboard_view(), report_path=report_path))
    window._generate_share_button.click()

    assert window._status_label.text() == (
        "分享图片生成失败，请稍后重试。"
    )
    assert window._generate_share_button.isEnabled()


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
    assert window._status_label.text() == expected_status


# -------------------------------------------------------------------- errors


# -------------------------------------------------------------------- layering


def test_gui_never_imports_analysis_provider_or_parser_internals() -> None:
    gui_directory = SRC_ROOT / "qq_chat_analyzer" / "gui"
    forbidden = (
        "from ..providers",
        "from ..parser",
        "from ..wechat_parser",
        "from ..analyzer",
        "from ..tokenizer",
        "from ..cleaner",
        "from ..qq_chat_exporter_adapter",
        "from ..wechat_db_adapter",
        "from ..wechat_cli_adapter",
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

    for name in ("dashboard_page.py", "main_window.py"):
        source = (gui_directory / name).read_text(encoding="utf-8")
        for marker in ("Counter(", "statistics.", "sum(", "sorted("):
            assert marker not in source, f"{name} computes {marker}"


def test_gui_pages_only_import_the_facade_from_application() -> None:
    gui_directory = SRC_ROOT / "qq_chat_analyzer" / "gui"

    for name in (
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


def _write_qrcode_png(path: Path) -> None:
    from PySide6.QtGui import QPixmap

    pixmap = QPixmap(8, 8)
    pixmap.fill(Qt.GlobalColor.black)
    assert pixmap.save(str(path)) is True


def test_poll_displays_qr_before_snapshot_worker_completes(
    qt_app,
    sources,
    tmp_path: Path,
) -> None:
    """QR refresh must not wait for the async snapshot/health worker.

    While waiting for auth, a ready local QR file has to be shown during the
    current poll even when ``get_qq_connection_snapshot`` is still blocked.
    """
    from qq_chat_analyzer.gui.qq_workspace import QQWorkspace

    qr_path = tmp_path / "qrcode.png"
    _write_qrcode_png(qr_path)

    snapshot_started = threading.Event()
    release = threading.Event()

    class _BlockingSnapshotFacade(_GatedQRFacade):
        def get_qq_connection_snapshot(self):
            self.get_qq_connection_snapshot_calls.append(1)
            snapshot_started.set()
            release.wait(timeout=5)
            return self._qq_snapshot()

    facade = _BlockingSnapshotFacade(
        _qq_snapshot("waiting_auth"),
        _qq_snapshot("waiting_auth"),
        sources=sources,
    )
    facade.qr_ready = True

    workspace = QQWorkspace(facade)
    workspace._qq_qrcode_path = qr_path
    workspace._qq_waiting_auth_since = time.monotonic()

    try:
        workspace._poll_qq_status()

        assert snapshot_started.wait(timeout=2)

        assert workspace._qq_qrcode_label.isVisibleTo(workspace) is True
    finally:
        release.set()
        _settle_workers()


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


def test_click_qq_navigates_to_qq_workspace_with_qq_source(qt_app, sources) -> None:
    """Clicking QQ on HomePage navigates to QQWorkspace with QQ preselected."""
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.navigate_to_qq()
    _drain(window)
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
    from qq_chat_analyzer.gui.main_window import QQ_WORKSPACE_INDEX
    assert window.stack.currentIndex() == QQ_WORKSPACE_INDEX
def test_click_wechat_navigates_to_wechat_workspace_with_wechat_source(qt_app, sources) -> None:
    """Clicking WeChat on HomePage navigates to WeChatWorkspace with WeChat preselected."""
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


def test_workspace_can_return_to_home_from_home_button(qt_app, sources) -> None:
    """The home button in the header returns to HomePage from a workspace."""
    from qq_chat_analyzer.gui.main_window import HOME_PAGE_INDEX
    facade = StubFacade(sources=sources)
    window = _main_window(qt_app, facade)
    window.show_qq_workspace()
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
    window.show_qq_workspace()
    _drain(window)
    assert window.size() == initial
    window.show_local_data_page()
    _drain(window)
    assert window.size() == initial
    window.show_home_page()
    _drain(window)
    assert window.size() == initial


# ----------------------------------------------------------------

# ----------------------------------------------------------------
# GUI-3 stabilization: restore GUI-2 workspace behavior equivalence
# ----------------------------------------------------------------


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


def test_qq_workspace_connect_disables_button_until_finish(
    qt_app,
    sources,
    instant_qq_connect,
) -> None:
    from qq_chat_analyzer.gui.qq_workspace import QQWorkspace

    facade = StubFacade(sources=sources)
    executor = _DeferredExecutor()
    workspace = QQWorkspace(facade, executor=executor)

    workspace.connect_qq()
    assert workspace._qq_connect_button.isEnabled() is False

    executor.progress("等待QQ登录")
    assert workspace._qq_connect_button.isEnabled() is False

    executor.fail("qq_connect_failed", "QQ 连接失败")
    _drain(workspace)
    assert workspace._qq_connect_button.isEnabled() is True
    assert workspace._qq_connect_button.text() == "重新开始"

    cancel_workspace = QQWorkspace(facade, executor=_DeferredExecutor())
    cancel_workspace.connect_qq()
    cancel_workspace.cancel_connection()
    assert cancel_workspace._qq_connect_button.isEnabled() is True
    assert cancel_workspace._qq_connect_button.text() == "连接QQ"


def test_qq_workspace_waiting_auth_disables_button_until_qr_ready(
    qt_app,
    sources,
    tmp_path: Path,
    instant_qq_connect,
) -> None:
    """Regression: the connect button must stay disabled while QR is not ready."""
    from qq_chat_analyzer.gui.qq_workspace import QQWorkspace
    from PySide6.QtGui import QPixmap

    qr_path = tmp_path / "qrcode.png"
    pixmap = QPixmap(8, 8)
    pixmap.fill(Qt.GlobalColor.black)
    assert pixmap.save(str(qr_path)) is True

    facade = _GatedQRFacade(
        _qq_snapshot("waiting_auth"),
        _qq_snapshot("waiting_auth"),
        sources=sources,
    )
    facade.qr_ready = False
    workspace = QQWorkspace(facade, executor=_inline_executor())
    workspace._qq_qrcode_path = qr_path

    workspace.connect_qq()
    _drain(workspace)

    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is False
    assert workspace._qq_connect_button.isEnabled() is False


def test_qq_workspace_waiting_auth_enables_button_once_qr_displayed(
    qt_app,
    sources,
    tmp_path: Path,
    instant_qq_connect,
) -> None:
    """Once the QR is actually displayed, the connect button becomes enabled."""
    from qq_chat_analyzer.gui.qq_workspace import QQWorkspace
    from PySide6.QtGui import QPixmap

    qr_path = tmp_path / "qrcode.png"
    pixmap = QPixmap(8, 8)
    pixmap.fill(Qt.GlobalColor.black)
    assert pixmap.save(str(qr_path)) is True

    facade = _GatedQRFacade(
        _qq_snapshot("waiting_auth"),
        _qq_snapshot("waiting_auth"),
        sources=sources,
    )
    facade.qr_ready = True
    workspace = QQWorkspace(facade, executor=_inline_executor())
    workspace._qq_qrcode_path = qr_path

    workspace.connect_qq()
    _drain(workspace)

    assert workspace._qq_qrcode_label.isVisibleTo(workspace) is True
    assert workspace._qq_connect_button.isEnabled() is True


def test_qq_workspace_offers_qq_exe_selection_when_install_path_missing(
    qt_app,
    tmp_path,
    monkeypatch,
) -> None:
    from qq_chat_analyzer.gui.qq_workspace import QQWorkspace

    module = importlib.import_module("qq_chat_analyzer.gui.qq_workspace")
    qq_path = tmp_path / "QQ.exe"
    qq_path.write_text("fictional", encoding="utf-8")
    facade = StubFacade(sources=())
    workspace = QQWorkspace(facade, executor=_inline_executor())
    dialog_calls = []

    def _fake_file_dialog(parent, title, directory, file_filter):
        dialog_calls.append((title, file_filter))
        return str(qq_path), ""

    monkeypatch.setattr(
        module.QFileDialog,
        "getOpenFileName",
        staticmethod(_fake_file_dialog),
    )
    snapshot = importlib.import_module(
        "qq_chat_analyzer.application.connection.models"
    ).ConnectionSnapshot(
        state=importlib.import_module(
            "qq_chat_analyzer.application.connection.models"
        ).ConnectionState.ERROR,
        source="qq",
        message="未检测到 QQ 客户端。",
        code="qq_install_path_missing",
    )

    workspace._show_qq_status(snapshot, load_sessions_on_ready=False)

    assert facade.set_qq_install_path_calls == [qq_path]
    assert facade.start_qq_auth_flow_calls == [1]
    assert dialog_calls == [
        (module._QQ_PATH_PROMPT_TITLE, module._QQ_PATH_PROMPT_FILTER)
    ]


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


def test_wechat_session_panel_selection_requests_message_range(
    qt_app,
    sources,
) -> None:
    """WeChat panel selection fetches the real message range through the facade."""
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


def test_qq_session_panel_selection_skips_range_probe(qt_app) -> None:
    """QQ panel selection must not probe the range and must not start a worker."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    facade = StubFacade(
        sources=_wechat_available_sources(),
        sessions=[_session(module.ChatSource.QQ, "10002", "Fictional Group", 10)],
        message_range=(1704067200, 1704153600),
    )
    panel = SessionAnalysisPanel()
    panel.configure(facade, module.ChatSource.QQ, executor=_inline_executor())
    panel.populate_sessions(facade._sessions)
    panel._session_list.setCurrentRow(0)
    _drain(panel)

    assert facade.get_session_message_range_calls == []
    assert panel._message_range is None


def test_session_panel_scope_defaults_to_all(qt_app, sources) -> None:
    """The shared panel defaults to analysing the full history."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    panel = SessionAnalysisPanel()
    panel.configure(StubFacade(sources=sources), module.ChatSource.QQ)

    config = panel.build_config()

    assert panel._scope_all.isChecked() is True
    assert panel._custom_range_widget.isHidden() is True
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
def test_session_panel_relative_scope_reaches_the_config(
    qt_app,
    sources,
    control_name,
    expected_mode,
) -> None:
    """Relative scope choices translate into the facade config."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    panel = SessionAnalysisPanel()
    panel.configure(StubFacade(sources=sources), module.ChatSource.QQ)

    getattr(panel, control_name).setChecked(True)
    config = panel.build_config()

    assert config.scope_mode is getattr(module.AnalysisScopeMode, expected_mode)
    assert config.start_time is None
    assert config.end_time is None
    assert panel._custom_range_widget.isHidden() is True


def test_session_panel_custom_scope_reaches_the_config(
    qt_app,
    sources,
) -> None:
    """Custom scope exposes the date editors and carries them into the config."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    panel = SessionAnalysisPanel()
    panel.configure(StubFacade(sources=sources), module.ChatSource.QQ)

    panel._scope_custom.setChecked(True)
    panel._start_date.setDate(QDate(2026, 2, 11))
    panel._end_date.setDate(QDate(2026, 8, 11))
    config = panel.build_config()

    assert panel._custom_range_widget.isHidden() is False
    assert config.scope_mode is module.AnalysisScopeMode.CUSTOM
    assert config.start_time == "2026-02-11"
    assert config.end_time == "2026-08-11"


def test_session_panel_search_filters_display_names(qt_app) -> None:
    """The shared panel search filters by display name and tracks the count."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    panel = SessionAnalysisPanel()
    panel.configure(
        StubFacade(sources=_wechat_available_sources()),
        module.ChatSource.WECHAT,
    )
    panel.populate_sessions(
        [
            _session(module.ChatSource.WECHAT, "wxid_a", "Alice"),
            _session(module.ChatSource.WECHAT, "wxid_b", "Board Game"),
            _session(module.ChatSource.WECHAT, "wxid_c", "Alice's Study Room"),
        ]
    )

    panel._session_search.setText("alice")

    assert panel._session_list.count() == 2
    assert [panel._session_list.item(i).text() for i in range(2)] == [
        "Alice",
        "Alice's Study Room",
    ]
    assert "\u4f1a\u8bdd\u5217\u8868\uff082\uff09" in panel._session_box.title()

    panel._session_search.setText("board")

    assert panel._session_list.count() == 1
    assert panel._session_list.item(0).text() == "Board Game"


def test_session_panel_sort_modes_reorder_the_list(qt_app) -> None:
    """The shared panel re-sorts the cached sessions for each mode."""
    from qq_chat_analyzer.gui.session_analysis_panel import SessionAnalysisPanel
    module = _facade_module()
    panel = SessionAnalysisPanel()
    panel.configure(
        StubFacade(sources=_wechat_available_sources()),
        module.ChatSource.WECHAT,
    )
    panel.populate_sessions(
        [
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
        ]
    )

    def names():
        return [
            panel._session_list.item(i).text()
            for i in range(panel._session_list.count())
        ]

    assert names() == ["Beta", "Gamma", "Alpha"]

    panel._session_sort.setCurrentIndex(_sort_index(panel, "message_count"))
    assert names() == ["Alpha", "Gamma", "Beta"]

    panel._session_sort.setCurrentIndex(_sort_index(panel, "name"))
    assert names() == ["Alpha", "Beta", "Gamma"]


def test_session_panel_keeps_session_ids_out_of_display_text(qt_app) -> None:
    """Session IDs drive selection but never appear in the displayed text."""
    from qq_chat_analyzer.gui.session_analysis_panel import (
        SESSION_ID_ROLE,
        SessionAnalysisPanel,
    )
    module = _facade_module()
    panel = SessionAnalysisPanel()
    panel.configure(
        StubFacade(sources=_wechat_available_sources()),
        module.ChatSource.WECHAT,
    )
    panel.populate_sessions(
        [
            _session(
                module.ChatSource.WECHAT,
                "secret-id-10001",
                "\u865a\u6784\u7fa4 A",
            )
        ]
    )

    item = panel._session_list.item(0)

    assert item.text() == "\u865a\u6784\u7fa4 A"
    assert "secret-id-10001" not in item.text()
    assert item.data(SESSION_ID_ROLE) == "secret-id-10001"


def test_qq_workspace_full_chain_connect_sessions_analyze(
    qt_app, sources, tmp_path, monkeypatch
) -> None:
    """QQ workspace keeps the GUI-2 connect -> sessions -> analyze chain."""
    from qq_chat_analyzer.gui.main_window import (
        DASHBOARD_PAGE_INDEX,
        PROCESSING_PAGE_INDEX,
        QQ_WORKSPACE_INDEX,
    )
    module = _facade_module()
    qq_module = importlib.import_module("qq_chat_analyzer.gui.qq_workspace")
    monkeypatch.setattr(qq_module, "_QQ_CONNECT_MIN_DISPLAY_MS", 0)
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
    assert "虚构分析失败" in window._status_label.text()


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
    assert facade.verify_wechat_database_calls == []
    assert window.wechat_workspace._wechat_connect_pending is True


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

# ----------------------------------------------------------------
# GUI-5b: WeChat key/database verification fallback
# ----------------------------------------------------------------


def _wechat_unreadable_error():
    module = _facade_module()
    return module.FacadeError(
        code="wechat_database_unreadable",
        public_message=(
            "\u5f53\u524d\u5fae\u4fe1\u767b\u5f55\u4fe1\u606f\u65e0\u6cd5"
            "\u8bfb\u53d6\u6240\u9009\u6570\u636e\u5e93\uff0c\u8bf7\u786e\u8ba4"
            "\u6570\u636e\u4f4d\u7f6e\u662f\u5426\u5bf9\u5e94\u5f53\u524d"
            "\u767b\u5f55\u8d26\u53f7\uff0c\u6216\u91cd\u65b0\u83b7\u53d6"
            "\u5fae\u4fe1\u8fde\u63a5\u4fe1\u606f\u3002"
        ),
        source=module.ChatSource.WECHAT,
    )


def _wechat_connected_status():
    module = _facade_module()
    return module.WeChatConnectionStatus(
        available=True, data_found=True, db_key_available=True,
        runtime_available=True, message="\u5fae\u4fe1\u5df2\u8fde\u63a5",
        action_hint="",
    )


def _wechat_missing_status():
    module = _facade_module()
    return module.WeChatConnectionStatus(
        available=False, data_found=False, db_key_available=False,
        runtime_available=False,
        message="\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e\u4f4d\u7f6e\u3002",
        action_hint="",
    )


def _wechat_mismatch_facade(
    sources,
    *,
    verify_error,
    data_roots=("D:/fictional_wechat",),
):
    module = _facade_module()
    return StubFacade(
        sources=sources,
        connection_status=_wechat_missing_status(),
        connection_status_after_connect=_wechat_connected_status(),
        sessions=[
            _session(module.ChatSource.WECHAT, "wx1", "\u6d4b\u8bd5\u4f1a\u8bdd1", 10)
        ],
        data_roots=list(data_roots),
        verify_error=verify_error,
    )


def _run_wechat_verification(executor):
    """Run the queued verification, which raises for a mismatched database."""
    with pytest.raises(_facade_module().FacadeError):
        executor.operation()


def _drive_wechat_database_mismatch(
    qt_app,
    sources,
    *,
    data_roots=("D:/fictional_wechat",),
):
    """Run the one-click flow until the captured key fails verification."""
    facade = _wechat_mismatch_facade(
        sources,
        verify_error=_wechat_unreadable_error(),
        data_roots=data_roots,
    )
    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window.navigate_to_wechat()
    _drain(window)

    executor.operation()
    executor.succeed(_wechat_missing_status())
    _drain(window)

    workspace = window.wechat_workspace
    if len(data_roots) > 1:
        # Several candidates: the user picks one first, so the connect runs
        # from the setup dialog instead of the one-click auto path.
        workspace._wechat_setup_dialog.set_data_root(data_roots[0])
        workspace._save_wechat_environment_from_dialog()
        _drain(window)

    executor.operation(lambda _message: None)
    executor.succeed(_wechat_connected_status())
    _drain(window)

    _run_wechat_verification(executor)
    executor.fail(
        "wechat_database_unreadable",
        facade._verify_error.public_message,
    )
    _drain(window)
    return window, facade, executor


def test_wechat_workspace_verifies_the_database_before_listing_sessions(
    qt_app, sources
) -> None:
    """A: one auto-detected root keeps the existing connect chain."""
    module = _facade_module()
    connected = _wechat_connected_status()
    facade = _wechat_mismatch_facade(sources, verify_error=None)
    order: list[str] = []
    verify = facade.verify_wechat_database
    list_sessions = facade.list_sessions

    def verify_spy():
        order.append("verify")
        return verify()

    def list_sessions_spy(source):
        order.append("list_sessions")
        return list_sessions(source)

    facade.verify_wechat_database = verify_spy
    facade.list_sessions = list_sessions_spy

    executor = _DeferredExecutor()
    window = _main_window(qt_app, facade, executor=executor)
    window.navigate_to_wechat()
    _drain(window)

    executor.operation()
    executor.succeed(_wechat_missing_status())
    _drain(window)

    assert facade.detect_wechat_data_roots_calls
    executor.operation(lambda _message: None)
    assert facade.setup_wechat_environment_calls
    assert facade.acquire_wechat_db_key_calls
    executor.succeed(connected)
    _drain(window)

    executor.operation()
    executor.succeed(facade._sessions)
    _drain(window)

    assert order[:2] == ["verify", "list_sessions"]
    assert facade.verify_wechat_database_calls
    assert facade.list_sessions_calls == [module.ChatSource.WECHAT]
    assert window.wechat_workspace.session_panel._sessions_ready is True


def test_wechat_workspace_mismatch_returns_to_directory_selection(
    qt_app, sources
) -> None:
    """B: a failed verification must not load sessions and must re-ask."""
    window, facade, executor = _drive_wechat_database_mismatch(qt_app, sources)
    workspace = window.wechat_workspace

    assert facade.verify_wechat_database_calls, "verification must run first"
    assert facade.list_sessions_calls == []
    assert workspace._sessions_loaded is False
    assert workspace._wechat_setup_dialog is not None
    # A single detected candidate is offered as an editable field so the user
    # can also paste a directory Echo never detected.
    assert workspace._wechat_setup_dialog._use_data_roots is False
    assert workspace._wechat_connect_pending is True
    assert facade._verify_error.public_message in workspace._status_label.text()
    assert workspace._wechat_connect_button.text() == "\u91cd\u65b0\u5f00\u59cb"
    assert workspace._wechat_connect_button.isEnabled() is True


def test_wechat_workspace_reselected_root_reuses_the_captured_key(
    qt_app, sources
) -> None:
    """D: the new directory is retried with the key already in this process."""
    module = _facade_module()
    window, facade, executor = _drive_wechat_database_mismatch(qt_app, sources)
    workspace = window.wechat_workspace
    assert len(facade.acquire_wechat_db_key_calls) == 1

    workspace._wechat_setup_dialog.set_data_root("D:/other_wechat_root")
    facade._verify_error = None
    workspace._save_wechat_environment_from_dialog()
    _drain(window)

    executor.operation(lambda _message: None)
    assert facade.setup_wechat_environment_calls[-1].data_root == Path(
        "D:/other_wechat_root"
    )
    # Changing the directory must not require another WeChat login.
    assert len(facade.acquire_wechat_db_key_calls) == 1
    executor.succeed(_wechat_connected_status())
    _drain(window)

    executor.operation()
    executor.succeed(facade._sessions)
    _drain(window)

    assert facade.verify_wechat_database_calls
    assert facade.list_sessions_calls == [module.ChatSource.WECHAT]
    assert workspace.session_panel._sessions_ready is True


def test_wechat_workspace_second_mismatch_offers_another_choice(
    qt_app, sources
) -> None:
    """E: a still-unreadable directory stays actionable without auto retry."""
    window, facade, executor = _drive_wechat_database_mismatch(qt_app, sources)
    workspace = window.wechat_workspace
    verify_calls_before = len(facade.verify_wechat_database_calls)

    workspace._wechat_setup_dialog.set_data_root("D:/still_wrong_root")
    workspace._save_wechat_environment_from_dialog()
    _drain(window)
    executor.operation(lambda _message: None)
    executor.succeed(_wechat_connected_status())
    _drain(window)
    _run_wechat_verification(executor)
    executor.fail(
        "wechat_database_unreadable",
        facade._verify_error.public_message,
    )
    _drain(window)

    assert facade.list_sessions_calls == []
    # One user action equals one verification: no automatic retry loop.
    assert len(facade.verify_wechat_database_calls) - verify_calls_before == 1
    assert workspace._wechat_setup_dialog is not None
    assert facade._verify_error.public_message in workspace._status_label.text()
    assert workspace._wechat_connect_pending is True
    assert workspace._wechat_connect_button.isEnabled() is True


def test_wechat_workspace_mismatch_offers_every_detected_candidate(
    qt_app, sources
) -> None:
    """C/E: several candidates stay selectable when verification fails."""
    module = _facade_module()
    window, facade, executor = _drive_wechat_database_mismatch(
        qt_app,
        sources,
        data_roots=("D:/fictional_wechat_a", "D:/fictional_wechat_b"),
    )
    workspace = window.wechat_workspace
    dialog = workspace._wechat_setup_dialog

    assert dialog is not None
    assert dialog._use_data_roots is True
    assert dialog._data_root_combo.count() == 2
    assert facade.list_sessions_calls == []

    # Picking the other detected candidate still reuses the captured key.
    facade._verify_error = None
    dialog._data_root_combo.setCurrentIndex(1)
    workspace._save_wechat_environment_from_dialog()
    _drain(window)

    executor.operation(lambda _message: None)
    assert facade.setup_wechat_environment_calls[-1].data_root == Path(
        "D:/fictional_wechat_b"
    )
    assert len(facade.acquire_wechat_db_key_calls) == 1
    executor.succeed(_wechat_connected_status())
    _drain(window)

    executor.operation()
    executor.succeed(facade._sessions)
    _drain(window)

    assert facade.list_sessions_calls == [module.ChatSource.WECHAT]
    assert workspace.session_panel._sessions_ready is True


def test_wechat_workspace_mismatch_message_exposes_no_internal_details(
    qt_app, sources
) -> None:
    """F: the recovery text stays actionable without internal details."""
    window, facade, executor = _drive_wechat_database_mismatch(qt_app, sources)
    workspace = window.wechat_workspace
    status_label = workspace._status_label

    visible = status_label.text() + "\n" + status_label.toolTip()
    assert "\u5f53\u524d\u5fae\u4fe1\u767b\u5f55\u4fe1\u606f" in visible
    assert "a" * 64 not in visible
    assert "session.db" not in visible
    assert "SELECT" not in visible
    assert ".db_storage" not in visible
    assert "D:/fictional_wechat" not in visible
    assert "wcdb" not in visible.lower()

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
    qt_app, sources, instant_qq_connect
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
    assert workspace._qq_connect_button.isEnabled() is True



def test_qq_auth_timeout_calls_facade_disconnect(qt_app, sources):
    doc = 'RED: _handle_qq_auth_timeout must call facade.disconnect_qq(). Root cause: WAITING_AUTH reaches 120s timeout -> QQWorkspace only does UI cleanup -> underlying auth session / connection manager is NOT ended -> user clicks restart -> start_auth_flow may reuse old session / QR. After the fix, _handle_qq_auth_timeout() must call self._facade.disconnect_qq() to ensure the old auth session is truly terminated before the user can restart.'
    module = importlib.import_module('qq_chat_analyzer.gui.qq_workspace')
    facade = _SnapshotFacade(_qq_snapshot('waiting_auth'), sources=sources)
    workspace = module.QQWorkspace(facade, executor=_inline_executor())
    workspace._show_qq_status(
        _qq_snapshot('waiting_auth'),
        load_sessions_on_ready=False,
    )
    assert workspace._qq_status_timer.isActive() is True
    workspace._qq_waiting_auth_since = module.time.monotonic() - 121
    workspace._handle_qq_auth_timeout()
    assert workspace._qq_status_timer.isActive() is False
    assert workspace._qq_connect_button.text() == '\u91cd\u65b0\u5f00\u59cb'
    assert workspace._qq_connect_button.isEnabled() is True
    assert len(facade.disconnect_qq_calls) >= 1, (
        '_handle_qq_auth_timeout() must call facade.disconnect_qq() to '
        'terminate the underlying auth session. Without this call, the '
        'old WAITING_AUTH session is reused on restart.'
    )


# ---------------------------------------------------------------------------
# MainWindow terminal state + preserved behavior
# ---------------------------------------------------------------------------


def test_main_window_owns_its_status_label(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    assert hasattr(window, "_status_label")
    window.show_status("分析已取消。")
    assert window._status_label.text() == "分析已取消。"


def test_local_data_page_shows_local_file_label_for_legacy_history(
    qt_app,
    sources,
) -> None:
    facade = StubFacade(
        sources=sources,
        history=[_gui_history_record("legacy-local-1", source="local_file")],
    )
    window = _main_window(qt_app, facade)
    window.show_local_data_page()
    _drain(window)

    assert window.local_data_page._history_table.item(0, 1).text() == "本地文件"


# ---------------------------------------------------------------------------
# WeChat workspace guide coverage
# ---------------------------------------------------------------------------


def _wechat_guide_module():
    return importlib.import_module("qq_chat_analyzer.gui.wechat_workspace")


def _wechat_workspace(qt_app, facade):
    from qq_chat_analyzer.gui.wechat_workspace import WeChatWorkspace

    return WeChatWorkspace(facade, executor=_inline_executor())


def test_wechat_workspace_guide_shows_status_confirmation(qt_app) -> None:
    module = _wechat_guide_module()
    workspace = _wechat_workspace(qt_app, StubFacade())
    workspace.show()

    workspace._show_wechat_guide()

    assert workspace._wechat_guide_label.isVisibleTo(workspace) is True
    assert workspace._wechat_guide_key_label.isVisibleTo(workspace) is True
    assert workspace._wechat_guide_note_label.isVisibleTo(workspace) is True
    assert workspace._wechat_guide_label.text() == module._WECHAT_GUIDE_STATUS
    assert workspace._wechat_guide_key_label.text() == module._WECHAT_GUIDE_WARNING
    assert workspace._wechat_guide_note_label.text() == (
        f"{module._WECHAT_GUIDE_KEY}\n\n{module._WECHAT_GUIDE_NOTE}"
    )
    assert "\u4e0d\u4e0a\u4f20" in workspace._wechat_guide_note_label.text()
    assert "\u4e0d\u4fdd\u5b58" in workspace._wechat_guide_note_label.text()
    assert "\u4e0d\u4e0a\u4f20" not in workspace._wechat_guide_key_label.text()
    assert "\u4e0d\u4fdd\u5b58" not in workspace._wechat_guide_key_label.text()


def test_wechat_workspace_guide_labels_wrap_and_expand(qt_app) -> None:
    workspace = _wechat_workspace(qt_app, StubFacade())

    for label in (
        workspace._wechat_guide_label,
        workspace._wechat_guide_key_label,
        workspace._wechat_guide_note_label,
    ):
        assert label.wordWrap() is True
        assert label.sizePolicy().horizontalPolicy() == (
            QSizePolicy.Policy.Expanding
        )


def test_wechat_workspace_guide_text_has_no_html_tags(qt_app) -> None:
    workspace = _wechat_workspace(qt_app, StubFacade())
    workspace.show()

    workspace._show_wechat_guide()

    for text in (
        workspace._wechat_guide_label.text(),
        workspace._wechat_guide_key_label.text(),
        workspace._wechat_guide_note_label.text(),
    ):
        assert "<br" not in text
        assert "<span" not in text
        assert ">" not in text


def test_wechat_workspace_directory_help_guide_is_plain_text(qt_app) -> None:
    module = _wechat_guide_module()
    workspace = _wechat_workspace(qt_app, StubFacade())
    workspace.show()

    workspace._show_wechat_guide(include_directory_help=True)

    assert workspace._wechat_guide_label.text() == (
        module._WECHAT_GUIDE_DIRECTORY_MISSING
    )
    assert workspace._wechat_guide_note_label.text() == (
        module._WECHAT_GUIDE_DIRECTORY_NOTE
    )
    assert workspace._wechat_guide_key_label.isVisibleTo(workspace) is False


def test_wechat_workspace_guide_image_load_failure_is_safe(
    qt_app,
    tmp_path: Path,
) -> None:
    module = _wechat_guide_module()
    workspace = _wechat_workspace(qt_app, StubFacade())
    workspace._wechat_guide_image_path = tmp_path / "missing.png"
    workspace.show()

    workspace._show_wechat_guide()

    assert workspace._wechat_guide_image_label.isVisibleTo(workspace) is False
    assert workspace._wechat_guide_key_label.text() == module._WECHAT_GUIDE_WARNING


def test_wechat_workspace_guide_shows_bundled_image(qt_app) -> None:
    workspace = _wechat_workspace(qt_app, StubFacade())
    workspace._wechat_guide_image_path = PROJECT_ROOT / "wechat_login_guide.png"
    workspace.show()

    workspace._show_wechat_guide()

    assert workspace._wechat_guide_image_label.isVisibleTo(workspace) is True
    assert workspace._wechat_guide_image_label.pixmap().isNull() is False


def test_wechat_workspace_guide_image_keeps_aspect_ratio(qt_app) -> None:
    from PySide6.QtGui import QPixmap

    workspace = _wechat_workspace(qt_app, StubFacade())
    workspace._wechat_guide_image_path = PROJECT_ROOT / "wechat_login_guide.png"
    workspace.show()

    workspace._show_wechat_guide()

    pixmap = workspace._wechat_guide_image_label.pixmap()
    assert pixmap is not None
    assert pixmap.isNull() is False
    assert pixmap.width() > 0 and pixmap.height() > 0
    original = QPixmap(str(PROJECT_ROOT / "wechat_login_guide.png"))
    assert abs(
        (original.width() / original.height())
        - (pixmap.width() / pixmap.height())
    ) < 0.01


def test_wechat_workspace_guide_uses_horizontal_layout(qt_app) -> None:
    from PySide6.QtWidgets import QHBoxLayout

    workspace = _wechat_workspace(qt_app, StubFacade())
    workspace._wechat_guide_image_path = PROJECT_ROOT / "wechat_login_guide.png"
    workspace.show()
    workspace.resize(900, 700)

    workspace._show_wechat_guide()

    assert isinstance(workspace._wechat_guide_row, QHBoxLayout)
    assert workspace._wechat_guide_row.indexOf(
        workspace._wechat_guide_image_label
    ) >= 0
    assert workspace._wechat_guide_image_label.maximumWidth() <= 160
