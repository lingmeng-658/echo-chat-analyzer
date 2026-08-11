"""Behavior tests for the PySide6 GUI layer.

These tests never open a real window: Qt runs on the ``offscreen`` platform
and every facade call is served by a stub. The GUI is verified as a pure
consumer of the facade.
"""

from __future__ import annotations

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
from PySide6.QtWidgets import QApplication  # noqa: E402


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
    ):
        self._sources = tuple(sources)
        self._sessions = list(sessions)
        self._outcome = outcome
        self._error = error
        self._connection_status = connection_status
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
        self.get_session_message_range_calls: list[tuple] = []
        self.analyze_session_calls: list[tuple] = []
        self.analyze_file_calls: list[tuple] = []

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
        return self._qq_snapshot()

    def start_qq_auth_flow(self, progress=None):
        self.start_qq_auth_flow_calls.append(1)
        if progress is not None:
            progress("正在加载 NapCat...")
        if self._connect_qq_error is not None:
            raise self._connect_qq_error
        return self._qq_snapshot()

    def get_qq_connection_snapshot(self):
        self.get_qq_connection_snapshot_calls.append(1)
        if self._connection_error is not None:
            raise self._connection_error
        return self._qq_snapshot()

    def shutdown_qq_runtime(self):
        self.shutdown_qq_runtime_calls.append(1)

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
    ):
        self.view = view
        self.history_saved = history_saved
        self.data_acquired_at = data_acquired_at


def _analysis_page(qt_app, facade, executor=None, qq_qrcode_path=None):
    module = importlib.import_module("qq_chat_analyzer.gui.analysis_page")
    return module.AnalysisPage(
        facade,
        executor=executor or _inline_executor(),
        qq_qrcode_path=qq_qrcode_path,
    )


def _dashboard_page(qt_app):
    module = importlib.import_module("qq_chat_analyzer.gui.dashboard_page")
    return module.DashboardPage()


def _main_window(qt_app, facade, executor=None):
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    return module.MainWindow(facade, executor=executor or _inline_executor())


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

    assert window.stack.count() == 3
    assert window.windowTitle() != ""
    assert window.stack.currentIndex() == 0


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
    assert page._wechat_connect_button.text() == "\u91cd\u65b0\u8fde\u63a5\u5fae\u4fe1"


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
    assert page._hint_label.text() == (
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
    assert page._hint_label.text() == "\u6b63\u5728\u7b49\u5f85\u5fae\u4fe1\u767b\u5f55..."
    assert received == ["\u6b63\u5728\u8fde\u63a5\u5fae\u4fe1..."]


def test_wechat_connect_progress_shows_database_read_stage(qt_app) -> None:
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)

    page._handle_wechat_connect_progress("\u6b63\u5728\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u5e93...")

    assert page._status_label.text() == "\u6b63\u5728\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u5e93..."
    assert page._hint_label.text() == "\u6b63\u5728\u8bfb\u53d6\u5fae\u4fe1\u6570\u636e\u5e93..."


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

    visible = page._status_label.text() + page._hint_label.text()
    assert "Key \u83b7\u53d6\u5931\u8d25" in visible
    assert "\u91cd\u65b0\u5b89\u88c5" not in visible


def test_wechat_hook_failure_keeps_the_classified_reason(qt_app) -> None:
    facade = StubFacade(sources=_wechat_available_sources())
    page = _analysis_page(qt_app, facade)

    page._handle_wechat_connect_error(
        "wechat_hook_failed",
        "\u5fae\u4fe1 Hook \u5931\u8d25\uff0c\u5f53\u524d\u5fae\u4fe1\u8fdb\u7a0b\u53ef\u80fd\u4e0d\u517c\u5bb9\u3002",
    )

    assert "Hook \u5931\u8d25" in page._hint_label.text()
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
    assert page._hint_label.text() == "\u8bf7\u5148\u8fde\u63a5 QQ\u3002"


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
    assert "不要手动打开QQ" in page._hint_label.text()


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


