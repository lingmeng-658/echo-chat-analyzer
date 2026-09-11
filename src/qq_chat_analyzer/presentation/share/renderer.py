"""Render a self-contained share HTML document into a PNG with Chromium."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


SHARE_IMAGE_WIDTH = 1200
SHARE_IMAGE_HEIGHT = 2000
_CHROMIUM_TIMEOUT_SECONDS = 60
_CLEANUP_RETRY_SECONDS = 0.2
_CLEANUP_RETRY_COUNT = 5

_LOGGER = logging.getLogger("qq_chat_analyzer.presentation.share.renderer")


class ShareImageRenderError(RuntimeError):
    """Raised when a share card cannot be rendered to PNG."""


@dataclass(frozen=True, slots=True)
class _ChromiumResult:
    """One Chromium process outcome."""

    returncode: int
    stdout: bytes
    stderr: str


def find_chromium() -> str | None:
    """Return a usable local Chromium executable, or None."""
    configured = os.environ.get("ECHO_CHROMIUM_PATH", "").strip()
    if configured:
        return configured
    for candidate in _candidate_chromium_paths():
        if Path(candidate).is_file() or shutil.which(candidate):
            return candidate
    return None


def _candidate_chromium_paths() -> tuple[str, ...]:
    if os.name == "nt":
        return (
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        )
    return (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "microsoft-edge",
    )


def render_share_html_to_png(
    html: str,
    output_path: str | Path,
    *,
    width: int = SHARE_IMAGE_WIDTH,
    height: int = SHARE_IMAGE_HEIGHT,
    chromium_path: str | None = None,
) -> Path:
    """Render one self-contained HTML card into a PNG file.

    Lifecycle: write the HTML, load it in Chromium, capture the screenshot,
    then always remove the temporary working directory.
    """
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    chromium = chromium_path or find_chromium()
    if not chromium:
        raise ShareImageRenderError(
            "No Chromium executable is available for share rendering."
        )

    temp_root = Path(
        tempfile.mkdtemp(prefix="echo-share-", dir=destination.parent)
    )
    _LOGGER.debug(
        "[renderer] start destination=%s chromium=%s temp_root=%s",
        destination,
        chromium,
        temp_root,
    )
    try:
        source = temp_root / "share-card.html"
        source.write_text(html, encoding="utf-8")
        _LOGGER.debug(
            "[renderer] html written source=%s exists=%s",
            source,
            source.exists(),
        )
        profile_directory = temp_root / "chromium-profile"
        dom_command = [
            chromium,
            *_chromium_flags(profile_directory),
            "--dump-dom",
            source.resolve().as_uri(),
        ]
        _LOGGER.debug("[renderer] DOM verification command=%r", dom_command)
        dom_result = _run_chromium(dom_command, capture_stdout=True)
        if dom_result.returncode != 0:
            raise ShareImageRenderError(
                "Chromium failed to load the share HTML."
                + _stderr_suffix(dom_result.stderr)
            )
        if b"ERR_FILE_NOT_FOUND" in dom_result.stdout:
            raise ShareImageRenderError(
                "Chromium failed to load the share HTML."
            )
        _capture_screenshot(
            chromium,
            source,
            destination,
            width=width,
            height=height,
            profile_directory=profile_directory,
        )
        _LOGGER.info("[renderer] screenshot finished destination=%s", destination)
        if not destination.is_file() or destination.stat().st_size == 0:
            raise ShareImageRenderError(
                "Chromium failed to render the share image."
            )
    finally:
        _LOGGER.debug("[renderer] cleanup start root=%s", temp_root)
        _cleanup_tree(temp_root)
        _LOGGER.debug(
            "[renderer] cleanup finished root=%s exists=%s",
            temp_root,
            temp_root.exists(),
        )
    return destination




def _capture_screenshot(
    chromium: str,
    source: Path,
    destination: Path,
    *,
    width: int,
    height: int,
    profile_directory: Path,
) -> None:
    """Run one Chromium screenshot process and surface its failure output."""
    command = _screenshot_command(
        chromium,
        source,
        destination,
        width=width,
        height=height,
        profile_directory=profile_directory,
    )
    _LOGGER.debug("[renderer] screenshot command=%r", command)
    result = _run_chromium(command, capture_stdout=False)
    destination_exists = destination.exists()
    destination_size = destination.stat().st_size if destination_exists else None
    _LOGGER.debug(
        "[renderer] screenshot finished returncode=%s stderr_tail=%r "
        "destination_exists=%s destination_size=%s",
        result.returncode,
        result.stderr[-500:],
        destination_exists,
        destination_size,
    )
    if result.returncode != 0:
        raise ShareImageRenderError(
            "Chromium failed to render the share image."
            + _stderr_suffix(result.stderr)
        )


def _screenshot_command(
    chromium: str,
    source: Path,
    destination: Path,
    *,
    width: int,
    height: int,
    profile_directory: Path,
) -> list[str]:
    return [
        chromium,
        *_chromium_flags(profile_directory),
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        f"--screenshot={destination}",
        source.resolve().as_uri(),
    ]


def _chromium_flags(profile_directory: Path) -> list[str]:
    return [
        "--headless=new",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-gpu-compositing",
        "--disable-gpu-sandbox",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile_directory}",
    ]


def _run_chromium(
    command: list[str],
    *,
    capture_stdout: bool = False,
    timeout: int = _CHROMIUM_TIMEOUT_SECONDS,
) -> _ChromiumResult:
    """Run one Chromium process and wait for it to finish completely."""
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        stdout, stderr = process.communicate()
        raise ShareImageRenderError(
            "Chromium timed out while rendering the share image."
            + _stderr_suffix(_decode_stderr(stderr))
        ) from None
    return _ChromiumResult(
        returncode=process.returncode,
        stdout=stdout or b"",
        stderr=_decode_stderr(stderr),
    )


def _kill_process_tree(process: subprocess.Popen) -> None:
    """Terminate Chromium and its child processes after a timeout."""
    if os.name != "nt":
        process.kill()
        return
    subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(process.pid)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _cleanup_tree(path: Path | None) -> None:
    """Remove the temporary working directory, retrying transient locks."""
    if path is None:
        return
    try:
        root = Path(path)
    except TypeError:
        return
    if not root.exists():
        return
    for _ in range(_CLEANUP_RETRY_COUNT):
        try:
            shutil.rmtree(root)
            return
        except OSError:
            time.sleep(_CLEANUP_RETRY_SECONDS)
    shutil.rmtree(root, ignore_errors=True)


def _stderr_suffix(stderr: str) -> str:
    tail = (stderr or "").strip()
    if not tail:
        return ""
    return f" Chromium stderr: {tail[-800:]}"


def _decode_stderr(data: bytes | None) -> str:
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")


__all__ = [
    "SHARE_IMAGE_HEIGHT",
    "SHARE_IMAGE_WIDTH",
    "ShareImageRenderError",
    "find_chromium",
    "render_share_html_to_png",
]
