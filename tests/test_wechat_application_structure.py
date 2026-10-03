"""Physical ownership and compatibility contracts for WeChat application code."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


APPLICATION_ROOT = (
    Path(__file__).resolve().parents[1] / "src/qq_chat_analyzer/application"
)
MODULE_NAMES = (
    "wechat_connection_progress",
    "wechat_connection_service",
    "wechat_data_detector",
    "wechat_environment_config",
    "wechat_export_import_service",
    "wechat_key_service",
    "wechat_provider_factory",
    "wechat_setup_service",
)
COMPATIBILITY_MODULES = ("wechat_connection_service", "wechat_environment_config")


@pytest.mark.parametrize("name", MODULE_NAMES)
def test_wechat_implementation_lives_in_source_package(name: str) -> None:
    module = importlib.import_module(f"qq_chat_analyzer.application.wechat.{name}")
    assert Path(module.__file__).resolve() == (
        APPLICATION_ROOT / "wechat" / f"{name}.py"
    )
    if name not in COMPATIBILITY_MODULES:
        assert not (APPLICATION_ROOT / f"{name}.py").exists()


def test_wechat_package_does_not_route_imports() -> None:
    tree = ast.parse(
        (APPLICATION_ROOT / "wechat/__init__.py").read_text(encoding="utf-8-sig")
    )
    assert all(
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for node in tree.body
    )


@pytest.mark.parametrize("name", COMPATIBILITY_MODULES)
def test_legacy_wechat_module_reexports_original_public_objects(name: str) -> None:
    legacy = importlib.import_module(f"qq_chat_analyzer.application.{name}")
    implementation = importlib.import_module(
        f"qq_chat_analyzer.application.wechat.{name}"
    )
    assert legacy.__all__ == implementation.__all__
    for symbol in implementation.__all__:
        assert getattr(legacy, symbol) is getattr(implementation, symbol)
    tree = ast.parse(Path(legacy.__file__).read_text(encoding="utf-8-sig"))
    assert not any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )


def test_application_wechat_exports_keep_implementation_identity() -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    for name in application.__all__:
        if name.startswith("WeChat"):
            public_object = getattr(application, name)
            assert public_object.__module__.startswith(
                "qq_chat_analyzer.application.wechat."
            )
            implementation = importlib.import_module(public_object.__module__)
            assert public_object is getattr(implementation, name)
