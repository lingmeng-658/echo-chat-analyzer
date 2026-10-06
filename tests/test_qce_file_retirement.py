"""Retired QQ file formats must never re-enter the local import pipeline."""

import importlib
import json
from pathlib import Path

import pytest

from qq_chat_analyzer.application import ImportRequest, ImportService


OLD_ROW = {
    "id": "fictional-old-message",
    "timestamp": 1750000000000,
    "sender": {"uin": "100000001", "nickname": "Fictional Alice"},
    "type": "text",
    "content": {"text": "fictional retired input"},
}


@pytest.mark.parametrize("platform", [None, "qq", "wechat"])
@pytest.mark.parametrize("file_format", ["qce-json", "old-qq-json", "old-qq-jsonl"])
def test_retired_qq_files_are_not_imported(tmp_path, platform, file_format):
    payload = {"messages": [OLD_ROW]}
    if file_format == "qce-json":
        payload.update({
            "metadata": {"name": "QQChatExporter"},
            "chatInfo": {"type": "group", "groupCode": "fictional-group"},
        })
    is_jsonl = file_format.endswith("jsonl")
    path = tmp_path / ("retired.jsonl" if is_jsonl else "retired.json")
    path.write_text(json.dumps(OLD_ROW if is_jsonl else payload), encoding="utf-8")
    outcome = ImportService().execute(ImportRequest(path, platform=platform))
    assert outcome.messages == ()
    assert outcome.rich_messages == ()
    assert outcome.processed_message_count == 0
    assert outcome.result.format is None
    assert outcome.result.warnings


@pytest.mark.parametrize("module", ["qq_chat_exporter_adapter", "parser"])
def test_retired_file_modules_are_absent(module):
    name = "qq_chat_analyzer." + module
    with pytest.raises(ModuleNotFoundError) as caught:
        importlib.import_module(name)
    assert caught.value.name == name
    assert not (Path(__file__).resolve().parents[1] / "src" / "qq_chat_analyzer" / (module + ".py")).exists()
