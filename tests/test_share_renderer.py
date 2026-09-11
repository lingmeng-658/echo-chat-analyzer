"""Behavior tests for Chromium-based share PNG rendering."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest


def _renderer():
    return importlib.import_module("qq_chat_analyzer.presentation.share.renderer")


def test_configured_chromium_path_wins(monkeypatch) -> None:
    module = _renderer()
    monkeypatch.setenv("ECHO_CHROMIUM_PATH", "C:/custom/chrome.exe")

    assert module.find_chromium() == "C:/custom/chrome.exe"


def test_windows_candidate_paths_prefer_chrome(monkeypatch) -> None:
    module = _renderer()
    monkeypatch.setattr(module.os, "name", "nt")

    candidates = module._candidate_chromium_paths()

    assert "chrome.exe" in candidates[0].lower()
    assert any("msedge.exe" in candidate.lower() for candidate in candidates)


def test_render_runs_dom_check_then_screenshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _renderer()
    output_path = tmp_path / "echo-share.png"
    calls: list[tuple[list[str], bool]] = []

    def _fake_run_chromium(command, *, capture_stdout=False, timeout=60):
        calls.append((command, capture_stdout))
        if "--dump-dom" in command:
            return module._ChromiumResult(
                returncode=0,
                stdout=(
                    b'<html><title>Echo</title>'
                    b'<main class="card"></main></html>'
                ),
                stderr="",
            )
        output_path.write_bytes(b"fake-png")
        return module._ChromiumResult(returncode=0, stdout=b"", stderr="")

    monkeypatch.setattr(module, "find_chromium", lambda: "C:/chrome.exe")
    monkeypatch.setattr(module, "_run_chromium", _fake_run_chromium)

    result = module.render_share_html_to_png("<html>share</html>", output_path)

    assert result == output_path
    assert output_path.read_bytes() == b"fake-png"
    assert len(calls) == 2
    dom_command, dom_capture = calls[0]
    screenshot_command, screenshot_capture = calls[1]
    assert "--dump-dom" in dom_command
    assert dom_command[-1].startswith("file:///")
    assert dom_capture is True
    assert any(
        part.startswith("--screenshot=") for part in screenshot_command
    )
    assert screenshot_command[-1].startswith("file:///")
    assert screenshot_capture is False
    assert "--user-data-dir=" in " ".join(dom_command)
    assert "--user-data-dir=" in " ".join(screenshot_command)


def test_render_without_chromium_raises(tmp_path: Path, monkeypatch) -> None:
    module = _renderer()
    monkeypatch.setattr(module, "find_chromium", lambda: None)

    with pytest.raises(module.ShareImageRenderError):
        module.render_share_html_to_png(
            "<html>share</html>",
            tmp_path / "echo-share.png",
        )


def test_render_failed_load_includes_stderr(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _renderer()

    def _fake_run_chromium(command, **kwargs):
        return module._ChromiumResult(
            returncode=1,
            stdout=b"",
            stderr="boom: file not found",
        )

    monkeypatch.setattr(module, "find_chromium", lambda: "C:/chrome.exe")
    monkeypatch.setattr(module, "_run_chromium", _fake_run_chromium)

    with pytest.raises(module.ShareImageRenderError) as exc:
        module.render_share_html_to_png(
            "<html>share</html>",
            tmp_path / "echo-share.png",
        )

    assert "boom: file not found" in str(exc.value)
    assert not (tmp_path / "echo-share.png").exists()


def test_render_rejects_error_page_dom(tmp_path: Path, monkeypatch) -> None:
    module = _renderer()
    calls: list[list[str]] = []

    def _fake_run_chromium(command, **kwargs):
        calls.append(command)
        return module._ChromiumResult(
            returncode=0,
            stdout=b"<html>ERR_FILE_NOT_FOUND</html>",
            stderr="",
        )

    monkeypatch.setattr(module, "find_chromium", lambda: "C:/chrome.exe")
    monkeypatch.setattr(module, "_run_chromium", _fake_run_chromium)

    with pytest.raises(module.ShareImageRenderError):
        module.render_share_html_to_png(
            "<html>share</html>",
            tmp_path / "echo-share.png",
        )

    assert len(calls) == 1
    assert "--dump-dom" in calls[0]
    assert not (tmp_path / "echo-share.png").exists()


def test_render_failure_cleans_temporary_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _renderer()

    def _fake_run_chromium(command, **kwargs):
        raise module.ShareImageRenderError("boom")

    monkeypatch.setattr(module, "find_chromium", lambda: "C:/chrome.exe")
    monkeypatch.setattr(module, "_run_chromium", _fake_run_chromium)

    with pytest.raises(module.ShareImageRenderError):
        module.render_share_html_to_png(
            "<html>share</html>",
            tmp_path / "echo-share.png",
        )

    assert list(tmp_path.glob("echo-share-*")) == []


def test_run_chromium_timeout_kills_process_tree(monkeypatch) -> None:
    module = _renderer()
    taskkill_calls: list[list[str]] = []

    class _FakeProcess:
        pid = 4242

        def __init__(self) -> None:
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("chromium", timeout)
            return b"", b"timeout stderr"

    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeProcess(),
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: taskkill_calls.append(args[0])
        or subprocess.CompletedProcess(args[0], 0),
    )

    with pytest.raises(module.ShareImageRenderError) as exc:
        module._run_chromium(["chrome", "--dump-dom"])

    assert "timed out" in str(exc.value)
    assert "timeout stderr" in str(exc.value)
    assert taskkill_calls
    assert "/T" in taskkill_calls[0]
    assert "/F" in taskkill_calls[0]
    assert "4242" in taskkill_calls[0]


@pytest.mark.skipif(
    importlib.import_module(
        "qq_chat_analyzer.presentation.share.renderer"
    ).find_chromium()
    is None,
    reason="no local Chromium available",
)
def test_real_chromium_renders_a_png(tmp_path: Path) -> None:
    module = _renderer()
    share = importlib.import_module("qq_chat_analyzer.presentation.share")
    html = share.build_share_card_html(
        share.ShareCardData(
            has_data=True,
            message_count_display="8,438",
            time_span_display="302 天",
        )
    )
    output_path = tmp_path / "echo-share.png"

    result = module.render_share_html_to_png(html, output_path)

    assert result.is_file()
    assert result.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert result.stat().st_size > 1000
    assert list(tmp_path.glob("echo-share-*")) == []

    from PIL import Image

    pixels = list(Image.open(result).convert("RGB").getdata())
    paperish = sum(
        1
        for red, green, blue in pixels
        if 225 <= red <= 252
        and 218 <= green <= 248
        and 200 <= blue <= 245
    )
    assert paperish / len(pixels) > 0.5
