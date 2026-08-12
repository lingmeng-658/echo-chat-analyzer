"""Resolve read-only application resources and user-writable data paths.

Development runs look up bundled text files next to the package root.
PyInstaller builds look inside ``sys._MEIPASS`` so the same helper works in
both environments. User data always lives outside the install directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DATA_DIR_NAME = "LocalChatAnalyzer"
RUNTIME_DIR_NAME = "runtime"
QQ_RUNTIME_DIR_NAME = "qq"
QQ_QCE_FILE_NAME = "qce-server.exe"
QQ_STATIC_RELATIVE_PATH = "static/qce"
QQ_NAPCAT_DIR_NAME = "napcat"
WECHAT_RUNTIME_DIR_NAME = "wechat"
WECHAT_WCDB_CLI_FILE_NAME = "wcdb_cli.exe"
WECHAT_WCDB_DLL_FILE_NAME = "WCDB.dll"
WECHAT_WX_KEY_DLL_FILE_NAME = "wx_key.dll"
WECHAT_LOGIN_GUIDE_FILE_NAME = "wechat_login_guide.png"

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RuntimeResourceError(Exception):
    """Raised when the packaged external runtime directory is unavailable."""

    code = "runtime_directory_missing"
    public_message = "运行组件不完整，请重新下载并解压完整的 Echo 安装包。"

    def __init__(self) -> None:
        self.public_message = type(self).public_message
        super().__init__(self.public_message)


def resources_dir() -> Path:
    """Return the directory containing bundled read-only resources."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _PROJECT_ROOT


def resource_path(relative_path: str | Path) -> Path:
    """Resolve one bundled resource in dev or PyInstaller mode."""
    return resources_dir() / Path(relative_path)


def bundled_runtime_dir() -> Path:
    """Return the stable directory holding external chat runtimes.

    PyInstaller-internal resources may live under ``sys._MEIPASS``, but QQ
    and WeChat launch child processes that require a stable on-disk location.
    Frozen builds therefore resolve them beside the executable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / RUNTIME_DIR_NAME
    return _PROJECT_ROOT / RUNTIME_DIR_NAME


def require_bundled_runtime_dir() -> Path:
    """Return the external runtime directory or raise a user-safe error."""
    directory = bundled_runtime_dir()
    if not directory.is_dir():
        raise RuntimeResourceError()
    return directory


def default_qq_runtime_directory() -> Path:
    """Return the expected bundled QQ runtime directory."""
    return bundled_runtime_dir() / QQ_RUNTIME_DIR_NAME


def default_qq_qce_path() -> Path:
    """Return the expected bundled ``qce-server.exe`` path."""
    return default_qq_runtime_directory() / QQ_QCE_FILE_NAME


def default_qq_static_directory() -> Path:
    """Return the expected bundled QCE static frontend directory."""
    return default_qq_runtime_directory() / QQ_STATIC_RELATIVE_PATH


def default_qq_napcat_directory() -> Path:
    """Return the expected bundled NapCat directory."""
    return default_qq_runtime_directory() / QQ_NAPCAT_DIR_NAME


def default_wechat_runtime_directory() -> Path:
    """Return the expected bundled WeChat runtime directory."""
    return bundled_runtime_dir() / WECHAT_RUNTIME_DIR_NAME


def default_wechat_wcdb_cli_path() -> Path:
    """Return the expected bundled ``wcdb_cli.exe`` path."""
    return default_wechat_runtime_directory() / WECHAT_WCDB_CLI_FILE_NAME


def default_wechat_wcdb_dll_path() -> Path:
    """Return the expected bundled ``WCDB.dll`` path."""
    return default_wechat_runtime_directory() / WECHAT_WCDB_DLL_FILE_NAME


def default_wechat_wx_key_dll_path() -> Path:
    """Return the expected bundled ``wx_key.dll`` path."""
    return default_wechat_runtime_directory() / WECHAT_WX_KEY_DLL_FILE_NAME


def default_wechat_login_guide_path() -> Path:
    """Return the bundled image used by the WeChat login guide."""
    return resource_path(WECHAT_LOGIN_GUIDE_FILE_NAME)


def user_data_dir() -> Path:
    """Return the user-writable application data directory, creating it."""
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        directory = Path(local_app_data) / APP_DATA_DIR_NAME
    else:
        directory = Path.home() / f".{APP_DATA_DIR_NAME.lower()}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def bundled_data_files(
    relative_paths: tuple[str, ...] | list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return PyInstaller ``(source, dest)`` pairs for bundled resources."""
    names = tuple(relative_paths or ()) or (
        "stopwords.txt",
        "stopwords_topic.txt",
        "stopwords_culture.txt",
        WECHAT_LOGIN_GUIDE_FILE_NAME,
    )
    source = resources_dir()
    return [(str(source / name), ".") for name in names]


__all__ = [
    "APP_DATA_DIR_NAME",
    "RuntimeResourceError",
    "bundled_data_files",
    "bundled_runtime_dir",
    "default_qq_napcat_directory",
    "default_qq_qce_path",
    "default_qq_runtime_directory",
    "default_qq_static_directory",
    "default_wechat_runtime_directory",
    "default_wechat_login_guide_path",
    "default_wechat_wcdb_cli_path",
    "default_wechat_wcdb_dll_path",
    "default_wechat_wx_key_dll_path",
    "resource_path",
    "require_bundled_runtime_dir",
    "resources_dir",
    "user_data_dir",
]
