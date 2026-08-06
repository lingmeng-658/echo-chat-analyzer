from __future__ import annotations

import json
from pathlib import Path

import pytest

from qq_chat_analyzer.application import ImportRequest, ImportService


NO_MESSAGES_LOADED = "no_messages_loaded"
UNSUPPORTED_FORMAT = "unsupported_format"
PLATFORM_HINT_FORMAT_MISMATCH = "platform_hint_format_mismatch"


def write_qq_json(path: Path, messages=None):
    if messages is None:
        messages = [
            {
                "timestamp": 1767315600,
                "sender": {
                    "uin": "100000001",
                    "nickname": "Alice",
                },
                "type": "text",
                "content": {
                    "text": "hello"
                },
            }
        ]

    path.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False),
        encoding="utf-8",
    )


def write_empty_qq_json(path: Path):
    write_qq_json(path, [])


def write_wechat_json(path: Path):
    payload = {
        "exportInfo": {
            "version": "0.0.2",
            "generator": "CipherTalk",
            "format": "detailed-json",
        },
        "session": {
            "platform": "wechat",
            "isGroup": True,
        },
        "messages": [
            {
                "type": "文本消息",
                "content": "hello",
                "senderUsername": "wxid_test",
                "senderDisplayName": "Alice",
            }
        ],
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def write_unknown_json(path: Path):
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "records": [],
            }
        ),
        encoding="utf-8",
    )


def write_manifest(path: Path):
    path.write_text(
        json.dumps(
            {
                "metadata": {},
                "chatInfo": {},
                "statistics": {},
                "chunked": {},
            }
        ),
        encoding="utf-8",
    )


def write_avatars(path: Path):
    path.write_text(
        json.dumps(
            {
                "uid": "avatar"
            }
        ),
        encoding="utf-8",
    )


# ----------------------------
# warning privacy
# ----------------------------


def test_warning_does_not_contain_filename(tmp_path):
    path = tmp_path / "群聊_测试群_123456.json"
    write_empty_qq_json(path)

    result = ImportService().execute(
        ImportRequest(path, platform="qq")
    )

    for warning in result.result.warnings:
        assert "群聊" not in warning
        assert "测试群" not in warning
        assert "123456" not in warning
        assert path.name not in warning


def test_warning_codes_are_stable(tmp_path):
    path = tmp_path / "empty.json"
    write_empty_qq_json(path)

    result = ImportService().execute(
        ImportRequest(path, platform="qq")
    )

    assert result.result.warnings == (
        NO_MESSAGES_LOADED,
    )


def test_warning_codes_are_deduplicated(tmp_path):
    directory = tmp_path / "chat"
    directory.mkdir()

    write_empty_qq_json(directory / "a.json")
    write_empty_qq_json(directory / "b.json")

    result = ImportService().execute(
        ImportRequest(directory, platform="qq")
    )

    assert result.result.warnings == (
        NO_MESSAGES_LOADED,
    )


# ----------------------------
# sidecar
# ----------------------------


def test_manifest_and_avatar_are_ignored(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()

    write_qq_json(directory / "chat.json")
    write_manifest(directory / "manifest.json")
    write_avatars(directory / "avatars.json")

    result = ImportService().execute(
        ImportRequest(directory)
    )

    assert result.result.message_count == 1
    assert result.result.warnings == ()


def test_chunks_directory_is_ignored(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()

    write_qq_json(directory / "chat.json")

    chunks = directory / "chunks"
    chunks.mkdir()

    write_qq_json(chunks / "chunk.json")

    result = ImportService().execute(
        ImportRequest(directory)
    )

    assert result.result.message_count == 1


def test_only_sidecar_returns_unsupported(tmp_path):
    directory = tmp_path / "export"
    directory.mkdir()

    write_manifest(directory / "manifest.json")
    write_avatars(directory / "avatars.json")

    result = ImportService().execute(
        ImportRequest(directory)
    )

    assert result.result.warnings == (
        UNSUPPORTED_FORMAT,
    )


# ----------------------------
# unknown
# ----------------------------


def test_unknown_json_not_treated_as_qq(tmp_path):
    path = tmp_path / "unknown.json"
    write_unknown_json(path)

    result = ImportService().execute(
        ImportRequest(path)
    )

    assert result.result.warnings == (
        UNSUPPORTED_FORMAT,
    )


def test_unknown_json_in_directory_warns(tmp_path):
    directory = tmp_path / "chat"
    directory.mkdir()

    write_qq_json(directory / "chat.json")
    write_unknown_json(directory / "unknown.json")

    result = ImportService().execute(
        ImportRequest(directory)
    )

    assert UNSUPPORTED_FORMAT in result.result.warnings


def test_unknown_warning_hides_filename(tmp_path):
    path = tmp_path / "群聊_秘密群_123456.json"
    write_unknown_json(path)

    result = ImportService().execute(
        ImportRequest(path)
    )

    for warning in result.result.warnings:
        assert "秘密群" not in warning
        assert "123456" not in warning


# ----------------------------
# platform hint
# ----------------------------


def test_platform_hint_mismatch_warning(tmp_path):
    path = tmp_path / "unknown.json"
    write_unknown_json(path)

    result = ImportService().execute(
        ImportRequest(
            path,
            platform="qq",
        )
    )

    assert result.result.platform == "qq"
    assert result.result.warnings == (
        PLATFORM_HINT_FORMAT_MISMATCH,
    )


def test_platform_hint_warning_hides_filename(tmp_path):
    path = tmp_path / "群聊_秘密群.json"
    write_unknown_json(path)

    result = ImportService().execute(
        ImportRequest(
            path,
            platform="qq",
        )
    )

    for warning in result.result.warnings:
        assert "秘密群" not in warning


# ----------------------------
# regression
# ----------------------------


def test_known_qq_and_wechat_detection(tmp_path):
    qq = tmp_path / "qq.json"
    wx = tmp_path / "wechat.json"

    write_qq_json(qq)
    write_wechat_json(wx)

    qq_result = ImportService().execute(
        ImportRequest(qq)
    )

    wx_result = ImportService().execute(
        ImportRequest(wx)
    )

    assert qq_result.result.platform == "qq"
    assert wx_result.result.platform == "wechat"