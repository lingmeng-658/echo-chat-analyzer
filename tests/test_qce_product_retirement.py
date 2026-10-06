"""QCE product entrypoints stay retired; source compatibility is separate."""

from contextlib import contextmanager
from dataclasses import fields

import pytest

from qq_chat_analyzer import cli
from qq_chat_analyzer.application.errors import ApplicationServiceError
from qq_chat_analyzer.application.facade import (
    AnalysisConfig,
    ChatAnalyzerFacade,
    ChatSource,
    FacadeError,
)


@pytest.mark.parametrize(
    "arguments",
    [["qce", "list"], ["qce", "analyze", "--group", "fictional-group"]],
)
def test_cli_rejects_retired_qce_commands(arguments, monkeypatch, capsys):
    calls = []

    def build_service():
        calls.append("build")
        raise ApplicationServiceError()

    monkeypatch.setattr(cli, "_build_qce_service", build_service, raising=False)

    assert cli.main(arguments) == 2
    assert calls == []
    assert capsys.readouterr().err


def test_facade_has_no_qce_task_api():
    assert not hasattr(ChatAnalyzerFacade(), "get_qq_export_tasks")


def test_analysis_config_has_no_qce_refresh_option():
    assert "force_refresh" not in {field.name for field in fields(AnalysisConfig)}


def test_facade_rejects_export_only_qq_service(tmp_path):
    calls = []

    class LegacyQQService:
        def list_sessions(self):
            return []

        @contextmanager
        def acquired_export(self, request, progress=None):
            calls.append("export")
            payload = tmp_path / "fictional.json"
            payload.write_text('{"messages": []}', encoding="utf-8")
            yield type("Acquisition", (), {"payload_path": payload})()

    class AnalysisService:
        def execute(self, request):
            calls.append("analysis")
            raise ApplicationServiceError()

    facade = ChatAnalyzerFacade(
        qq_service=LegacyQQService(), analysis_service=AnalysisService()
    )
    with pytest.raises(FacadeError):
        facade.analyze_session(ChatSource.QQ, "fictional-group")
    assert calls == []
