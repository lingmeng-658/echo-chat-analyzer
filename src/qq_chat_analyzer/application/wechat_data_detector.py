"""Detect local WeChat chat record directories for first-time setup.

Detection is deliberately cheap and conservative. It checks WeChat's default
Documents locations first, then any custom storage parent WeChat itself has
persisted, validates the WeChat data structure of every candidate account
directory, and returns all valid candidates. When more than one account is
found the caller is expected to let the user choose instead of guessing.

The detector only reads directory names and marker files; it never opens a
database or a chat record.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any


XWECHAT_DIR_NAME = "xwechat_files"
WECHAT_FILES_DIR_NAME = "WeChat Files"
DEFAULT_DATA_DIR_NAMES = (XWECHAT_DIR_NAME, WECHAT_FILES_DIR_NAME)
ACCOUNT_PREFIXES = ("wxid_", "wx_")
SESSION_DB_NAME = "session.db"
MESSAGE_DB_GLOB = "message_*.db"
DB_STORAGE_DIR_NAME = "db_storage"
MSG_DIR_NAME = "Msg"


def detect_wechat_data_roots(
    *,
    home: Path | None = None,
    appdata: Path | None = None,
) -> list[Path]:
    """Return every valid WeChat account data directory found locally.

    Candidates are ordered by detection priority: default Documents
    locations first, then paths WeChat itself has saved for a custom storage
    location. Duplicates are removed and only structurally valid roots are
    returned.
    """
    home_path = home or Path.home()
    appdata_path = appdata or _default_appdata()
    base_dirs: list[Path] = []
    base_dirs.extend(default_wechat_data_dirs(home_path))
    base_dirs.extend(configured_wechat_data_dirs(appdata_path))
    base_dirs.extend(registered_wechat_data_dirs())

    roots: list[Path] = []
    for base in base_dirs:
        if not base.is_dir():
            continue
        roots.extend(
            candidate
            for candidate in _expand_account_roots(base)
            if is_valid_wechat_data_root(candidate)
        )
    return _unique_paths(roots)


def detect_single_wechat_data_root(
    *,
    home: Path | None = None,
    appdata: Path | None = None,
) -> Path | None:
    """Return the only valid root, or ``None`` when there are 0 or many."""
    roots = detect_wechat_data_roots(home=home, appdata=appdata)
    if len(roots) == 1:
        return roots[0]
    return None


def default_wechat_data_dirs(home: Path) -> list[Path]:
    """Return WeChat's default data parent directories under Documents."""
    return [
        home / "Documents" / name
        for name in DEFAULT_DATA_DIR_NAMES
    ]


def configured_wechat_data_dirs(appdata: Path) -> list[Path]:
    """Return custom storage parents WeChat has persisted in its config."""
    result: list[Path] = []
    config_dir = appdata / "Tencent" / "xwechat" / "config"
    for ini_file in sorted(config_dir.glob("*.ini")):
        path = _read_plain_path(ini_file)
        if path is not None:
            result.append(path)

    legacy_dir = appdata / "Tencent" / "WeChat" / "All Users" / "config"
    for ini_file in sorted(legacy_dir.glob("*.ini")):
        path = _read_ini_path(ini_file, "FileSavePath")
        if path is not None:
            result.append(path)
    return result


def registered_wechat_data_dirs() -> list[Path]:
    """Best-effort registry read of WeChat's custom storage parent."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except Exception:  # pragma: no cover - platform dependent
        return []
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Tencent\WeChat",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "FileSavePath")
    except OSError:
        return []
    if isinstance(value, str) and value.strip():
        return [Path(value.strip())]
    return []


def is_valid_wechat_data_root(path: Path) -> bool:
    """Return whether a directory has WeChat data structure markers."""
    if not path.is_dir():
        return False
    if (path / SESSION_DB_NAME).is_file():
        return True

    db_storage = path / DB_STORAGE_DIR_NAME
    if db_storage.is_dir() and (
        (db_storage / SESSION_DB_NAME).is_file()
        or any(db_storage.glob(MESSAGE_DB_GLOB))
    ):
        return True

    msg_dir = path / MSG_DIR_NAME
    if msg_dir.is_dir() and any(msg_dir.glob("*.db")):
        return True
    return False


# ---------------------------------------------------------------- internals


def _expand_account_roots(base: Path) -> list[Path]:
    candidates: list[Path] = [base]
    for name in DEFAULT_DATA_DIR_NAMES:
        nested = base / name
        if nested.is_dir():
            candidates.append(nested)

    roots: list[Path] = []
    for root_dir in candidates:
        if _looks_like_account_dir(root_dir):
            roots.append(root_dir)
        try:
            children = sorted(root_dir.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and _looks_like_account_dir(child):
                roots.append(child)
    return roots


def _looks_like_account_dir(path: Path) -> bool:
    name = path.name.lower()
    return any(name.startswith(prefix) for prefix in ACCOUNT_PREFIXES)


def _read_plain_path(path: Path) -> Path | None:
    text = _read_text(path)
    if text is None:
        return None
    candidate = text.strip().strip('"').strip()
    if not candidate or not Path(candidate).is_absolute():
        return None
    return Path(candidate)


def _read_ini_path(path: Path, key: str) -> Path | None:
    text = _read_text(path)
    if text is None:
        return None
    for line in text.splitlines():
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip().lower() != key.lower():
            continue
        candidate = value.strip().strip('"').strip()
        if candidate and Path(candidate).is_absolute():
            return Path(candidate)
    return None


def _read_text(path: Path) -> str | None:
    for encoding in ("utf-8", "gbk"):
        try:
            text = path.read_text(encoding=encoding, errors="replace")
            return text.lstrip("\ufeff")
        except OSError:
            continue
    return None


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(os.path.normpath(str(path)))
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _default_appdata() -> Path:
    value = os.environ.get("APPDATA", "").strip()
    if value:
        return Path(value)
    return Path.home() / "AppData" / "Roaming"


__all__ = [
    "configured_wechat_data_dirs",
    "default_wechat_data_dirs",
    "detect_single_wechat_data_root",
    "detect_wechat_data_roots",
    "is_valid_wechat_data_root",
    "registered_wechat_data_dirs",
]