def test_clicking_qq_connect_through_the_real_worker_updates_the_page(
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

    page._qq_connect_button.click()
    _settle_workers()

    assert facade.start_qq_auth_flow_calls == [1]
    assert page._session_list.count() == 1
    assert "\u5df2\u8fde\u63a5" in page._status_label.text()
    assert "\u91cd\u65b0\u8fde\u63a5QQ" in page._qq_connect_button.text()
    assert page._qq_connect_button.isEnabled() is True


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


def test_qq_ready_shows_reconnect_button_and_loads_sessions(
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

    assert page._qq_connect_button.isVisibleTo(page) is True
    assert page._qq_connect_button.isEnabled() is True
    assert "\u91cd\u65b0\u8fde\u63a5QQ" in page._qq_connect_button.text()
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
        in page._hint_label.text()
    )
    assert "Traceback" not in page._hint_label.text()
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
        page._hint_label.text()
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
    assert "\u91cd\u65b0\u8fde\u63a5QQ" in page._qq_connect_button.text()


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
    assert "raw provider failure" not in page._hint_label.text()


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
    assert "保持在登录界面" in page._wechat_guide_label.text()
    assert "不要进入聊天页面" in page._wechat_guide_label.text()
    assert "\u4e0d\u4e0a\u4f20" in page._wechat_guide_label.text()
    assert "\u4e0d\u4fdd\u5b58" in page._wechat_guide_label.text()
    assert "LCA" not in page._wechat_guide_label.text()


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
    assert "\u5982\u679c\u672a\u81ea\u52a8\u8bc6\u522b\u5fae\u4fe1\u6570\u636e\u76ee\u5f55" in (
        page._wechat_guide_label.text()
    )
    assert "\u5b58\u50a8\u6587\u4ef6\u5939" in page._wechat_guide_label.text()


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
        page._hint_label.text()
    )
    assert "Traceback" not in page._hint_label.text()


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
    assert page._hint_label.text() != ""


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
    assert page._hint_label.text() == message
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


def test_successful_analysis_switches_to_the_dashboard(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    view = _dashboard_view()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        outcome=_StubOutcome(view),
        qq_setup_status=_qq_setup_status(
            configured=True,
            runtime_available=True,
        ),
        qq_runtime_status=_qq_runtime_status(state="running"),
    )
    window = _main_window(qt_app, facade)
    window.analysis_page.select_source(module.ChatSource.QQ)
    _drain(window.analysis_page)
    window.analysis_page._session_list.setCurrentRow(0)

    window.analysis_page.start_analysis()
    _drain(window.analysis_page)

    assert window.stack.currentIndex() == 2
    assert window.dashboard_page._user_table.rowCount() == 1


def test_show_outcome_accepts_a_bare_view(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_outcome(_dashboard_view())

    assert window.stack.currentIndex() == 2


@pytest.mark.parametrize(
    ("history_saved", "expected_status"),
    [
        (True, "分析已保存"),
        (False, "分析完成，但历史记录保存失败。"),
        (None, "分析完成"),
    ],
)
def test_show_outcome_reports_history_save_status_after_rendering(
    qt_app,
    sources,
    history_saved,
    expected_status,
) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_outcome(
        _StubOutcome(_dashboard_view(), history_saved=history_saved)
    )

    assert window.stack.currentIndex() == 2
    assert window.dashboard_page._user_table.rowCount() == 1
    assert window.statusBar().currentMessage() == expected_status


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

    assert window.statusBar().currentMessage() == (
        "\u5206\u6790\u5df2\u4fdd\u5b58"
        " \u00b7 \u6570\u636e\u83b7\u53d6\u65f6\u95f4\uff1a"
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

    assert window.stack.currentIndex() == 1
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
    assert window.stack.currentIndex() == 0
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

    assert window.stack.currentIndex() == 0
    assert window.analysis_page._analysis_running is False
    assert window.analysis_page._analyze_button.isEnabled() is True
    assert "\u865a\u6784\u5206\u6790\u5931\u8d25" in window.analysis_page._hint_label.text()


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
    assert page._hint_label.text() == "\u5fae\u4fe1\u5bfc\u51fa\u4e0d\u53ef\u7528\u3002"


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
    assert "连接QQ后" in item.text()
    assert not (item.flags() & Qt.ItemFlag.ItemIsSelectable)


def test_connecting_source_shows_loading_placeholder(qt_app, sources) -> None:
    page = _qq_page_in_state(
        qt_app,
        sources,
        _qq_snapshot("starting"),
    )

    assert page._session_list.count() == 1
    assert "正在加载聊天列表" in page._session_list.item(0).text()


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

    assert page._hint_label.text() == action_hint
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

    assert page._hint_label.text() == "\u5171 1 \u4e2a\u4f1a\u8bdd\u3002"
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
    assert "不要手动启动QQ" in text
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
    assert page._qq_connect_button.text() == "\u91cd\u65b0\u8fde\u63a5QQ"
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
    assert "正在加载聊天列表" in page._session_list.item(0).text()

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
