"""Behavior tests for the PySide6 GUI layer.

These tests never open a real window: Qt runs on the ``offscreen`` platform
and every facade call is served by a stub. The GUI is verified as a pure
consumer of the facade.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="PySide6 is required for the GUI layer")

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
        setup_status=None,
        setup_error=None,
    ):
        self._sources = tuple(sources)
        self._sessions = list(sessions)
        self._outcome = outcome
        self._error = error
        self._connection_status = connection_status
        self._connection_error = connection_error
        self._setup_status = setup_status
        self._setup_error = setup_error
        self.list_sessions_calls: list[object] = []
        self.get_connection_status_calls: list[object] = []
        self.get_wechat_setup_status_calls: list[object] = []
        self.setup_wechat_environment_calls: list[object] = []
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

    def analyze_session(self, source, session_id, config=None):
        self.analyze_session_calls.append((source, session_id, config))
        if self._error is not None:
            raise self._error
        return self._outcome

    def analyze_file(self, path, config=None):
        self.analyze_file_calls.append((path, config))
        if self._error is not None:
            raise self._error
        return self._outcome


def _session(source, session_id: str, display_name: str, count=None):
    module = _facade_module()
    return module.SessionInfo(
        source=source,
        session_id=session_id,
        display_name=display_name,
        message_count=count,
    )


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
    def __init__(self, view):
        self.view = view


def _analysis_page(qt_app, facade):
    module = importlib.import_module("qq_chat_analyzer.gui.analysis_page")
    return module.AnalysisPage(facade, executor=_inline_executor())


def _dashboard_page(qt_app):
    module = importlib.import_module("qq_chat_analyzer.gui.dashboard_page")
    return module.DashboardPage()


def _main_window(qt_app, facade):
    module = importlib.import_module("qq_chat_analyzer.gui.main_window")
    return module.MainWindow(facade, executor=_inline_executor())


def _inline_executor():
    """Run facade calls on the calling thread.

    The GUI defaults to a real thread pool. Tests inject this instead so no
    test depends on thread scheduling or on a Qt event loop turn.
    """
    module = importlib.import_module("qq_chat_analyzer.gui.workers")
    return module.run_inline


def _drain(page):
    """No-op: the injected executor already ran everything synchronously."""
    return None


# ------------------------------------------------------------ initialization


def test_main_window_builds_both_pages(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    assert window.stack.count() == 2
    assert window.windowTitle() != ""
    assert window.stack.currentIndex() == 0


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
        message="\u5df2\u8fde\u63a5 QQChatExporter\u3002",
        action_hint="\u53ef\u4ee5\u5f00\u59cb\u5bfc\u51fa\u3002",
    )
    facade = StubFacade(sources=sources, connection_status=status)

    page = _analysis_page(qt_app, facade)
    _drain(page)

    assert facade.get_connection_status_calls == [module.ChatSource.QQ]
    assert page._status_label.isVisibleTo(page) is True
    assert "\u5df2\u8fde\u63a5" in page._status_label.text()
    assert "\u5df2\u8fde\u63a5 QQChatExporter\u3002" in page._status_label.text()
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
        message="\u672a\u68c0\u6d4b\u5230 QQChatExporter \u670d\u52a1\u3002",
        action_hint="\u8bf7\u5148\u542f\u52a8 QQChatExporter\u3002",
    )
    facade = StubFacade(sources=sources, connection_status=status)

    page = _analysis_page(qt_app, facade)
    _drain(page)

    assert facade.get_connection_status_calls == [module.ChatSource.QQ]
    assert page._status_label.isVisibleTo(page) is True
    assert "\U0001F534" in page._status_label.text()
    assert "\u672a\u68c0\u6d4b\u5230 QQChatExporter \u670d\u52a1\u3002" in (
        page._status_label.text()
    )
    assert page._status_label.toolTip() == "\u8bf7\u5148\u542f\u52a8 QQChatExporter\u3002"


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
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert facade.get_connection_status_calls == [
        module.ChatSource.QQ,
        module.ChatSource.QQ,
    ]
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
        "\U0001F7E2 \u5fae\u4fe1\u6570\u636e\u5df2\u5c31\u7eea"
    )


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
    assert page._session_list.count() == 0
    assert page._status_label.text() == (
        "\U0001F534 \u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e"
    )
    assert page._status_label.toolTip() == (
        "\u8bf7\u767b\u5f55\u5fae\u4fe1\u6216\u914d\u7f6e\u6570\u636e\u76ee\u5f55\u3002"
    )
    assert page._hint_label.text() == (
        "\u8bf7\u767b\u5f55\u5fae\u4fe1\u6216\u914d\u7f6e\u6570\u636e\u76ee\u5f55\u3002"
    )
    assert page._analyze_button.isEnabled() is False


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
        action_hint="\u8bf7\u5148\u542f\u52a8 QQChatExporter\u3002",
    )
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
        connection_status=status,
    )
    page = _analysis_page(qt_app, facade)
    _drain(page)

    page.select_source(module.ChatSource.QQ)
    _drain(page)

    assert facade.list_sessions_calls == []
    assert page._session_list.count() == 0
    assert page._hint_label.text() == "\u8bf7\u5148\u542f\u52a8 QQChatExporter\u3002"


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
    assert page._session_list.count() == 0
    assert received == []
    assert page._status_label.text() == "\u65e0\u6cd5\u786e\u8ba4\u8fde\u63a5\u72b6\u6001\u3002"
    assert "raw provider failure" not in page._status_label.text()
    assert "raw provider failure" not in page._hint_label.text()


def test_wechat_unconfigured_shows_setup_entry(qt_app) -> None:
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

    assert page._wechat_setup_button.isVisibleTo(page) is True
    assert "\u5fae\u4fe1\u73af\u5883\u8bbe\u7f6e" in page._wechat_setup_button.text()


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
    assert "\u5fae\u4fe1\u6570\u636e\u6e90\u53ef\u7528" in page._status_label.text()


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

    assert len(buttons) == 3
    assert buttons[module.ChatSource.QQ].isEnabled() is True
    assert buttons[module.ChatSource.LOCAL_FILE].isEnabled() is True


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

    assert page._session_list.count() == 0
    assert page._hint_label.text() != ""


# ------------------------------------------------------------------ analysis


def test_analyze_button_stays_disabled_until_a_session_is_chosen(
    qt_app,
    sources,
) -> None:
    module = _facade_module()
    facade = StubFacade(
        sources=sources,
        sessions=[_session(module.ChatSource.QQ, "10001", "\u865a\u6784\u7fa4")],
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


def test_time_range_is_optional(qt_app, sources) -> None:
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    config = page.build_config()

    assert config.start_time is None
    assert config.end_time is None


def test_enabled_time_range_reaches_the_config(qt_app, sources) -> None:
    page = _analysis_page(qt_app, StubFacade(sources=sources))

    page._start_enabled.setChecked(True)
    page._end_enabled.setChecked(True)
    config = page.build_config()

    assert config.start_time is not None
    assert config.end_time is not None


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
    )
    window = _main_window(qt_app, facade)
    window.analysis_page.select_source(module.ChatSource.QQ)
    _drain(window.analysis_page)
    window.analysis_page._session_list.setCurrentRow(0)

    window.analysis_page.start_analysis()
    _drain(window.analysis_page)

    assert window.stack.currentIndex() == 1
    assert window.dashboard_page._user_table.rowCount() == 1


def test_show_outcome_accepts_a_bare_view(qt_app, sources) -> None:
    window = _main_window(qt_app, StubFacade(sources=sources))

    window.show_outcome(_dashboard_view())

    assert window.stack.currentIndex() == 1


# -------------------------------------------------------------------- errors


def test_facade_errors_surface_as_public_messages(qt_app, sources) -> None:
    module = _facade_module()
    error = module.FacadeError(
        code="wechat_export_unavailable",
        public_message="\u5fae\u4fe1\u5bfc\u51fa\u4e0d\u53ef\u7528\u3002",
    )
    facade = StubFacade(sources=sources, error=error)
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
    facade = StubFacade(sources=sources, error=RuntimeError("boom internal"))
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
