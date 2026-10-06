"""Aggregate diagnostics use current local formats and keep payloads private."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import debug_automation_profile, profile_report
from qq_db_test_data import qq_db_payload, qq_db_record


@pytest.mark.parametrize("diagnostic", [profile_report, debug_automation_profile])
@pytest.mark.parametrize("source", ["qq", "wechat"])
def test_diagnostic_accepts_db_directory_and_ignores_sidecars(tmp_path, capsys, diagnostic, source):
    directory = tmp_path / "fictional-input"
    directory.mkdir()
    payload = qq_db_payload([
        qq_db_record("private-fictional-marker", nickname="private-fictional-name"),
    ]) if source == "qq" else {
        "source": "wechat-db",
        "conversation": {"username": "fictional-room@chatroom"},
        "messages": [{
            "local_id": 1, "server_id": 9001, "local_type": 1,
            "create_time": 1760000000, "user_name": "private-fictional-name",
            "message_content": "private-fictional-marker",
        }],
    }
    (directory / "db.json").write_text(json.dumps(payload), encoding="utf-8")
    (directory / "manifest.json").write_text("{}", encoding="utf-8")
    assert diagnostic.main([str(directory)]) == 0
    output = capsys.readouterr()
    assert "原始消息数量: 1" in output.out
    assert "private-fictional-marker" not in output.out + output.err
    assert "private-fictional-name" not in output.out + output.err
    assert str(directory) not in output.out + output.err


@pytest.mark.parametrize("diagnostic", [profile_report, debug_automation_profile])
def test_diagnostic_rejects_retired_qq_files(tmp_path, capsys, diagnostic):
    path = tmp_path / "private-path.json"
    path.write_text(json.dumps({"messages": [{
        "timestamp": 1, "sender": {"nickname": "private-name"},
        "type": "text", "content": {"text": "private-text"},
    }]}), encoding="utf-8")
    assert diagnostic.main([str(path)]) == 2
    output = capsys.readouterr()
    assert "private-text" not in output.out + output.err
    assert "private-name" not in output.out + output.err
    assert str(path) not in output.out + output.err


@pytest.mark.parametrize("diagnostic", [profile_report, debug_automation_profile])
def test_diagnostic_accepts_recognized_empty_input(tmp_path, diagnostic):
    path = tmp_path / "empty-db.json"
    path.write_text(json.dumps(qq_db_payload([])), encoding="utf-8")
    assert diagnostic.main([str(path)]) == 0
