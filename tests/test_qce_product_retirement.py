"""QCE product entrypoints stay retired; file-format retirement is covered separately."""

from contextlib import contextmanager
from dataclasses import fields
import importlib
from pathlib import Path

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


RETIRED_MODULES = (
    "qq_chat_analyzer.providers.qq_chat_exporter_provider",
    "qq_chat_analyzer.application.qq.qce_compat",
    "qq_chat_analyzer.application.qq.qce_compat.qq_export_import_service",
    "qq_chat_analyzer.application.qq.qce_compat.export_task_manager",
    "qq_chat_analyzer.application.qq.qce_compat.qq_transient_export",
    "qq_chat_analyzer.application.qq_export_import_service",
    "qq_chat_analyzer.application.export_task_manager",
)


@pytest.mark.parametrize("module_name", RETIRED_MODULES)
def test_retired_qce_modules_cannot_be_imported(module_name):
    with pytest.raises(ModuleNotFoundError) as caught:
        importlib.import_module(module_name)
    assert module_name == caught.value.name or module_name.startswith(
        caught.value.name + "."
    )


def test_retired_qce_modules_are_physically_absent():
    source_root = Path(__file__).resolve().parents[1] / "src"
    for module_name in RETIRED_MODULES:
        path = source_root.joinpath(*module_name.split("."))
        assert not path.with_suffix(".py").exists()
        assert not path.exists()


@pytest.mark.parametrize(
    "package_name, retired_names",
    [
        (
            "qq_chat_analyzer.application",
            {
                "QQExportAcquisition", "QQExportFileMissing", "QQExportImportRequest",
                "QQExportImportService", "QQExportProgress", "QQExportProvider",
                "QQExportUnavailable", "ExportTaskManager", "ExportTaskState",
                "ExportTaskStatus",
            },
        ),
        (
            "qq_chat_analyzer.providers",
            {
                "DEFAULT_BASE_URL", "ExportGroup", "ExportTask", "ExportTaskCancelled",
                "ExportTaskFailed", "ExportTaskLimitReached", "ExportTimeout",
                "QQChatExporterError", "QQChatExporterProvider", "RequestFailed",
                "ServiceHealth", "ServiceUnavailable", "TaskNotFound", "TokenUnavailable",
                "read_token", "resolve_security_candidates", "resolve_security_path",
            },
        ),
    ],
)
def test_public_packages_do_not_export_qce_types(package_name, retired_names):
    package = importlib.import_module(package_name)
    assert retired_names.isdisjoint(package.__all__)
    assert not any(hasattr(package, name) for name in retired_names)
