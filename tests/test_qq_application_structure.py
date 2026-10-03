"""Physical ownership and legacy import contracts for QQ application code."""

from __future__ import annotations

import ast
import importlib
from importlib.util import resolve_name
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
APPLICATION_ROOT = SRC_ROOT / "qq_chat_analyzer/application"
MOVES = {
    "qq_direct_database_import_service": "qq.qq_direct_database_import_service",
    "qq_connection_service": "qq.qq_connection_service",
    "qq_setup_service": "qq.qq_setup_service",
    "qq_environment_config": "qq.qq_environment_config",
    "qq_provider_factory": "qq.qq_provider_factory",
    "qq_process_registry": "qq.qq_process_registry",
    "connection.qq_connection_manager": "qq.qq_connection_manager",
    "connection.qq_auth_bridge": "qq.qq_auth_bridge",
    "runtime.qq_runtime_manager": "qq.qq_runtime_manager",
    "connection.models": "connection_models",
    "qq_export_import_service": "qq.qce_compat.qq_export_import_service",
    "export_task_manager": "qq.qce_compat.export_task_manager",
    "qq_transient_export": "qq.qce_compat.qq_transient_export",
}
CONTRACTS = (
    ("qq_connection_service", "qq.qq_connection_service",
     ("QQConnectionService", "QQConnectionStatus")),
    ("qq_export_import_service", "qq.qce_compat.qq_export_import_service",
     ("QQExportAcquisition", "QQExportFileMissing", "QQExportImportRequest",
      "QQExportImportService", "QQExportProgress", "QQExportProvider",
      "QQExportUnavailable")),
    ("export_task_manager", "qq.qce_compat.export_task_manager",
     ("ExportTaskManager", "ExportTaskState", "ExportTaskStatus")),
    ("runtime.qq_runtime_manager", "qq.qq_runtime_manager",
     ("QQRuntimeManager", "QQRuntimeState", "QQRuntimeStatus")),
    ("runtime", "qq.qq_runtime_manager",
     ("QQRuntimeManager", "QQRuntimeState", "QQRuntimeStatus")),
    ("connection", "qq.qq_auth_bridge", ("QQAuthBridge",)),
    ("connection", "qq.qq_connection_manager", ("QQConnectionManager",)),
    ("connection", "connection_models", ("ConnectionSnapshot", "ConnectionState")),
)
SHIM_PATHS = {
    APPLICATION_ROOT / (old.replace(".", "/") + ".py")
    for old, _, _ in CONTRACTS if old not in ("connection", "runtime")
} | {APPLICATION_ROOT / "connection/__init__.py",
     APPLICATION_ROOT / "runtime/__init__.py"}


@pytest.mark.parametrize("old,new", MOVES.items())
def test_qq_implementation_has_visible_owner(old: str, new: str) -> None:
    module = importlib.import_module(f"qq_chat_analyzer.application.{new}")
    assert Path(module.__file__).resolve() == (
        APPLICATION_ROOT / (new.replace(".", "/") + ".py")
    )
    old_path = APPLICATION_ROOT / (old.replace(".", "/") + ".py")
    if old_path not in SHIM_PATHS:
        assert not old_path.exists()


@pytest.mark.parametrize("old,new,symbols", CONTRACTS)
def test_old_new_and_application_exports_share_identity(old, new, symbols) -> None:
    legacy = importlib.import_module(f"qq_chat_analyzer.application.{old}")
    implementation = importlib.import_module(f"qq_chat_analyzer.application.{new}")
    application = importlib.import_module("qq_chat_analyzer.application")
    for name in symbols:
        assert getattr(legacy, name) is getattr(implementation, name)
        assert getattr(application, name) is getattr(implementation, name)
        assert name in application.__all__


@pytest.mark.parametrize("package", ("qq", "qq/qce_compat"))
def test_new_qq_packages_do_not_route_imports(package: str) -> None:
    tree = ast.parse(
        (APPLICATION_ROOT / package / "__init__.py").read_text(encoding="utf-8-sig")
    )
    assert all(
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for node in tree.body
    )


@pytest.mark.parametrize("path", sorted(SHIM_PATHS))
def test_legacy_qq_paths_have_no_implementation(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    assert not any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )


def test_production_imports_do_not_use_legacy_qq_paths() -> None:
    old_paths = {
        "qq_chat_analyzer.application." + name
        for name in (*MOVES, "connection", "runtime")
    }
    for path in (SRC_ROOT / "qq_chat_analyzer").rglob("*.py"):
        if path in SHIM_PATHS:
            continue
        parts = path.relative_to(SRC_ROOT).with_suffix("").parts
        package = ".".join(parts[:-1])
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = resolve_name("." * node.level + (node.module or ""), package)
                targets = [base, *(base + "." + alias.name for alias in node.names)]
            else:
                continue
            assert old_paths.isdisjoint(targets), (path, targets)
