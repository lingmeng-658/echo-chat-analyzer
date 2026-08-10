"""Tests for WeChat chat record directory auto-detection.

Every directory and path here is fabricated in temp folders; the real user
profile and WeChat config are never touched.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _module():
    return importlib.import_module(
        "qq_chat_analyzer.application.wechat_data_detector"
    )


def _xwechat_account(base: Path, wxid: str) -> Path:
    """Create one valid WeChat 4.x account directory."""
    account = base / "xwechat_files" / wxid
    db_storage = account / "db_storage"
    db_storage.mkdir(parents=True)
    (db_storage / "session.db").write_bytes(b"fake")
    return account


def _legacy_account(base: Path, wxid: str) -> Path:
    """Create one valid WeChat 3.x account directory."""
    account = base / "WeChat Files" / wxid
    msg_dir = account / "Msg"
    msg_dir.mkdir(parents=True)
    (msg_dir / "MSG0.db").write_bytes(b"fake")
    return account


def test_default_documents_location_detected(tmp_path: Path) -> None:
    module = _module()
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    root = _xwechat_account(home / "Documents", "wxid_fake_a")

    detected = module.detect_wechat_data_roots(home=home, appdata=appdata)

    assert detected == [root]
    assert module.detect_single_wechat_data_root(
        home=home,
        appdata=appdata,
    ) == root


def test_custom_config_location_detected(tmp_path: Path) -> None:
    module = _module()
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    base = tmp_path / "custom_storage"
    root = _xwechat_account(base, "wxid_fake_b")
    config_dir = appdata / "Tencent" / "xwechat" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "custom.ini").write_text(str(base), encoding="utf-8")

    detected = module.detect_wechat_data_roots(home=home, appdata=appdata)

    assert detected == [root]


def test_custom_config_ignores_utf8_bom(tmp_path: Path) -> None:
    module = _module()
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    base = tmp_path / "custom_storage"
    root = _xwechat_account(base, "wxid_fake_bom")
    config_dir = appdata / "Tencent" / "xwechat" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "bom.ini").write_bytes(
        b"\xef\xbb\xbf" + str(base).encode("utf-8")
    )

    detected = module.detect_wechat_data_roots(home=home, appdata=appdata)

    assert detected == [root]


def test_legacy_wechat_files_config_detected(tmp_path: Path) -> None:
    module = _module()
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    base = tmp_path / "legacy_storage"
    root = _legacy_account(base, "wxid_fake_c")
    config_dir = appdata / "Tencent" / "WeChat" / "All Users" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "3ebffe94.ini").write_text(
        f"FileSavePath={base}",
        encoding="utf-8",
    )

    detected = module.detect_wechat_data_roots(home=home, appdata=appdata)

    assert root in detected


def test_no_valid_directories_returns_empty(tmp_path: Path) -> None:
    module = _module()
    home = tmp_path / "home"
    (home / "Documents" / "xwechat_files").mkdir(parents=True)
    appdata = tmp_path / "appdata"

    assert module.detect_wechat_data_roots(
        home=home,
        appdata=appdata,
    ) == []
    assert (
        module.detect_single_wechat_data_root(
            home=home,
            appdata=appdata,
        )
        is None
    )


def test_multiple_accounts_return_all_without_guessing(
    tmp_path: Path,
) -> None:
    module = _module()
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    first = _xwechat_account(home / "Documents", "wxid_fake_a")
    second = _xwechat_account(home / "Documents", "wxid_fake_b")

    detected = module.detect_wechat_data_roots(home=home, appdata=appdata)

    assert sorted(detected) == sorted([first, second])
    assert (
        module.detect_single_wechat_data_root(
            home=home,
            appdata=appdata,
        )
        is None
    )


def test_duplicate_candidates_are_deduplicated(tmp_path: Path) -> None:
    module = _module()
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    root = _xwechat_account(home / "Documents", "wxid_fake_a")
    config_dir = appdata / "Tencent" / "xwechat" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "same.ini").write_text(
        str(home / "Documents"),
        encoding="utf-8",
    )

    detected = module.detect_wechat_data_roots(home=home, appdata=appdata)

    assert detected == [root]


def test_validity_requires_wechat_data_markers(tmp_path: Path) -> None:
    module = _module()
    empty = tmp_path / "empty"
    empty.mkdir()
    plain = tmp_path / "plain"
    (plain / "db_storage").mkdir(parents=True)

    assert module.is_valid_wechat_data_root(empty) is False
    assert module.is_valid_wechat_data_root(plain) is False


def test_configured_dirs_ignore_missing_config(tmp_path: Path) -> None:
    module = _module()
    appdata = tmp_path / "appdata"

    assert module.configured_wechat_data_dirs(appdata) == []
