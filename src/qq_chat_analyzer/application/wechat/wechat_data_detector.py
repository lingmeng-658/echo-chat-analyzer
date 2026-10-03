"""Detect local WeChat chat record directories for first-time setup.

Detection is deliberately cheap and conservative. It checks WeChat's default
Documents locations first, then any custom storage parent WeChat itself has
persisted. Raw account directories are exposed as *candidates*; only roots
whose database layout matches what the WeChat database provider can actually
read are returned as *valid* roots. When more than one account is found the
caller is expected to let the user choose instead of guessing.

The detector only reads directory names and marker files; it never opens a
database or a chat record, and never runs WCDB queries.
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
    return _unique_paths(
        candidate
        for candidate in candidate_wechat_data_roots(
            home=home,
            appdata=appdata,
        )
        if is_valid_wechat_data_root(candidate)
    )


def candidate_wechat_data_roots(
    *,
    home: Path | None = None,
    appdata: Path | None = None,
) -> list[Path]:
    """Return every plausible WeChat account data directory found locally.

    Candidates include old WeChat layouts that Echo cannot read. Callers that
    must not present a stale directory as usable should use
    :func:`detect_wechat_data_roots` or filter with
    :func:`is_valid_wechat_data_root`.
    """
    home_path = home or _default_home()
    appdata_path = appdata or _default_appdata()
    base_dirs: list[Path] = []
    base_dirs.extend(default_wechat_data_dirs(home_path))
    base_dirs.extend(configured_wechat_data_dirs(appdata_path))
    base_dirs.extend(registered_wechat_data_dirs())

    roots: list[Path] = []
    for base in base_dirs:
        if not base.is_dir():
            continue
        roots.extend(_expand_account_roots(base))
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
    """Return whether a directory has usable WeChat databases.

    A root is valid only when its provider-readable database directories
    contain both ``session.db`` and at least one ``message_*.db``. Legacy
    WeChat 3.x ``Msg`` folders are deliberately not valid because the bundled
    provider cannot read them.
    """
    if not path.is_dir():
        return False
    db_directories = _provider_db_directories(path)
    return (
        any(
            _is_non_empty_file(db_directory / SESSION_DB_NAME)
            for db_directory in db_directories
        )
        and any(
            any(
                _is_non_empty_file(db_file)
                for db_file in db_directory.glob(MESSAGE_DB_GLOB)
            )
            for db_directory in db_directories
        )
    )


# ---------------------------------------------------------------- internals


def _provider_db_directories(path: Path) -> list[Path]:
    """Mirror the database directories the provider actually scans."""
    directories: list[Path] = []
    if (path / SESSION_DB_NAME).is_file() or any(
        path.glob(MESSAGE_DB_GLOB)
    ):
        directories.append(path)

    try:
        storage_dirs = sorted(path.rglob(DB_STORAGE_DIR_NAME))
    except OSError:
        return directories
    for candidate in storage_dirs:
        if not candidate.is_dir():
            continue
        directories.append(candidate)
        try:
            children = sorted(candidate.iterdir())
        except OSError:
            children = []
        directories.extend(child for child in children if child.is_dir())
    return directories


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


def _is_non_empty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


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


def _default_home() -> Path:
    userprofile = os.environ.get("USERPROFILE", "").strip()
    if userprofile:
        return Path(userprofile)
    return Path.home()


__all__ = [
    "candidate_wechat_data_roots",
    "configured_wechat_data_dirs",
    "default_wechat_data_dirs",
    "detect_single_wechat_data_root",
    "detect_wechat_data_roots",
    "is_valid_wechat_data_root",
    "registered_wechat_data_dirs",
]
