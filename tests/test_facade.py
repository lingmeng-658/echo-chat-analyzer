"""Behavior tests for the ChatAnalyzerFacade application entry point."""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _facade_module():
    return importlib.import_module("qq_chat_analyzer.application.facade")


def _analysis_models():
    return importlib.import_module("qq_chat_analyzer.analysis.models")


def _dto():
    return importlib.import_module("qq_chat_analyzer.application.dto")


def _errors():
    return importlib.import_module("qq_chat_analyzer.application.errors")


class _FakeQQGroup:
    """Mirror the fields of the real QQ ExportGroup without importing it."""

    def __init__(
        self,
        group_code: str,
        group_name: str,
        member_count: int | None = None,
        last_message_time: int | None = None,
    ) -> None:
        self.group_code = group_code
        self.group_name = group_name
        self.member_count = member_count
        self.last_message_time = last_message_time


class _FakeQQFriend:
    def __init__(self, session_id: str, display_name: str, peer_uin: str) -> None:
        self.session_id = session_id
        self.display_name = display_name
        self.peer_uin = peer_uin
        self.session_type = "private"


class _FakeExportTask:
    """Mirror the minimum surface of a QCE export task snapshot."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id


class _FakeWeChatSession:
    """Mirror the fields of a real WeChat session listing."""

    def __init__(
        self,
        session_id: str,
        display_name: str,
        session_type: str = "friend",
        message_count: int | None = None,
        last_message_time: int | None = None,
    ) -> None:
        self.session_id = session_id
        self.display_name = display_name
        self.session_type = session_type
        self.message_count = message_count
        self.last_message_time = last_message_time


class _StubQQService:
    def __init__(
        self,
        groups=(),
        export_path: Path | None = None,
        error=None,
        tasks=(),
        message_range=None,
    ):
        self._groups = list(groups)
        self._export_path = export_path
        self._error = error
        self._tasks = None if tasks is None else list(tasks)
        self._message_range = message_range
        self.export_requests: list[object] = []
        self.list_calls = 0
        self.list_tasks_calls = 0
        self.range_requests: list[tuple[object, dict[str, object]]] = []

    def list_groups(self):
        self.list_calls += 1
        if self._error is not None:
            raise self._error
        return self._groups

    def list_sessions(self):
        return self.list_groups()

    def list_tasks(self):
        self.list_tasks_calls += 1
        if self._error is not None:
            raise self._error
        return self._tasks

    def export_only(self, request):
        self.export_requests.append(request)
        if self._error is not None:
            raise self._error
        return self._export_path

    def get_session_message_range(self, group_code, **kwargs):
        self.range_requests.append((group_code, kwargs))
        if self._error is not None:
            raise self._error
        return self._message_range


class _SnapshotQQService(_StubQQService):
    def __init__(self, *, acquisition, groups=()) -> None:
        super().__init__(groups=groups, export_path=acquisition.payload_path)
        self._acquisition = acquisition

    def acquire_export(self, request):
        self.export_requests.append(request)
        return self._acquisition


class _StubWeChatService:
    def __init__(
        self,
        sessions=(),
        export_path: Path | None = None,
        error=None,
        provider=None,
    ):
        self._sessions = None if sessions is None else list(sessions)
        self._export_path = export_path
        self._error = error
        self._provider = provider
        self.export_requests: list[object] = []
        self.list_calls = 0

    def list_sessions(self):
        self.list_calls += 1
        if self._error is not None:
            raise self._error
        return self._sessions

    def export_only(self, request):
        self.export_requests.append(request)
        if self._error is not None:
            raise self._error
        return self._export_path

    def provider(self):
        return self._provider


class _FakeReadProvider:
    def __init__(self, rows):
        self.rows = rows

    def read_session_rows(self, session_id):
        return self.rows


class _StubQQConnectionService:
    def __init__(self, status=None, error=None):
        self._status = status
        self._error = error
        self.check_calls = 0

    def check_status(self):
        self.check_calls += 1
        if self._error is not None:
            raise self._error
        return self._status


class _StubQQSetupService:
    def __init__(self, config=None, error=None, connect_status=None):
        self._config = config
        self._error = error
        self._connect_status = connect_status
        self.config_calls = 0
        self.connect_calls = 0

    def get_environment_config(self):
        self.config_calls += 1
        if self._error is not None:
            raise self._error
        return self._config

    def connect(self):
        self.connect_calls += 1
        if self._error is not None:
            raise self._error
        return self._connect_status


class _StubQQAuthBridge:
    def __init__(self, snapshot=None):
        self._snapshot = snapshot
        self.calls: list[int] = []

    def start_auth_flow(self, progress=None):
        self.calls.append(1)
        if progress is not None:
            progress("backend stage")
        if self._snapshot is not None:
            return self._snapshot
        connection = importlib.import_module(
            "qq_chat_analyzer.application.connection"
        )
        return connection.ConnectionSnapshot(
            state=connection.ConnectionState.WAITING_AUTH,
            source="qq",
            message="\u7b49\u5f85\u6388\u6743",
        )


class _RecordingProcessRegistry:
    def __init__(self):
        self.terminate_calls = 0

    def terminate_all(self) -> int:
        self.terminate_calls += 1
        return 1


class _StubWeChatConnectionService:
    def __init__(self, status=None, error=None):
        self._status = status
        self._error = error
        self.check_calls = 0

    def check_status(self):
        self.check_calls += 1
        if self._error is not None:
            raise self._error
        return self._status


class _LazySourceBundle:
    """One lazily built source with service/connection/setup slots."""

    def __init__(
        self,
        service: object | None = None,
        connection: object | None = None,
        setup: object | None = None,
    ) -> None:
        self.service = service
        self.connection = connection
        self.setup = setup


def _reports(message_count: int = 2):
    models = _analysis_models()
    return models.AnalysisReports(
        activity=models.ActivityReport(
            total_message_count=message_count,
            dated_message_count=message_count,
            hourly_counts=tuple(
                models.HourlyActivity(hour=hour, count=0) for hour in range(24)
            ),
            weekday_counts=tuple(
                models.WeekdayActivity(weekday=day, count=0) for day in range(7)
            ),
            busiest_hour=9,
            busiest_weekday=0,
        ),
        user_profiles=models.UserProfileReport(
            total_message_count=message_count,
            speaker_count=1,
            profiles=(
                models.UserProfile(
                    speaker="Fictional-Alice",
                    message_count=message_count,
                    message_share_percent=100.0,
                    average_length=5.0,
                    max_length=7,
                ),
            ),
        ),
        conversations=models.ConversationReport(conversation_count=1),
    )


def _result(message_count: int = 2):
    dto = _dto()
    return dto.AnalysisResultDTO(
        status=dto.AnalysisStatus.COMPLETED,
        processed_message_count=message_count,
        valid_text_count=message_count,
        top_words=(dto.WordFrequencyDTO(word="deck", count=3),),
        reports=_reports(message_count),
    )


class _StubAnalysisService:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.requests: list[object] = []

    def execute(self, request):
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._result


class _ConversationSummaryAnalysisService:
    """Exercise the real summary/presentation name consumers for one session."""

    def __init__(self, conversation_id: str) -> None:
        self._conversation_id = conversation_id

    def execute(self, request):
        message_module = importlib.import_module("qq_chat_analyzer.message")
        analyzer_module = importlib.import_module(
            "qq_chat_analyzer.analysis.analyzers.conversation_analyzer"
        )
        report = analyzer_module.ConversationAnalyzer().analyze(
            [
                message_module.ChatMessage(
                    timestamp=1704099600,
                    sender="Fictional Sender",
                    message_type="text",
                    text="Fictional message",
                    conversation_id=self._conversation_id,
                )
            ],
            conversation_names=request.conversation_names,
        )
        dto = _dto()
        return dto.AnalysisResultDTO(
            status=dto.AnalysisStatus.COMPLETED,
            processed_message_count=1,
            valid_text_count=1,
            reports=_analysis_models().AnalysisReports(conversations=report),
        )


class _RecordingBuilder:
    def __init__(self, view=None):
        self.calls: list[object] = []
        self._view = view

    def build(self, reports, top_words=()):
        self.calls.append((reports, tuple(top_words)))
        if self._view is not None:
            return self._view
        presentation = importlib.import_module("qq_chat_analyzer.presentation")
        return presentation.build_dashboard_view(reports, top_words=top_words)


def _facade(**overrides):
    module = _facade_module()
    defaults = {
        "analysis_service": _StubAnalysisService(result=_result()),
    }
    defaults.update(overrides)
    return module.ChatAnalyzerFacade(**defaults)


def _export_file(tmp_path: Path, name: str = "export.json") -> Path:
    path = tmp_path / name
    path.write_text('{"messages": []}', encoding="utf-8")
    return path


# --------------------------------------------------------------- data models


def test_chat_source_covers_every_supported_origin() -> None:
    module = _facade_module()

    assert {source.value for source in module.ChatSource} == {
        "qq",
        "wechat",
        "local_file",
    }


def test_facade_models_are_frozen_dataclasses() -> None:
    module = _facade_module()

    for model_type in (
        module.SessionInfo,
        module.SourceInfo,
        module.AnalysisConfig,
        module.AnalysisOutcome,
    ):
        assert dataclasses.is_dataclass(model_type)

    session = module.SessionInfo(
        source=module.ChatSource.QQ,
        session_id="fictional-1",
        display_name="Fictional Group",
    )
    try:
        session.session_id = "changed"
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - guards the immutability contract
        raise AssertionError("SessionInfo should be immutable")


def test_analysis_config_has_no_acquaintance_field() -> None:
    module = _facade_module()

    field_names = {
        field.name for field in dataclasses.fields(module.AnalysisConfig)
    }

    assert "start_time" in field_names
    assert "end_time" in field_names
    assert "scope_mode" in field_names
    assert {"top", "profile", "output_directory"} <= field_names
    for forbidden in (
        "acquaintance_time",
        "known_since",
        "relationship_duration",
        "first_met",
    ):
        assert forbidden not in field_names


def test_analysis_config_copy_sets_output_directory(tmp_path: Path) -> None:
    module = _facade_module()

    config = module.AnalysisConfig(top=10)
    updated = config.with_output_directory(tmp_path)

    assert config.output_directory is None
    assert updated.output_directory == tmp_path
    assert updated.top == 10


# ------------------------------------------------------------------ listing


def test_list_sources_flags_unwired_sources() -> None:
    module = _facade_module()
    facade = _facade(qq_service=_StubQQService())

    sources = {info.source: info for info in facade.list_sources()}

    assert sources[module.ChatSource.QQ].available is True
    assert sources[module.ChatSource.WECHAT].available is False
    assert sources[module.ChatSource.WECHAT].description != ""
    assert sources[module.ChatSource.LOCAL_FILE].available is True


def test_list_sessions_converts_qq_groups_into_session_info() -> None:
    module = _facade_module()
    service = _StubQQService(
        groups=[
            _FakeQQGroup(
                "10001",
                "Fictional Board Games",
                member_count=12,
                last_message_time=1700003600,
            ),
            _FakeQQGroup("10002", "Fictional Study Room"),
        ]
    )
    facade = _facade(qq_service=service)

    sessions = facade.list_sessions(module.ChatSource.QQ)

    assert service.list_calls == 1
    assert [session.session_id for session in sessions] == ["10001", "10002"]
    assert sessions[0].display_name == "Fictional Board Games"
    assert sessions[0].source is module.ChatSource.QQ
    assert sessions[0].session_type == "group"
    assert sessions[0].message_count == 12
    assert sessions[0].last_message_time == 1700003600
    assert sessions[1].message_count is None


def test_list_sessions_keeps_qq_private_sessions_visible() -> None:
    module = _facade_module()
    service = _StubQQService(
        groups=[_FakeQQFriend("u_fictional_1", "Fictional Alice", "200001")]
    )

    sessions = _facade(qq_service=service).list_sessions(module.ChatSource.QQ)

    assert [(item.session_id, item.display_name, item.session_type) for item in sessions] == [
        ("u_fictional_1", "Fictional Alice", "private")
    ]


def test_get_qq_export_tasks_delegates_to_the_qq_service() -> None:
    tasks = [_FakeExportTask("task-1"), _FakeExportTask("task-2")]
    service = _StubQQService(tasks=tasks)
    facade = _facade(qq_service=service)

    result = facade.get_qq_export_tasks()

    assert result == tasks
    assert service.list_tasks_calls == 1


def test_get_qq_export_tasks_turns_none_into_empty_list() -> None:
    service = _StubQQService(tasks=None)
    facade = _facade(qq_service=service)

    assert facade.get_qq_export_tasks() == []
    assert service.list_tasks_calls == 1


def test_list_sessions_hides_unnamed_qq_group_id() -> None:
    module = _facade_module()
    facade = _facade(
        qq_service=_StubQQService(
            groups=[_FakeQQGroup("10099", "", member_count=3)]
        )
    )

    session = facade.list_sessions(module.ChatSource.QQ)[0]

    assert session.session_id == "10099"
    assert session.display_name == "\u672a\u77e5\u7fa4\u804a"


def test_facade_returns_qq_environment_config_for_prefill() -> None:
    module = _facade_module()
    config = module.QQEnvironmentConfig(
        runtime_directory=Path("D:/fake_runtime"),
    )
    setup = _StubQQSetupService(config=config)
    facade = _facade(qq_setup_service=setup)

    assert facade.get_qq_environment_config() is config
    assert setup.config_calls == 1


def test_connect_qq_delegates_to_the_setup_service() -> None:
    module = _facade_module()
    status = module.QQConnectionStatus(
        available=True,
        qce_running=True,
        authenticated=True,
        version="4.1.0",
        message="QQ \u5df2\u8fde\u63a5\u3002",
        action_hint="",
    )
    setup = _StubQQSetupService(connect_status=status)
    facade = _facade(qq_setup_service=setup)

    result = facade.connect_qq()

    assert setup.connect_calls == 1
    connection = importlib.import_module(
        "qq_chat_analyzer.application.connection"
    )
    assert isinstance(result, connection.ConnectionSnapshot)
    assert result.state is connection.ConnectionState.CONNECTED
    assert result.connected is True
    assert result.version == "4.1.0"
    assert result.message == "QQ \u5df2\u8fde\u63a5\u3002"


def test_start_qq_auth_flow_delegates_to_the_auth_bridge() -> None:
    module = _facade_module()
    bridge = _StubQQAuthBridge()
    facade = _facade(qq_auth_bridge=bridge)

    result = facade.start_qq_auth_flow()

    assert bridge.calls == [1]
    connection = importlib.import_module(
        "qq_chat_analyzer.application.connection"
    )
    assert isinstance(result, connection.ConnectionSnapshot)
    assert result.state is connection.ConnectionState.WAITING_AUTH


def test_start_qq_auth_flow_forwards_progress_callback() -> None:
    bridge = _StubQQAuthBridge()
    progress: list[str] = []

    _facade(qq_auth_bridge=bridge).start_qq_auth_flow(progress=progress.append)

    assert progress == ["backend stage"]


def test_shutdown_qq_runtime_terminates_recorded_processes() -> None:
    registry = _RecordingProcessRegistry()
    facade = _facade(qq_process_registry=registry)

    facade.shutdown_qq_runtime()

    assert registry.terminate_calls == 1


def test_list_sessions_converts_wechat_sessions_into_session_info() -> None:
    module = _facade_module()
    service = _StubWeChatService(
        sessions=[
            _FakeWeChatSession(
                "wxid_fictional_a",
                "Fictional Alice",
                session_type="friend",
                message_count=40,
                last_message_time=1700007200,
            ),
            _FakeWeChatSession("fictional@chatroom", "Fictional Room", "group"),
        ]
    )
    facade = _facade(wechat_service=service)

    sessions = facade.list_sessions(module.ChatSource.WECHAT)

    assert service.list_calls == 1
    assert sessions[0].session_id == "wxid_fictional_a"
    assert sessions[0].display_name == "Fictional Alice"
    assert sessions[0].source is module.ChatSource.WECHAT
    assert sessions[0].message_count == 40
    assert sessions[0].last_message_time == 1700007200
    assert sessions[1].session_type == "group"


def test_both_sources_produce_the_same_session_shape() -> None:
    module = _facade_module()
    qq_sessions = _facade(
        qq_service=_StubQQService(groups=[_FakeQQGroup("1", "Fictional QQ")])
    ).list_sessions(module.ChatSource.QQ)
    wechat_sessions = _facade(
        wechat_service=_StubWeChatService(
            sessions=[_FakeWeChatSession("2", "Fictional WeChat")]
        )
    ).list_sessions(module.ChatSource.WECHAT)

    assert type(qq_sessions[0]) is type(wechat_sessions[0])
    assert qq_sessions[0].source is not wechat_sessions[0].source


def test_list_sessions_accepts_a_plain_source_string() -> None:
    service = _StubQQService(groups=[_FakeQQGroup("1", "Fictional QQ")])
    facade = _facade(qq_service=service)

    sessions = facade.list_sessions("qq")

    assert len(sessions) == 1


def test_list_sessions_returns_empty_for_local_files() -> None:
    module = _facade_module()

    assert _facade().list_sessions(module.ChatSource.LOCAL_FILE) == []


def test_list_sessions_handles_a_source_with_no_conversations() -> None:
    module = _facade_module()
    facade = _facade(wechat_service=_StubWeChatService(sessions=[]))

    assert facade.list_sessions(module.ChatSource.WECHAT) == []


def test_list_sessions_tolerates_a_service_returning_none() -> None:
    module = _facade_module()
    facade = _facade(wechat_service=_StubWeChatService(sessions=None))

    assert facade.list_sessions(module.ChatSource.WECHAT) == []


def test_get_session_message_range_uses_qq_service_range() -> None:
    module = _facade_module()
    service = _StubQQService(message_range=(1700000000, 1700007200))
    facade = _facade(qq_service=service)

    message_range = facade.get_session_message_range(
        module.ChatSource.QQ,
        "10001",
    )

    assert message_range == (1700000000, 1700007200)


def test_get_session_message_range_uses_private_export_identity() -> None:
    module = _facade_module()
    service = _StubQQService(
        groups=[_FakeQQFriend("u_fictional_1", "Fictional Alice", "200001")],
        message_range=(1700000000, 1700007200),
    )

    message_range = _facade(qq_service=service).get_session_message_range(
        module.ChatSource.QQ,
        "u_fictional_1",
    )

    assert message_range == (1700000000, 1700007200)
    assert service.range_requests == [
        (
            "u_fictional_1",
            {
                "chat_type": 1,
                "peer_uin": "200001",
                "session_name": "Fictional Alice",
            },
        )
    ]


def test_get_session_message_range_keeps_wechat_provider_behavior() -> None:
    module = _facade_module()
    provider = _FakeReadProvider(
        [
            {"create_time": 1700000000},
            {"create_time": 1700007200},
        ]
    )
    facade = _facade(
        wechat_service=_StubWeChatService(provider=provider),
    )

    message_range = facade.get_session_message_range(
        module.ChatSource.WECHAT,
        "wxid_fictional",
    )

    assert message_range == (1700000000, 1700007200)


def test_get_session_message_range_returns_none_for_local_files() -> None:
    module = _facade_module()

    assert (
        _facade().get_session_message_range(
            module.ChatSource.LOCAL_FILE,
            "local",
        )
        is None
    )


# --------------------------------------------------------------- connection


def test_get_connection_status_delegates_to_the_connection_service() -> None:
    module = _facade_module()
    connection_service = _StubQQConnectionService(
        status=module.QQConnectionStatus(
            available=True,
            qce_running=True,
            authenticated=True,
            version="4.1.0",
            message="\u53ef\u7528",
            action_hint="\u5f00\u59cb\u5206\u6790",
        )
    )
    facade = _facade(qq_connection_service=connection_service)

    status = facade.get_connection_status(module.ChatSource.QQ)

    assert connection_service.check_calls == 1
    assert status.available is True
    assert status.qce_running is True
    assert status.authenticated is True
    assert status.version == "4.1.0"
    assert status.message != ""
    assert status.action_hint != ""


def test_get_connection_status_accepts_a_plain_source_string() -> None:
    module = _facade_module()
    connection_service = _StubQQConnectionService(
        status=module.QQConnectionStatus(
            available=False,
            qce_running=False,
            authenticated=False,
            version=None,
            message="\u4e0d\u53ef\u7528",
            action_hint="\u542f\u52a8 QQChatExporter",
        )
    )
    facade = _facade(qq_connection_service=connection_service)

    status = facade.get_connection_status("qq")

    assert status.available is False


def test_get_connection_status_without_service_raises() -> None:
    module = _facade_module()
    facade = _facade()

    try:
        facade.get_connection_status(module.ChatSource.QQ)
    except module.FacadeError as error:
        assert error.code == "source_unavailable"
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_get_connection_status_delegates_to_wechat_connection_service() -> None:
    module = _facade_module()
    connection_service = _StubWeChatConnectionService(
        status=module.WeChatConnectionStatus(
            available=True,
            data_found=True,
            db_key_available=True,
            runtime_available=True,
            message="\u5fae\u4fe1\u53ef\u7528",
            action_hint="\u5f00\u59cb\u5206\u6790",
        )
    )
    facade = _facade(wechat_connection_service=connection_service)

    status = facade.get_connection_status(module.ChatSource.WECHAT)

    assert connection_service.check_calls == 1
    assert status.available is True
    assert status.data_found is True
    assert status.db_key_available is True
    assert status.runtime_available is True
    assert status.message != ""
    assert status.action_hint != ""


def test_get_connection_status_accepts_a_wechat_source_string() -> None:
    module = _facade_module()
    connection_service = _StubWeChatConnectionService(
        status=module.WeChatConnectionStatus(
            available=False,
            data_found=False,
            db_key_available=False,
            runtime_available=False,
            message="\u4e0d\u53ef\u7528",
            action_hint="\u68c0\u67e5\u6570\u636e\u76ee\u5f55",
        )
    )
    facade = _facade(wechat_connection_service=connection_service)

    status = facade.get_connection_status("wechat")

    assert connection_service.check_calls == 1
    assert status.available is False


def test_get_connection_status_without_wechat_service_raises() -> None:
    module = _facade_module()
    facade = _facade()

    try:
        facade.get_connection_status(module.ChatSource.WECHAT)
    except module.FacadeError as error:
        assert error.code == "source_unavailable"
        assert error.source is module.ChatSource.WECHAT
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_get_connection_status_rejects_local_file_source() -> None:
    module = _facade_module()
    facade = _facade()

    try:
        facade.get_connection_status(module.ChatSource.LOCAL_FILE)
    except module.FacadeError as error:
        assert error.code == "unknown_source"
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_qq_source_usable_when_wechat_builder_raises() -> None:
    module = _facade_module()
    qq_status = module.QQConnectionStatus(
        available=True,
        qce_running=True,
        authenticated=True,
        version="4.1.0",
        message="QQ \u5df2\u8fde\u63a5",
        action_hint="",
    )
    qq_service = _StubQQService(groups=[_FakeQQGroup("10001", "Fictional")])
    qq_connection = _StubQQConnectionService(status=qq_status)
    qq_built: list[int] = []
    wechat_built: list[int] = []

    def build_qq():
        qq_built.append(1)
        return _LazySourceBundle(
            service=qq_service,
            connection=qq_connection,
        )

    def build_wechat():
        wechat_built.append(1)
        raise RuntimeError("wechat runtime missing")

    facade = module.ChatAnalyzerFacade(
        source_builders={
            module.ChatSource.QQ: build_qq,
            module.ChatSource.WECHAT: build_wechat,
        },
        analysis_service=_StubAnalysisService(result=_result()),
    )

    sessions = facade.list_sessions(module.ChatSource.QQ)
    status = facade.get_connection_status(module.ChatSource.QQ)

    assert wechat_built == []
    assert [session.session_id for session in sessions] == ["10001"]
    assert status.available is True
    assert qq_built == [1]


def test_wechat_status_usable_when_qq_builder_raises() -> None:
    module = _facade_module()
    wechat_status = module.WeChatConnectionStatus(
        available=False,
        data_found=False,
        db_key_available=False,
        runtime_available=False,
        message="\u672a\u627e\u5230\u5fae\u4fe1\u6570\u636e\u76ee\u5f55",
        action_hint="\u8bf7\u5148\u767b\u5f55\u5fae\u4fe1",
    )
    wechat_connection = _StubWeChatConnectionService(status=wechat_status)
    qq_built: list[int] = []
    wechat_built: list[int] = []

    def build_qq():
        qq_built.append(1)
        raise RuntimeError("qq runtime missing")

    def build_wechat():
        wechat_built.append(1)
        return _LazySourceBundle(connection=wechat_connection)

    facade = module.ChatAnalyzerFacade(
        source_builders={
            module.ChatSource.QQ: build_qq,
            module.ChatSource.WECHAT: build_wechat,
        },
        analysis_service=_StubAnalysisService(result=_result()),
    )

    status = facade.get_connection_status(module.ChatSource.WECHAT)

    assert qq_built == []
    assert status.available is False
    assert "\u5fae\u4fe1\u6570\u636e\u76ee\u5f55" in status.message
    assert wechat_built == [1]


def test_wechat_connection_service_errors_become_facade_errors() -> None:
    module = _facade_module()
    facade = _facade(
        wechat_connection_service=_StubWeChatConnectionService(
            error=RuntimeError("raw wechat connection failure")
        )
    )

    try:
        facade.get_connection_status(module.ChatSource.WECHAT)
    except module.FacadeError as error:
        assert error.code == "runtime_error"
        assert error.public_message.strip() != ""
        assert error.source is module.ChatSource.WECHAT
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_connection_service_errors_become_facade_errors() -> None:
    module = _facade_module()
    facade = _facade(
        qq_connection_service=_StubQQConnectionService(
            error=RuntimeError("raw connection failure")
        )
    )

    try:
        facade.get_connection_status(module.ChatSource.QQ)
    except module.FacadeError as error:
        assert error.code == "runtime_error"
        assert error.public_message.strip() != ""
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


# ----------------------------------------------------------------- analysis


def test_analyze_file_runs_analysis_then_presentation(tmp_path: Path) -> None:
    module = _facade_module()
    analysis_service = _StubAnalysisService(result=_result(message_count=5))
    builder = _RecordingBuilder()
    facade = _facade(
        analysis_service=analysis_service,
        presentation_builder=builder,
    )
    export_path = _export_file(tmp_path)

    outcome = facade.analyze_file(
        export_path,
        module.AnalysisConfig(
            top=25,
            output_directory=tmp_path / "out",
        ),
    )

    assert len(analysis_service.requests) == 1
    request = analysis_service.requests[0]
    assert request.input_path == export_path
    assert request.top == 25
    assert request.output_directory == tmp_path / "out"
    assert (tmp_path / "out").is_dir()
    assert len(builder.calls) == 1
    assert outcome.source is module.ChatSource.LOCAL_FILE
    assert outcome.session is None
    assert outcome.view.has_data is True
    assert outcome.result.processed_message_count == 5


def test_analyze_file_reports_each_analysis_stage(tmp_path: Path) -> None:
    progress: list[str] = []
    facade = _facade()

    facade.analyze_file(_export_file(tmp_path), progress=progress.append)

    assert progress == [
        "正在准备分析...",
        "正在读取聊天记录...",
        "正在处理消息...",
        "正在分析聊天内容...",
        "正在生成报告...",
        "分析完成",
    ]


def test_analyze_file_accepts_a_string_path(tmp_path: Path) -> None:
    export_path = _export_file(tmp_path)
    facade = _facade()

    outcome = facade.analyze_file(str(export_path))

    assert outcome.view is not None


def test_analyze_file_uses_defaults_without_a_config(tmp_path: Path) -> None:
    module = _facade_module()
    analysis_service = _StubAnalysisService(result=_result())
    facade = _facade(analysis_service=analysis_service)

    facade.analyze_file(_export_file(tmp_path))

    request = analysis_service.requests[0]
    assert request.top == module.DEFAULT_TOP
    assert request.output_directory.is_absolute()


def test_analyze_file_maps_profile_to_a_stopwords_file(tmp_path: Path) -> None:
    module = _facade_module()
    analysis_service = _StubAnalysisService(result=_result())
    facade = module.ChatAnalyzerFacade(
        analysis_service=analysis_service,
        stopwords_directory=tmp_path,
    )

    facade.analyze_file(
        _export_file(tmp_path),
        module.AnalysisConfig(profile="topic"),
    )

    assert analysis_service.requests[0].stopwords_path == (
        tmp_path / "stopwords_topic.txt"
    )


def test_unknown_profile_falls_back_to_the_default_stopwords(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    analysis_service = _StubAnalysisService(result=_result())
    facade = module.ChatAnalyzerFacade(
        analysis_service=analysis_service,
        stopwords_directory=tmp_path,
    )

    facade.analyze_file(
        _export_file(tmp_path),
        module.AnalysisConfig(profile="not-a-profile"),
    )

    assert analysis_service.requests[0].stopwords_path == (
        tmp_path / "stopwords.txt"
    )


def test_default_stopwords_resolve_from_resources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _facade_module()
    if hasattr(sys, "_MEIPASS"):
        monkeypatch.delattr(sys, "_MEIPASS")
    resources = importlib.import_module("qq_chat_analyzer.resources")
    analysis_service = _StubAnalysisService(result=_result())
    facade = module.ChatAnalyzerFacade(analysis_service=analysis_service)

    facade.analyze_file(
        _export_file(tmp_path),
        module.AnalysisConfig(profile="topic"),
    )

    assert analysis_service.requests[0].stopwords_path == (
        resources.resources_dir() / "stopwords_topic.txt"
    )


def test_default_stopwords_use_meipass_in_bundled_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _facade_module()
    fake_bundle = tmp_path / "bundle"
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_bundle), raising=False)
    analysis_service = _StubAnalysisService(result=_result())
    facade = module.ChatAnalyzerFacade(analysis_service=analysis_service)

    facade.analyze_file(
        _export_file(tmp_path),
        module.AnalysisConfig(profile="culture"),
    )

    assert analysis_service.requests[0].stopwords_path == (
        fake_bundle / "stopwords_culture.txt"
    )


def test_analyze_session_dispatches_to_the_qq_service(tmp_path: Path) -> None:
    module = _facade_module()
    export_path = _export_file(tmp_path, "qq_export.json")
    qq_service = _StubQQService(export_path=export_path)
    wechat_service = _StubWeChatService(export_path=export_path)
    analysis_service = _StubAnalysisService(result=_result())
    facade = _facade(
        qq_service=qq_service,
        wechat_service=wechat_service,
        analysis_service=analysis_service,
    )

    outcome = facade.analyze_session(
        module.ChatSource.QQ,
        "10001",
        module.AnalysisConfig(start_time="2024-01-01", end_time="2024-02-01"),
    )

    assert len(qq_service.export_requests) == 1
    assert wechat_service.export_requests == []
    request = qq_service.export_requests[0]
    assert request.group_code == "10001"
    assert request.start_time is None
    assert request.end_time is None
    assert analysis_service.requests[0].input_path == export_path
    assert analysis_service.requests[0].scope == module.AnalysisScope.custom(
        date(2024, 1, 1),
        date(2024, 2, 1),
    )
    assert outcome.source is module.ChatSource.QQ
    assert outcome.session.session_id == "10001"


def test_qq_snapshot_metadata_and_force_refresh_flow_through_facade(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    snapshot_path = _export_file(tmp_path, "snapshot-export.json")
    acquired_at = datetime(2026, 8, 11, 12, 30, tzinfo=timezone.utc)
    acquisition = type(
        "Acquisition",
        (),
        {
            "payload_path": snapshot_path,
            "snapshot_id": "11111111-1111-1111-1111-111111111111",
            "acquired_at": acquired_at,
            "reused_snapshot": True,
        },
    )()
    qq_service = _SnapshotQQService(acquisition=acquisition)
    analysis_service = _StubAnalysisService(result=_result())
    facade = _facade(
        qq_service=qq_service,
        analysis_service=analysis_service,
    )

    outcome = facade.analyze_session(
        module.ChatSource.QQ,
        "fictional-session",
        module.AnalysisConfig(force_refresh=True),
    )

    assert qq_service.export_requests[0].force_refresh is True
    assert analysis_service.requests[0].input_path == snapshot_path
    assert outcome.snapshot_id == "11111111-1111-1111-1111-111111111111"
    assert outcome.data_acquired_at == acquired_at
    assert outcome.snapshot_reused is True


def test_wechat_analysis_ignores_qq_force_refresh_flag(tmp_path: Path) -> None:
    module = _facade_module()
    export_path = _export_file(tmp_path, "wechat-force-refresh.json")
    wechat_service = _StubWeChatService(export_path=export_path)
    facade = _facade(wechat_service=wechat_service)

    outcome = facade.analyze_session(
        module.ChatSource.WECHAT,
        "wxid_fictional_force_refresh",
        module.AnalysisConfig(force_refresh=True),
    )

    request = wechat_service.export_requests[0]
    assert not hasattr(request, "force_refresh")
    assert request.session_id == "wxid_fictional_force_refresh"
    assert outcome.snapshot_id is None
    assert outcome.data_acquired_at is None
    assert outcome.snapshot_reused is False


def test_successful_qq_analysis_saves_scoped_history_metadata(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    history_module = importlib.import_module(
        "qq_chat_analyzer.application.report_history"
    )
    history_manager = history_module.ReportHistoryManager(
        tmp_path / "qq-history.jsonl"
    )
    result = _result(message_count=5)
    expected_view = object()
    session_id = "fictional-qq-session"
    facade = _facade(
        qq_service=_StubQQService(
            groups=[_FakeQQGroup(session_id, "Fictional QQ Group")],
            export_path=_export_file(tmp_path, "qq-history-export.json"),
        ),
        analysis_service=_StubAnalysisService(result=result),
        presentation_builder=_RecordingBuilder(view=expected_view),
        report_history_manager=history_manager,
    )

    outcome = facade.analyze_session(
        module.ChatSource.QQ,
        session_id,
        module.AnalysisConfig(
            scope_mode=module.AnalysisScopeMode.CUSTOM,
            start_time="2026-02-01",
            end_time="2026-08-11",
        ),
    )

    records = history_manager.list_records()
    assert len(records) == 1
    record = records[0]
    assert record.source == "qq"
    assert record.session_name == "Fictional QQ Group"
    assert record.session_id == session_id
    assert record.message_count == 5
    assert record.analysis_scope == "custom"
    assert record.scope_start == date(2026, 2, 1)
    assert record.scope_end == date(2026, 8, 11)
    assert record.report_generated_at.tzinfo is not None
    assert outcome.result is result
    assert outcome.view is expected_view
    assert outcome.history_saved is True
    assert outcome.history_record_id == record.analysis_id


def test_successful_qq_analysis_links_history_to_snapshot(tmp_path: Path) -> None:
    module = _facade_module()
    history_module = importlib.import_module(
        "qq_chat_analyzer.application.report_history"
    )
    snapshot_path = _export_file(tmp_path, "history-snapshot.json")
    snapshot_id = "22222222-2222-2222-2222-222222222222"
    acquisition = type(
        "Acquisition",
        (),
        {
            "payload_path": snapshot_path,
            "snapshot_id": snapshot_id,
            "acquired_at": datetime(
                2026,
                8,
                11,
                13,
                0,
                tzinfo=timezone.utc,
            ),
            "reused_snapshot": False,
        },
    )()
    history_manager = history_module.ReportHistoryManager(
        tmp_path / "snapshot-history.jsonl"
    )
    facade = _facade(
        qq_service=_SnapshotQQService(acquisition=acquisition),
        report_history_manager=history_manager,
    )

    facade.analyze_session(module.ChatSource.QQ, "fictional-session")

    assert history_manager.list_records()[0].snapshot_id == snapshot_id


def test_successful_wechat_analysis_saves_history_metadata(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    history_module = importlib.import_module(
        "qq_chat_analyzer.application.report_history"
    )
    history_manager = history_module.ReportHistoryManager(
        tmp_path / "wechat-history.jsonl"
    )
    session_id = "wxid_fictional_history"
    result = _result(message_count=8)
    facade = _facade(
        wechat_service=_StubWeChatService(
            sessions=[_FakeWeChatSession(session_id, "Fictional WeChat")],
            export_path=_export_file(tmp_path, "wechat-history-export.json"),
        ),
        analysis_service=_StubAnalysisService(result=result),
        report_history_manager=history_manager,
    )

    outcome = facade.analyze_session(module.ChatSource.WECHAT, session_id)

    record = history_manager.list_records()[0]
    assert record.source == "wechat"
    assert record.session_name == "Fictional WeChat"
    assert record.session_id == session_id
    assert record.message_count == 8
    assert record.analysis_scope == "all"
    assert record.scope_start is None
    assert record.scope_end is None
    assert record.snapshot_id is None
    assert outcome.result is result
    assert outcome.history_saved is True


def test_history_save_failure_does_not_replace_successful_analysis(
    tmp_path: Path,
    caplog,
) -> None:
    history_module = importlib.import_module(
        "qq_chat_analyzer.application.report_history"
    )
    invalid_history_path = tmp_path / "history-is-a-directory"
    invalid_history_path.mkdir()
    result = _result(message_count=3)
    expected_view = object()
    facade = _facade(
        analysis_service=_StubAnalysisService(result=result),
        presentation_builder=_RecordingBuilder(view=expected_view),
        report_history_manager=history_module.ReportHistoryManager(
            invalid_history_path
        ),
    )

    with caplog.at_level(
        "ERROR",
        logger="qq_chat_analyzer.desktop.facade",
    ):
        outcome = facade.analyze_file(_export_file(tmp_path))

    assert outcome.result is result
    assert outcome.view is expected_view
    assert outcome.history_saved is False
    assert outcome.history_record_id is None
    assert any(
        record.name == "qq_chat_analyzer.desktop.facade"
        and record.levelname == "ERROR"
        for record in caplog.records
    )


def test_facade_reads_history_through_the_application_boundary(
    tmp_path: Path,
) -> None:
    history_module = importlib.import_module(
        "qq_chat_analyzer.application.report_history"
    )
    history_manager = history_module.ReportHistoryManager(
        tmp_path / "history.jsonl"
    )
    facade = _facade(report_history_manager=history_manager)

    outcome = facade.analyze_file(_export_file(tmp_path))

    records = facade.list_analysis_history()
    assert len(records) == 1
    assert records[0].analysis_id == outcome.history_record_id
    assert facade.get_analysis_history(records[0].analysis_id) == records[0]
    assert facade.get_analysis_history("missing") is None


def test_analysis_failure_does_not_create_history(tmp_path: Path) -> None:
    module = _facade_module()
    errors = _errors()
    history_module = importlib.import_module(
        "qq_chat_analyzer.application.report_history"
    )
    history_manager = history_module.ReportHistoryManager(
        tmp_path / "history.jsonl"
    )
    facade = _facade(
        analysis_service=_StubAnalysisService(error=errors.InputPathNotFound()),
        report_history_manager=history_manager,
    )

    with pytest.raises(module.FacadeError):
        facade.analyze_file(_export_file(tmp_path))

    assert history_manager.list_records() == ()


def test_facade_without_history_manager_preserves_old_outcome_behavior(
    tmp_path: Path,
) -> None:
    outcome = _facade().analyze_file(_export_file(tmp_path))

    assert outcome.history_saved is None
    assert outcome.history_record_id is None
    assert _facade().list_analysis_history() == ()
    assert _facade().get_analysis_history("missing") is None


def test_analyze_private_qq_session_preserves_private_export_identity(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    export_path = _export_file(tmp_path, "qq_private_export.json")
    qq_service = _StubQQService(
        groups=[_FakeQQFriend("u_fictional_1", "Fictional Alice", "200001")],
        export_path=export_path,
    )

    outcome = _facade(qq_service=qq_service).analyze_session(
        module.ChatSource.QQ,
        "u_fictional_1",
    )

    request = qq_service.export_requests[0]
    assert request.chat_type == 1
    assert request.peer_uin == "200001"
    assert request.session_name == "Fictional Alice"
    assert outcome.session.display_name == "Fictional Alice"
    assert outcome.session.session_type == "private"


def test_analyze_qq_group_uses_session_name_in_conversation_summary(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    session_id = "365970690"
    display_name = "Fictional Study Group"
    qq_service = _StubQQService(
        groups=[_FakeQQGroup(session_id, display_name)],
        export_path=_export_file(tmp_path, "qq_group_export.json"),
    )

    outcome = _facade(
        qq_service=qq_service,
        analysis_service=_ConversationSummaryAnalysisService(session_id),
    ).analyze_session(module.ChatSource.QQ, session_id)

    summary = outcome.result.reports.conversations.conversations[0]
    assert summary.display_name == display_name
    assert summary.resolved_display_name == display_name
    assert outcome.view.conversation_cards[0].conversation_id == display_name


def test_analyze_qq_private_uses_friend_name_in_conversation_summary(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    session_id = "u_fictional_internal_uid"
    display_name = "Fictional Alice"
    qq_service = _StubQQService(
        groups=[_FakeQQFriend(session_id, display_name, "200001")],
        export_path=_export_file(tmp_path, "qq_private_export.json"),
    )

    outcome = _facade(
        qq_service=qq_service,
        analysis_service=_ConversationSummaryAnalysisService(session_id),
    ).analyze_session(module.ChatSource.QQ, session_id)

    summary = outcome.result.reports.conversations.conversations[0]
    assert summary.display_name == display_name
    assert summary.resolved_display_name == display_name
    assert outcome.view.conversation_cards[0].conversation_id == display_name


def test_analyze_session_applies_wechat_time_range_after_export(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    export_path = _export_file(tmp_path, "wechat_export.json")
    wechat_service = _StubWeChatService(export_path=export_path)
    analysis_service = _StubAnalysisService(result=_result())
    facade = _facade(
        wechat_service=wechat_service,
        analysis_service=analysis_service,
    )

    facade.analyze_session(
        module.ChatSource.WECHAT,
        "wxid_fictional_a",
        module.AnalysisConfig(
            start_time="2024-01-01",
            end_time="2024-02-01",
        ),
    )

    request = wechat_service.export_requests[0]
    assert request.start_time is None
    assert request.end_time is None
    assert analysis_service.requests[0].scope == module.AnalysisScope.custom(
        date(2024, 1, 1),
        date(2024, 2, 1),
    )


@pytest.mark.parametrize("source", ["QQ", "WECHAT"])
def test_invalid_custom_scope_stops_before_source_export(
    tmp_path: Path,
    source: str,
) -> None:
    module = _facade_module()
    export_path = _export_file(tmp_path)
    qq_service = _StubQQService(export_path=export_path)
    wechat_service = _StubWeChatService(export_path=export_path)
    analysis_service = _StubAnalysisService(result=_result())
    facade = _facade(
        qq_service=qq_service,
        wechat_service=wechat_service,
        analysis_service=analysis_service,
    )

    with pytest.raises(module.FacadeError) as captured:
        facade.analyze_session(
            getattr(module.ChatSource, source),
            "fictional-session",
            module.AnalysisConfig(
                scope_mode=module.AnalysisScopeMode.CUSTOM,
                start_time="2026-08-12",
                end_time="2026-08-11",
            ),
        )

    assert captured.value.code == "invalid_analysis_scope"
    assert captured.value.public_message == (
        "开始日期不能晚于结束日期，请重新选择。"
    )
    assert qq_service.export_requests == []
    assert wechat_service.export_requests == []
    assert analysis_service.requests == []


@pytest.mark.parametrize("source_name", ["QQ", "WECHAT"])
def test_source_analysis_uses_the_shared_application_scope_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_name: str,
) -> None:
    module = _facade_module()
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    export_path = tmp_path / "fictional-scoped-export.json"
    export_path.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "timestamp": "2026-01-31 23:59:59",
                        "sender": {"nickname": "Fictional Alice"},
                        "type": "text",
                        "content": {"text": "OutsideMarker"},
                    },
                    {
                        "timestamp": "2026-02-01 12:00:00",
                        "sender": {"nickname": "Fictional Alice"},
                        "type": "text",
                        "content": {"text": "InsideMarker"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    for exporter_name in (
        "export_word_frequency_csv",
        "export_word_speaker_summary_csv",
        "export_word_speaker_frequency_csv",
        "generate_word_top_speakers_chart",
        "generate_wordcloud",
    ):
        monkeypatch.setattr(service_module, exporter_name, lambda *args: None)
    source = getattr(module.ChatSource, source_name)
    services = {
        "qq_service": _StubQQService(export_path=export_path),
        "wechat_service": _StubWeChatService(export_path=export_path),
    }
    facade = module.ChatAnalyzerFacade(
        analysis_service=service_module.AnalysisApplicationService(),
        **services,
    )

    outcome = facade.analyze_session(
        source,
        "fictional-session",
        module.AnalysisConfig(
            scope_mode=module.AnalysisScopeMode.CUSTOM,
            start_time="2026-02-01",
            end_time="2026-02-01",
        ),
    )

    assert outcome.result.processed_message_count == 1
    assert outcome.result.reports.activity.total_message_count == 1
    assert {word.word for word in outcome.result.top_words} == {
        "InsideMarker"
    }


def test_analyze_session_dispatches_to_the_wechat_service(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    export_path = _export_file(tmp_path, "wechat_export.json")
    qq_service = _StubQQService(export_path=export_path)
    wechat_service = _StubWeChatService(export_path=export_path)
    facade = _facade(qq_service=qq_service, wechat_service=wechat_service)

    outcome = facade.analyze_session(
        module.ChatSource.WECHAT,
        "wxid_fictional_a",
    )

    assert len(wechat_service.export_requests) == 1
    assert qq_service.export_requests == []
    request = wechat_service.export_requests[0]
    assert request.session_id == "wxid_fictional_a"
    assert request.output_path.name.endswith(".json")
    assert outcome.source is module.ChatSource.WECHAT


def test_analyze_session_resolves_wechat_conversation_name(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    export_path = _export_file(tmp_path, "wechat_export.json")
    analysis_service = _StubAnalysisService(result=_result())
    session_id = "wxid_fictional_a"
    wechat_service = _StubWeChatService(
        export_path=export_path,
        sessions=[
            _FakeWeChatSession(
                session_id,
                "Fictional Alice",
            )
        ],
    )
    facade = module.ChatAnalyzerFacade(
        wechat_service=wechat_service,
        analysis_service=analysis_service,
    )

    outcome = facade.analyze_session(
        module.ChatSource.WECHAT,
        session_id,
    )

    assert outcome.session.display_name == "Fictional Alice"
    assert analysis_service.requests[0].conversation_names == {
        session_id: "Fictional Alice"
    }


def test_analyze_session_hides_the_intermediate_export_file(
    tmp_path: Path,
) -> None:
    module = _facade_module()
    export_path = _export_file(tmp_path)
    facade = _facade(wechat_service=_StubWeChatService(export_path=export_path))

    outcome = facade.analyze_session(module.ChatSource.WECHAT, "fictional")

    public_values = [
        getattr(outcome, field.name)
        for field in dataclasses.fields(outcome)
        if field.name != "artifact_directory"
    ]
    assert not any(isinstance(value, Path) for value in public_values)
    assert not hasattr(outcome, "export_path")


def test_analyze_session_rejects_the_local_file_source() -> None:
    module = _facade_module()
    facade = _facade()

    try:
        facade.analyze_session(module.ChatSource.LOCAL_FILE, "anything")
    except module.FacadeError as error:
        assert error.code == "session_not_supported"
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_analyze_reports_empty_data_without_crashing(tmp_path: Path) -> None:
    dto = _dto()
    empty_result = dto.AnalysisResultDTO(
        status=dto.AnalysisStatus.NO_VALID_TEXT,
        processed_message_count=0,
        valid_text_count=0,
    )
    facade = _facade(analysis_service=_StubAnalysisService(result=empty_result))

    outcome = facade.analyze_file(_export_file(tmp_path))

    assert outcome.result.processed_message_count == 0
    assert outcome.view.user_cards == ()
    assert outcome.view.conversation_cards == ()


# ------------------------------------------------------------------- errors


def test_application_errors_become_facade_errors(tmp_path: Path) -> None:
    module = _facade_module()
    errors = _errors()
    facade = _facade(
        analysis_service=_StubAnalysisService(error=errors.InputPathNotFound())
    )

    try:
        facade.analyze_file(_export_file(tmp_path))
    except module.FacadeError as error:
        assert error.code == "input_not_found"
        assert error.public_message != ""
        assert error.source is module.ChatSource.LOCAL_FILE
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_qq_provider_errors_become_facade_errors() -> None:
    module = _facade_module()

    class _QQServiceDown(Exception):
        code = "qq_service_unavailable"
        public_message = "QQ \u5bfc\u51fa\u670d\u52a1\u672a\u8fd0\u884c\u3002"

    facade = _facade(qq_service=_StubQQService(error=_QQServiceDown()))

    try:
        facade.list_sessions(module.ChatSource.QQ)
    except module.FacadeError as error:
        assert error.code == "qq_service_unavailable"
        assert error.public_message == "QQ \u5bfc\u51fa\u670d\u52a1\u672a\u8fd0\u884c\u3002"
        assert error.source is module.ChatSource.QQ
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_wechat_provider_errors_become_facade_errors() -> None:
    module = _facade_module()

    class KeyUnavailable(Exception):
        public_message = "\u65e0\u6cd5\u83b7\u53d6\u5fae\u4fe1\u5bc6\u94a5\u3002"

    facade = _facade(wechat_service=_StubWeChatService(error=KeyUnavailable()))

    try:
        facade.list_sessions(module.ChatSource.WECHAT)
    except module.FacadeError as error:
        assert error.code == "key_unavailable"
        assert error.source is module.ChatSource.WECHAT
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_unlabelled_errors_still_produce_a_safe_message() -> None:
    module = _facade_module()
    facade = _facade(wechat_service=_StubWeChatService(error=RuntimeError()))

    try:
        facade.list_sessions(module.ChatSource.WECHAT)
    except module.FacadeError as error:
        assert error.code == "runtime_error"
        assert error.public_message.strip() != ""
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_unknown_source_raises_a_facade_error() -> None:
    module = _facade_module()
    facade = _facade()

    try:
        facade.list_sessions("myspace")
    except module.FacadeError as error:
        assert error.code == "unknown_source"
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_unwired_source_raises_a_facade_error() -> None:
    module = _facade_module()
    facade = _facade()

    try:
        facade.list_sessions(module.ChatSource.QQ)
    except module.FacadeError as error:
        assert error.code == "source_unavailable"
        assert error.source is module.ChatSource.QQ
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_missing_analysis_service_raises_a_facade_error(tmp_path: Path) -> None:
    module = _facade_module()
    facade = module.ChatAnalyzerFacade()

    try:
        facade.analyze_file(_export_file(tmp_path))
    except module.FacadeError as error:
        assert error.code == "source_unavailable"
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


def test_facade_errors_are_not_re_wrapped(tmp_path: Path) -> None:
    module = _facade_module()
    original = module.FacadeError(code="already_wrapped", public_message="x")
    facade = _facade(analysis_service=_StubAnalysisService(error=original))

    try:
        facade.analyze_file(_export_file(tmp_path))
    except module.FacadeError as error:
        assert error is original
    else:  # pragma: no cover
        raise AssertionError("expected a FacadeError")


# -------------------------------------------------------- injection & layering


def test_every_collaborator_can_be_injected(tmp_path: Path) -> None:
    module = _facade_module()
    qq_service = _StubQQService(export_path=_export_file(tmp_path))
    wechat_service = _StubWeChatService()
    analysis_service = _StubAnalysisService(result=_result())
    builder = _RecordingBuilder()

    facade = module.ChatAnalyzerFacade(
        qq_service=qq_service,
        wechat_service=wechat_service,
        analysis_service=analysis_service,
        presentation_builder=builder,
    )
    facade.analyze_session(module.ChatSource.QQ, "10001")

    assert qq_service.export_requests
    assert analysis_service.requests
    assert builder.calls


def test_injected_builder_receives_reports_untouched(tmp_path: Path) -> None:
    result = _result(message_count=7)
    builder = _RecordingBuilder()
    facade = _facade(
        analysis_service=_StubAnalysisService(result=result),
        presentation_builder=builder,
    )

    facade.analyze_file(_export_file(tmp_path))

    reports, top_words = builder.calls[0]
    assert reports is result.reports
    assert top_words == result.top_words


def test_facade_falls_back_to_the_default_builder(tmp_path: Path) -> None:
    presentation = importlib.import_module("qq_chat_analyzer.presentation")
    facade = _facade()

    outcome = facade.analyze_file(_export_file(tmp_path))

    assert isinstance(outcome.view, presentation.DashboardView)


def test_facade_does_not_recompute_presentation_values() -> None:
    module = _facade_module()
    source = Path(module.__file__).read_text(encoding="utf-8")
    code_lines = [
        line
        for line in source.splitlines()
        if not line.lstrip().startswith(("#", "*"))
    ]
    code = "\n".join(code_lines)

    for forbidden in ("Counter(", "sorted(", "statistics.", "tokenize("):
        assert forbidden not in code


def test_facade_imports_no_gui_framework() -> None:
    module = _facade_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    for forbidden in ("PyQt", "PySide", "tkinter", "flask", "django"):
        assert forbidden not in source


def test_facade_is_exported_from_the_application_package() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")

    for name in (
        "ChatAnalyzerFacade",
        "ChatSource",
        "SessionInfo",
        "AnalysisConfig",
        "FacadeError",
    ):
        assert name in application.__all__
        assert hasattr(application, name)
