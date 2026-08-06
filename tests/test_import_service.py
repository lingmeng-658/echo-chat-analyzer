"""Behavior tests for the ImportService foundation."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import (
    ImportOutcome,
    ImportRequest,
    ImportResult,
    ImportService,
)
from qq_chat_analyzer.application.errors import InputPathNotFound, NoSupportedInput
from qq_chat_analyzer.message import ChatMessage


WECHAT_TEXT_TYPE = "\u6587\u672c\u6d88\u606f"


def _import_service_module():
    return importlib.import_module("qq_chat_analyzer.application.import_service")


def _write_qq_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "timestamp": 1767315600,
                        "sender": {
                            "uin": "100000001",
                            "nickname": "Fictional Alice",
                        },
                        "type": "text",
                        "content": {"text": "Hello from QQ JSON"},
                    },
                    {
                        "timestamp": 1767315660,
                        "sender": {
                            "uin": "100000002",
                            "nickname": "Fictional Bob",
                        },
                        "type": "image",
                        "content": {"text": "[image]"},
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_qq_jsonl(path: Path) -> None:
    messages = [
        {
            "id": "fictional-jsonl-1",
            "timestamp": 1767402000,
            "sender": {
                "uin": "200000001",
                "nickname": "Fictional Alice",
            },
            "type": "text",
            "content": {"text": "Hello from QQ JSONL"},
            "recalled": False,
            "system": False,
        },
        {
            "id": "fictional-jsonl-2",
            "timestamp": 1767402060,
            "sender": {
                "uin": "200000002",
                "nickname": "Fictional Bob",
            },
            "type": "reply",
            "content": {"text": "Reply from QQ JSONL"},
            "recalled": False,
            "system": False,
        },
    ]
    path.write_text(
        "\n".join(
            json.dumps(message, ensure_ascii=False) for message in messages
        ),
        encoding="utf-8",
    )


def _write_wechat_json(path: Path) -> None:
    payload = {
        "exportInfo": {
            "version": "0.0.2",
            "exportedAt": 1785895813,
            "generator": "CipherTalk",
            "format": "detailed-json",
        },
        "session": {
            "wxid": "fictional-chatroom",
            "nickname": "Fictional Group",
            "platform": "wechat",
            "isGroup": True,
        },
        "messages": [
            {
                "localId": 1,
                "platformMessageId": "fictional-wechat-message-001",
                "createTime": 1783223281,
                "type": WECHAT_TEXT_TYPE,
                "content": "Hello from WeChat",
                "senderUsername": "wxid_fictional_sender",
                "senderDisplayName": "Fictional Alice",
            },
            {
                "localId": 2,
                "platformMessageId": "fictional-wechat-message-002",
                "createTime": 1783223285,
                "type": WECHAT_TEXT_TYPE,
                "content": "Hello again from WeChat",
                "senderUsername": "wxid_fictional_sender",
                "senderDisplayName": "Fictional Alice",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_qq_json_import_returns_result_and_messages(tmp_path: Path) -> None:
    input_path = tmp_path / "qq.json"
    _write_qq_json(input_path)

    outcome = ImportService().execute(
        ImportRequest(input_path=input_path, platform="qq")
    )

    assert isinstance(outcome, ImportOutcome)
    assert outcome.processed_message_count == 2
    assert outcome.result == ImportResult(
        platform="qq",
        message_count=1,
        valid_text_count=1,
        format="json",
    )
    assert len(outcome.messages) == 1
    assert isinstance(outcome.messages[0], ChatMessage)
    assert outcome.messages[0].text == "Hello from QQ JSON"


def test_qq_jsonl_import_returns_result_and_messages(tmp_path: Path) -> None:
    input_path = tmp_path / "qq.jsonl"
    _write_qq_jsonl(input_path)

    outcome = ImportService().execute(
        ImportRequest(input_path=input_path, platform="qq")
    )

    assert outcome.result == ImportResult(
        platform="qq",
        message_count=2,
        valid_text_count=2,
        format="jsonl",
    )
    assert [message.text for message in outcome.messages] == [
        "Hello from QQ JSONL",
        "Reply from QQ JSONL",
    ]


def test_wechat_detailed_json_import_returns_result_and_messages(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "wechat.json"
    _write_wechat_json(input_path)

    outcome = ImportService().execute(
        ImportRequest(input_path=input_path, platform="wechat")
    )

    assert outcome.result == ImportResult(
        platform="wechat",
        message_count=2,
        valid_text_count=2,
        format="detailed-json",
    )
    assert [message.text for message in outcome.messages] == [
        "Hello from WeChat",
        "Hello again from WeChat",
    ]


def test_auto_detection_routes_wechat_file_without_platform(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "wechat.json"
    _write_wechat_json(input_path)

    outcome = ImportService().execute(
        ImportRequest(input_path=input_path)
    )

    assert outcome.result.platform == "wechat"
    assert outcome.result.format == "detailed-json"
    assert len(outcome.messages) == 2


def test_directory_import_discovers_supported_files(tmp_path: Path) -> None:
    directory = tmp_path / "chats"
    directory.mkdir()
    _write_qq_json(directory / "chat.json")
    _write_qq_jsonl(directory / "chat.jsonl")

    outcome = ImportService().execute(
        ImportRequest(input_path=directory, platform="qq")
    )

    assert outcome.result.message_count == 3
    assert outcome.result.format is None
    assert outcome.result.warnings == ()


def test_missing_input_path_raises_input_path_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"

    with pytest.raises(InputPathNotFound):
        ImportService().execute(ImportRequest(input_path=missing))


def test_unsupported_input_file_raises_no_supported_input(tmp_path: Path) -> None:
    input_path = tmp_path / "chat.txt"
    input_path.write_text("plain text", encoding="utf-8")

    with pytest.raises(NoSupportedInput):
        ImportService().execute(ImportRequest(input_path=input_path))


def test_corrupt_json_returns_warning_and_empty_result(tmp_path: Path) -> None:
    input_path = tmp_path / "broken.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    outcome = ImportService().execute(
        ImportRequest(input_path=input_path, platform="qq")
    )

    assert outcome.result.message_count == 0
    assert outcome.processed_message_count == 0
    assert outcome.result.valid_text_count == 0
    assert outcome.result.warnings
    assert outcome.messages == ()


def test_qq_import_reuses_existing_qq_parser_functions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "qq.json"
    input_path.write_text("{}", encoding="utf-8")
    module = _import_service_module()
    calls: list[str] = []
    raw_messages = [{"fictional": "raw"}]
    parsed = [
        ChatMessage(
            timestamp=1,
            sender="Fictional Alice",
            message_type="text",
            text="Hello",
        )
    ]

    def fake_load(_: Path) -> list[dict[str, str]]:
        calls.append("load_qq")
        return raw_messages

    def fake_parse(raw: object) -> list[ChatMessage]:
        calls.append("parse_qq")
        assert raw is raw_messages
        return parsed

    monkeypatch.setattr(module, "load_qq_messages", fake_load)
    monkeypatch.setattr(module, "parse_qq_messages", fake_parse)

    outcome = ImportService().execute(
        ImportRequest(input_path=input_path, platform="qq")
    )

    assert calls == ["load_qq", "parse_qq"]
    assert outcome.messages == tuple(parsed)


def test_wechat_import_reuses_existing_wechat_parser_functions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "wechat.json"
    input_path.write_text("{}", encoding="utf-8")
    module = _import_service_module()
    calls: list[str] = []
    raw_messages = [{"fictional": "raw"}]
    parsed = [
        ChatMessage(
            timestamp=1,
            sender="Fictional Alice",
            message_type="text",
            text="Hello",
        )
    ]

    def fake_load(_: Path) -> list[dict[str, str]]:
        calls.append("load_wechat")
        return raw_messages

    def fake_parse(raw: object) -> list[ChatMessage]:
        calls.append("parse_wechat")
        assert raw is raw_messages
        return parsed

    def unexpected_detect(_: Path) -> bool:
        raise AssertionError("explicit platform should skip detection")

    monkeypatch.setattr(module, "load_wechat_messages", fake_load)
    monkeypatch.setattr(module, "parse_wechat_messages", fake_parse)
    monkeypatch.setattr(module, "is_wechat_export", unexpected_detect)

    outcome = ImportService().execute(
        ImportRequest(input_path=input_path, platform="wechat")
    )

    assert calls == ["load_wechat", "parse_wechat"]
    assert outcome.messages == tuple(parsed)
