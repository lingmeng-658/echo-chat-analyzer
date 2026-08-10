"""Best-effort control of QCE's internal WebUI auto-open behavior.

The bundled QCE plugin announces its WebUI URL after the API server is ready
and, by default, opens it in the system browser. LCA does not need that page:
its provider reads ``security.json`` directly and the GUI renders the login
QR from the runtime cache, so the browser window is pure noise here.

The plugin gates the browser launch on ``autoOpenBrowser`` in
``~/.qq-chat-exporter/user-config.json`` (missing value defaults to true).
This module writes that setting while preserving every other key the user
already configured. It never raises: a failed write only leaves QCE's
default behavior in place.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


QCE_CONFIG_DIR_NAME = ".qq-chat-exporter"
QCE_USER_CONFIG_FILENAME = "user-config.json"

_LOGGER = logging.getLogger("qq_chat_analyzer.desktop.qq_webui_config")


def qce_user_config_path() -> Path:
    """Return the QCE user config file the plugin reads on startup."""
    return Path.home() / QCE_CONFIG_DIR_NAME / QCE_USER_CONFIG_FILENAME


def disable_qce_auto_open_browser(
    config_path: Path | None = None,
) -> bool:
    """Disable QCE's auto-open browser behavior, preserving other settings.

    Returns ``True`` when the setting was persisted. Any filesystem or JSON
    failure is swallowed and reported as ``False`` so runtime startup never
    depends on this best-effort step.
    """
    path = config_path or qce_user_config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _load_payload(path)
        payload["autoOpenBrowser"] = False
        body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(body, encoding="utf-8")
    except Exception:
        _LOGGER.warning(
            "[qq webui] failed to disable auto-open config=%s",
            path,
            exc_info=True,
        )
        return False
    _LOGGER.info("[qq webui] auto-open browser disabled config=%s", path)
    return True


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


__all__ = [
    "QCE_CONFIG_DIR_NAME",
    "QCE_USER_CONFIG_FILENAME",
    "disable_qce_auto_open_browser",
    "qce_user_config_path",
]
