"""Contract tests for the stable application-layer public API."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def test_application_package_exports_analysis_application_service() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )

    assert hasattr(application, "AnalysisApplicationService")
    public_service = application.AnalysisApplicationService
    assert public_service is service_module.AnalysisApplicationService
    assert "AnalysisApplicationService" in application.__all__
    assert callable(public_service.execute)


def test_application_package_exports_qq_connection_types() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.qq_connection_service"
    )

    assert application.QQConnectionService is service_module.QQConnectionService
    assert application.QQConnectionStatus is service_module.QQConnectionStatus
    assert "QQConnectionService" in application.__all__
    assert "QQConnectionStatus" in application.__all__
    assert callable(application.QQConnectionService.check_status)


def test_application_package_exports_qq_snapshot_acquisition() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.qq_export_import_service"
    )

    assert application.QQExportAcquisition is service_module.QQExportAcquisition
    assert "QQExportAcquisition" in application.__all__
    assert callable(application.QQExportImportService.acquire_export)


def test_application_package_exports_wechat_connection_types() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.wechat_connection_service"
    )

    assert (
        application.WeChatConnectionService
        is service_module.WeChatConnectionService
    )
    assert (
        application.WeChatConnectionStatus
        is service_module.WeChatConnectionStatus
    )
    assert "WeChatConnectionService" in application.__all__
    assert "WeChatConnectionStatus" in application.__all__
    assert callable(application.WeChatConnectionService.check_status)


def test_application_package_exports_wechat_environment_config() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    config_module = importlib.import_module(
        "qq_chat_analyzer.application.wechat_environment_config"
    )

    assert (
        application.WeChatEnvironmentConfig
        is config_module.WeChatEnvironmentConfig
    )
    assert (
        application.WeChatEnvironmentConfigLoader
        is config_module.WeChatEnvironmentConfigLoader
    )
    assert (
        application.WeChatConfigNotFound
        is config_module.WeChatConfigNotFound
    )
    assert (
        application.WeChatConfigCorrupted
        is config_module.WeChatConfigCorrupted
    )
    for name in (
        "WeChatEnvironmentConfig",
        "WeChatEnvironmentConfigLoader",
        "WeChatConfigNotFound",
        "WeChatConfigCorrupted",
        "WeChatEnvironmentConfigError",
    ):
        assert name in application.__all__


def test_application_package_exports_export_task_types() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    manager_module = importlib.import_module(
        "qq_chat_analyzer.application.export_task_manager"
    )

    assert application.ExportTaskManager is manager_module.ExportTaskManager
    assert application.ExportTaskStatus is manager_module.ExportTaskStatus
    assert application.ExportTaskState is manager_module.ExportTaskState
    for name in (
        "ExportTaskManager",
        "ExportTaskState",
        "ExportTaskStatus",
    ):
        assert name in application.__all__
    assert callable(application.ExportTaskManager.start_export)
    assert callable(application.ExportTaskManager.get_status)
    assert callable(application.ExportTaskManager.wait_for_completion)


def test_application_package_exports_runtime_manager_types() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    manager_module = importlib.import_module(
        "qq_chat_analyzer.application.runtime.qq_runtime_manager"
    )

    assert application.QQRuntimeManager is manager_module.QQRuntimeManager
    assert application.QQRuntimeStatus is manager_module.QQRuntimeStatus
    assert application.QQRuntimeState is manager_module.QQRuntimeState
    for name in (
        "QQRuntimeManager",
        "QQRuntimeState",
        "QQRuntimeStatus",
    ):
        assert name in application.__all__
    assert callable(application.QQRuntimeManager.start)
    assert callable(application.QQRuntimeManager.stop)
    assert callable(application.QQRuntimeManager.get_status)
    assert callable(application.QQRuntimeManager.is_available)


def test_application_package_exports_chat_data_snapshot_types() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    snapshot_module = importlib.import_module(
        "qq_chat_analyzer.application.chat_data_snapshot"
    )

    assert (
        application.ChatDataSnapshotManager
        is snapshot_module.ChatDataSnapshotManager
    )
    assert application.ChatDataSnapshot is snapshot_module.ChatDataSnapshot
    assert application.ChatDataSource is snapshot_module.ChatDataSource
    assert application.SnapshotStatus is snapshot_module.SnapshotStatus
    for name in (
        "ChatDataSnapshot",
        "ChatDataSnapshotManager",
        "ChatDataSource",
        "SnapshotCleanupError",
        "SnapshotPayloadState",
        "SnapshotSaveError",
        "SnapshotStatus",
        "SnapshotValidation",
    ):
        assert name in application.__all__
    assert callable(application.ChatDataSnapshotManager.save_snapshot)
    assert callable(application.ChatDataSnapshotManager.list_snapshots)
    assert callable(application.ChatDataSnapshotManager.validate_snapshot)
    assert callable(application.ChatDataSnapshotManager.remove_payload)


def test_runtime_package_exports_bundled_runtime_surface() -> None:
    runtime_package = importlib.import_module("qq_chat_analyzer.runtime")

    assert hasattr(runtime_package, "BundledQQRuntime")
    assert hasattr(runtime_package, "QQRuntimeConfig")
    assert hasattr(runtime_package, "QQChatRuntimeError")
    assert callable(runtime_package.ChatRuntime.wait_ready)
    assert callable(runtime_package.BundledQQRuntime.wait_ready)
