"""Behavior tests for resource and user-data path resolution."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_ROOT))


def _fresh_module(monkeypatch: pytest.MonkeyPatch):
    """Reload the helper so it observes the patched sys attributes."""
    for name in tuple(sys.modules):
        if name == "qq_chat_analyzer.resources" or name.startswith(
            "qq_chat_analyzer.resources."
        ):
            del sys.modules[name]
    module = importlib.import_module("qq_chat_analyzer.resources")
    monkeypatch.setattr(module.sys, "frozen", False, raising=False)
    return module


def test_resources_dir_points_at_project_root_in_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fresh_module(monkeypatch)
    if hasattr(module.sys, "_MEIPASS"):
        monkeypatch.delattr(module.sys, "_MEIPASS")

    assert module.resources_dir() == PROJECT_ROOT


def test_resources_dir_points_at_meipass_in_bundled_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fresh_module(monkeypatch)
    fake_bundle = PROJECT_ROOT / ".tmp-resources-bundle"
    monkeypatch.setattr(
        module.sys,
        "_MEIPASS",
        str(fake_bundle),
        raising=False,
    )

    assert module.resources_dir() == fake_bundle
    assert module.resource_path("stopwords.txt") == (
        fake_bundle / "stopwords.txt"
    )


def test_resource_path_resolves_bundled_stopwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fresh_module(monkeypatch)
    fake_bundle = PROJECT_ROOT / ".tmp-resources-bundle"
    monkeypatch.setattr(
        module.sys,
        "_MEIPASS",
        str(fake_bundle),
        raising=False,
    )

    assert module.resource_path("stopwords_topic.txt") == (
        fake_bundle / "stopwords_topic.txt"
    )


def test_user_data_dir_uses_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _fresh_module(monkeypatch)
    local = tmp_path / "Local"
    local.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    assert module.user_data_dir() == local / "LocalChatAnalyzer"
    assert (local / "LocalChatAnalyzer").is_dir()


def test_user_data_dir_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _fresh_module(monkeypatch)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    assert module.user_data_dir() == tmp_path / ".localchatanalyzer"
    assert (tmp_path / ".localchatanalyzer").is_dir()


def test_bundled_data_files_lists_stopwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fresh_module(monkeypatch)
    fake_bundle = PROJECT_ROOT / ".tmp-resources-bundle"
    monkeypatch.setattr(
        module.sys,
        "_MEIPASS",
        str(fake_bundle),
        raising=False,
    )

    pairs = module.bundled_data_files()

    assert pairs == [
        (str(fake_bundle / "stopwords.txt"), "."),
        (str(fake_bundle / "stopwords_topic.txt"), "."),
        (str(fake_bundle / "stopwords_culture.txt"), "."),
    ]


def test_bundled_runtime_dir_points_at_project_runtime_in_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fresh_module(monkeypatch)
    if hasattr(module.sys, "_MEIPASS"):
        monkeypatch.delattr(module.sys, "_MEIPASS")

    assert module.bundled_runtime_dir() == PROJECT_ROOT / "runtime"


def test_default_wechat_runtime_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fresh_module(monkeypatch)
    if hasattr(module.sys, "_MEIPASS"):
        monkeypatch.delattr(module.sys, "_MEIPASS")

    root = PROJECT_ROOT / "runtime" / "wechat"
    assert module.default_wechat_runtime_directory() == root
    assert module.default_wechat_wcdb_cli_path() == root / "wcdb_cli.exe"
    assert module.default_wechat_wcdb_dll_path() == root / "WCDB.dll"
    assert module.default_wechat_wx_key_dll_path() == root / "wx_key.dll"


def test_bundled_runtime_dir_points_at_meipass_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fresh_module(monkeypatch)
    fake_bundle = PROJECT_ROOT / ".tmp-runtime-bundle"
    monkeypatch.setattr(
        module.sys,
        "_MEIPASS",
        str(fake_bundle),
        raising=False,
    )

    assert module.bundled_runtime_dir() == fake_bundle / "runtime"
    assert module.default_wechat_wcdb_cli_path() == (
        fake_bundle / "runtime" / "wechat" / "wcdb_cli.exe"
    )
    assert module.default_wechat_wcdb_dll_path() == (
        fake_bundle / "runtime" / "wechat" / "WCDB.dll"
    )
