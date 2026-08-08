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

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resources_dir() -> Path:
    """Return the directory containing bundled read-only resources."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _PROJECT_ROOT


def resource_path(relative_path: str | Path) -> Path:
    """Resolve one bundled resource in dev or PyInstaller mode."""
    return resources_dir() / Path(relative_path)


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
    )
    source = resources_dir()
    return [(str(source / name), ".") for name in names]


__all__ = [
    "APP_DATA_DIR_NAME",
    "bundled_data_files",
    "resource_path",
    "resources_dir",
    "user_data_dir",
]

