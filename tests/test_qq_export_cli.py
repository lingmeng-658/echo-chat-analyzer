"""CLI tests for the ``qce`` pre-dispatch commands.

No real QCE service is contacted: the provider is always a stub, and every
export file is fictional data written by the test itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer import cli as cli_module
from qq_chat_analyzer.application import (
    ApplicationServiceError,
    QQExportImportService,
)


# --------------------------------------------------------------------- fixtures


class _StubGroup:
    def __init__(self, group_code: str, group_name: str, member_count: int | None) -> None:
        self.group_code = group_code
        self.group_name = group_name
        self.member_count = member_count


class _ListProvider:
    """Provider stub that only answers group listing."""

    def __init__(self, groups: list[_StubGroup] | None = None) -> None:
        self._groups = groups or []
        self.list_calls = 0

    def list_groups(self):
        self.list_calls += 1
        return self._groups

    def export_group_json(self, group_code, start_time=None, end_time=None):
        raise AssertionError("export must not be called for qce list")


class _BoomError(ApplicationServiceError):
    code = "qce_service_unreachable"
    public_message = "QQChatExporter \u670d\u52a1\u672a\u8fd0\u884c\u3002"


class _FailingListProvider:
    def list_groups(self):
        raise _BoomError()

    def export_group_json(self, group_code, start_time=None, end_time=None):
        raise _BoomError()


def _qce_message(message_id: str, text: str, nickname: str) -> dict:
    return {
        "id": message_id,
        "seq": message_id,
        "timestamp": 1750000000000,
        "time": "2025-06-15 12:00:00",
        "sender": {"uid": "user-1", "uin": "1", "nickname": nickname},
        "type": "text",
        "content": {"text": text, "elements": [], "resources": [], "mentions": []},
        "recalled": False,
        "system": False,
    }


def _write_fake_export(path: Path) -> Path:
    payload = {
        "metadata": {"exportedAt": "2025-06-15T12:00:00Z", "version": "4.0.0"},
        "chatInfo": {"chatType": 2, "peerUid": "700000001", "name": "Fictional Group"},
        "statistics": {"totalMessages": 3},
        "messages": [
            _qce_message("fake-1", "\u4eca\u5929\u5929\u6c14\u5f88\u597d \u5929\u6c14\u5f88\u597d", "Fictional Alice"),
            _qce_message("fake-2", "\u5929\u6c14\u5f88\u597d \u9002\u5408\u51fa\u95e8", "Fictional Bob"),
            _qce_message("fake-3", "\u9002\u5408\u51fa\u95e8 \u4eca\u5929\u5929\u6c14", "Fictional Alice"),
        ],
        "avatars": {},
        "exportOptions": {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class _ExportProvider:
    """Provider stub that returns a pre-written fictional export file."""

    def __init__(self, export_path: Path) -> None:
        self._export_path = export_path
        self.export_calls: list[tuple[str, object, object]] = []

    def list_groups(self):
        return []

    def export_group_json(self, group_code, start_time=None, end_time=None):
        self.export_calls.append((group_code, start_time, end_time))
        return self._export_path


# ------------------------------------------------------------------- qce list


def test_qce_list_prints_groups(monkeypatch, capsys) -> None:
    provider = _ListProvider(
        [
            _StubGroup("700000001", "Fictional Group A", 42),
            _StubGroup("700000002", "Fictional Group B", None),
        ]
    )
    monkeypatch.setattr(cli_module, "_build_qce_service", lambda: QQExportImportService(provider))

    exit_code = cli_module.main(["qce", "list"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert provider.list_calls == 1
    assert "700000001" in captured.out
    assert "Fictional Group A" in captured.out
    assert "700000002" in captured.out


def test_qce_list_reports_empty_result(monkeypatch, capsys) -> None:
    provider = _ListProvider([])
    monkeypatch.setattr(cli_module, "_build_qce_service", lambda: QQExportImportService(provider))

    exit_code = cli_module.main(["qce", "list"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "\u672a\u627e\u5230" in captured.out


def test_qce_list_translates_provider_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_module, "_build_qce_service", lambda: QQExportImportService(_FailingListProvider())
    )

    exit_code = cli_module.main(["qce", "list"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "QQChatExporter" in captured.err


# ---------------------------------------------------------------- qce analyze


def test_qce_analyze_runs_full_pipeline(monkeypatch, capsys, tmp_path) -> None:
    export_path = _write_fake_export(tmp_path / "fake-export.json")
    provider = _ExportProvider(export_path)
    monkeypatch.setattr(cli_module, "_build_qce_service", lambda: QQExportImportService(provider))
    output_dir = tmp_path / "out"

    exit_code = cli_module.main(
        ["qce", "analyze", "--group", "700000001", "--output-dir", str(output_dir)]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert provider.export_calls and provider.export_calls[0][0] == "700000001"
    assert "\u5904\u7406\u6d88\u606f\u6570\u91cf" in captured.out
    assert output_dir.exists()


def test_qce_analyze_requires_group(capsys) -> None:
    exit_code = cli_module.main(["qce", "analyze"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--group" in captured.err


def test_qce_analyze_translates_provider_error(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(
        cli_module, "_build_qce_service", lambda: QQExportImportService(_FailingListProvider())
    )

    exit_code = cli_module.main(
        ["qce", "analyze", "--group", "700000001", "--output", str(tmp_path / "out")]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err.strip()


# ------------------------------------------------------------ unknown / legacy


def test_unknown_qce_subcommand_is_rejected(capsys) -> None:
    exit_code = cli_module.main(["qce", "nope"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.err.strip()


def test_legacy_cli_behaviour_is_unchanged(tmp_path, capsys) -> None:
    """A plain positional invocation must still use the old analysis path."""
    source = tmp_path / "legacy.json"
    _write_fake_export(source)
    output_dir = tmp_path / "legacy-out"

    exit_code = cli_module.main([str(source), "--output", str(output_dir)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "\u5904\u7406\u6d88\u606f\u6570\u91cf" in captured.out
