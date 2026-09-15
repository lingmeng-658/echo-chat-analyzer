"""Behavior tests for routing WeChat exports through the application service."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


TEXT_TYPE = "\u6587\u672c\u6d88\u606f"
REPLY_TYPE = "\u5f15\u7528\u6d88\u606f"
IMAGE_TYPE = "\u56fe\u7247\u6d88\u606f"
SYSTEM_TYPE = "\u7cfb\u7edf\u6d88\u606f"

# Artifacts retired from the desktop analysis path: they belong to the legacy
# CLI only and must not be produced by AnalysisApplicationService.
RETIRED_DESKTOP_ARTIFACT_FILENAMES = (
    "word_frequency.csv",
    "word_speaker_summary.csv",
    "word_speaker_frequency.csv",
    "word_top_speakers.png",
    "wordcloud.png",
)


def _application_module():
    return importlib.import_module("qq_chat_analyzer.application")


def _service_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )


def _write_wechat_export(path: Path, messages: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
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
                "messages": messages,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _message(
    *,
    text: str,
    sender: str,
    message_type: str,
) -> dict[str, object]:
    return {
        "localId": 1,
        "platformMessageId": f"fictional-wechat-{message_type}",
        "createTime": 1783223281,
        "type": message_type,
        "chatLabType": 0,
        "content": text,
        "rawContent": text,
        "senderUsername": f"wxid_{sender}",
        "senderDisplayName": sender,
    }


def _request(
    application,
    tmp_path: Path,
    input_path: Path,
):
    stopwords_path = tmp_path / "private-stopwords.txt"
    stopwords_path.write_text("", encoding="utf-8")
    return application.AnalysisRequestDTO(
        input_path=input_path,
        output_directory=tmp_path / "private-output",
        stopwords_path=stopwords_path,
        font_path=None,
        top=5,
    )


def test_execute_routes_wechat_detailed_json_through_existing_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application_module()
    service_module = _service_module()
    input_path = tmp_path / "fictional-wechat.json"
    _write_wechat_export(
        input_path,
        [
            _message(
                text="Python Python analytics",
                sender="Fictional-Alice",
                message_type=TEXT_TYPE,
            ),
            _message(
                text="Python project",
                sender="Fictional-Bob",
                message_type=REPLY_TYPE,
            ),
            _message(
                text="[image]",
                sender="Fictional-Alice",
                message_type=IMAGE_TYPE,
            ),
            _message(
                text="System notice",
                sender="Fictional-System",
                message_type=SYSTEM_TYPE,
            ),
        ],
    )
    generated_filenames: list[str] = []

    def record_export(*args: object) -> None:
        generated_filenames.append(Path(str(args[-1])).name)

    monkeypatch.setattr(
        service_module,
        "export_echo_report_json",
        record_export,
    )
    monkeypatch.setattr(
        service_module,
        "export_echo_report_html",
        record_export,
    )

    result = service_module.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    assert result.processed_message_count == 4
    assert result.valid_text_count == 2
    assert result.top_words[0] == application.WordFrequencyDTO(
        word="Python",
        count=3,
    )
    assert {(artifact.kind, artifact.filename) for artifact in result.artifacts} == {
        ("echo_report_json", "echo-report.json"),
        ("echo_report_html", "echo-report.html"),
    }
    assert set(generated_filenames) == {
        "echo-report.json",
        "echo-report.html",
    }
    for retired_filename in RETIRED_DESKTOP_ARTIFACT_FILENAMES:
        assert not (tmp_path / "private-output" / retired_filename).exists()
