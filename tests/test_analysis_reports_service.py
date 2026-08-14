"""Integration tests for extended reports on the analysis service."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _application_module():
    return importlib.import_module("qq_chat_analyzer.application")


def _write_fictional_chat(path: Path, messages: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False),
        encoding="utf-8",
    )


def _raw_message(
    timestamp: int,
    nickname: str,
    text: str,
    message_type: str = "text",
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "sender": {"nickname": nickname},
        "type": message_type,
        "content": {"text": text},
    }


def _write_qce_chat(path: Path) -> None:
    payload = {
        "chatInfo": {
            "groupCode": "fictional-expression-group",
            "name": "Fictional Expression Group",
            "type": "group",
        },
        "messages": [
            {
                "id": "fictional-expression-1",
                "timestamp": 1704099600,
                "sender": {"uid": "u-1", "uin": "1", "name": "Fictional Alice"},
                "type": "text",
                "content": {
                    "text": "今天 😀 开心",
                    "elements": [
                        {"type": "face", "data": {"id": "1", "name": "[笑]"}}
                    ],
                },
                "recalled": False,
                "system": False,
            },
            {
                "id": "fictional-expression-2",
                "timestamp": 1704099660,
                "sender": {"uid": "u-2", "uin": "2", "name": "Fictional Bob"},
                "type": "text",
                "content": {
                    "text": "",
                    "elements": [
                        {"type": "face", "data": {"id": "2", "name": "[赞]"}}
                    ],
                },
                "recalled": False,
                "system": False,
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_wechat_db_sticker_export(path: Path) -> None:
    payload = {
        "source": "wechat-db",
        "conversation": {
            "username": "wxid_fictional_room@chatroom",
            "session_type": "group",
        },
        "messages": [
            {
                "local_id": 1,
                "server_id": 9001,
                "local_type": 47,
                "create_time": 1704099600,
                "message_content": '<msg><emoji md5="stickeronly"/></msg>',
                "user_name": "wxid_fictional_sender",
            },
            {
                "local_id": 2,
                "server_id": 9002,
                "local_type": 47,
                "create_time": 1704099660,
                "message_content": '<msg><emoji md5="stickeronly"/></msg>',
                "user_name": "wxid_fictional_sender",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_wechat_db_text_emoji_export(path: Path) -> None:
    payload = {
        "source": "wechat-db",
        "conversation": {
            "username": "wxid_fictional_room@chatroom",
            "session_type": "group",
        },
        "messages": [
            {
                "local_id": 2,
                "server_id": 9002,
                "local_type": 1,
                "create_time": 1704099600,
                "message_content": "哈哈[捂脸]来了[旺柴]",
                "user_name": "wxid_fictional_sender",
            },
            {
                "local_id": 3,
                "server_id": 9003,
                "local_type": 1,
                "create_time": 1704099660,
                "message_content": "哈哈[捂脸]来了[旺柴]",
                "user_name": "wxid_fictional_sender",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_qce_market_face_chat(path: Path) -> None:
    payload = {
        "chatInfo": {
            "groupCode": "fictional-market-face-group",
            "name": "Fictional Market Face Group",
            "type": "group",
        },
        "messages": [
            {
                "id": "fictional-market-face-1",
                "timestamp": 1704099600,
                "sender": {"uid": "u-1", "uin": "1", "name": "Fictional Alice"},
                "type": "text",
                "content": {
                    "text": "来一个",
                    "elements": [
                        {
                            "type": "market_face",
                            "marketFaceElement": {
                                "faceName": "[肘击]",
                                "emojiId": "market-1",
                            },
                        }
                    ],
                },
                "recalled": False,
                "system": False,
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _request(application, tmp_path: Path, input_path: Path):
    stopwords_path = tmp_path / "private-stopwords.txt"
    stopwords_path.write_text("", encoding="utf-8")
    return application.AnalysisRequestDTO(
        input_path=input_path,
        output_directory=tmp_path / "private-output",
        stopwords_path=stopwords_path,
        font_path=None,
        top=5,
    )


def test_non_completed_results_keep_the_empty_reports_bundle(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    _write_fictional_chat(
        input_path,
        [_raw_message(1704099600, "Fictional-Alice", "[图片]")],
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is not application.AnalysisStatus.COMPLETED
    assert result.reports == application.AnalysisReports()


def test_result_exposes_default_reports_bundle_without_reports_argument() -> None:
    application = _application_module()

    result = application.AnalysisResultDTO(
        status=application.AnalysisStatus.COMPLETED,
        processed_message_count=0,
        valid_text_count=0,
    )

    assert result.reports.activity is None
    assert result.reports.message_length is None
    assert result.reports.user_profiles is None
    assert result.reports.conversations is None
    assert result.reports.message_composition is None


def test_execute_attaches_every_report_to_the_result(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_fictional_chat(
        input_path,
        [
            _raw_message(1704099600, "Fictional-Alice", "Python 数据分析 很有趣"),
            _raw_message(1704103200, "Fictional-Alice", "Python 项目 讨论"),
            _raw_message(1704106800, "Fictional-Bob", "Python 项目 讨论 很好"),
        ],
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )
    reports = result.reports

    assert result.status is application.AnalysisStatus.COMPLETED
    assert reports.activity is not None
    assert reports.activity.total_message_count == 3
    assert len(reports.activity.hourly_counts) == 24
    assert reports.message_length is not None
    assert reports.message_length.message_count == 3
    assert reports.user_profiles is not None
    assert reports.user_profiles.speaker_count == 2
    assert reports.conversations is not None
    assert reports.conversations.conversation_count == 1
    assert reports.message_composition is not None
    assert reports.message_composition.total_count == 3
    assert _text_category_count(reports.message_composition) == 3
    assert reports.conversation_sessions is not None
    assert reports.conversation_sessions.session_count == 3


def test_reports_stay_out_of_the_result_repr(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    private_sender = "Fictional-Carol"
    _write_fictional_chat(
        input_path,
        [
            _raw_message(1704099600, private_sender, "Python 数据分析 很有趣"),
            _raw_message(1704103200, private_sender, "Python 项目 讨论"),
        ],
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert private_sender not in repr(result)
    profiles = result.reports.user_profiles.profiles
    assert profiles[0].speaker == private_sender


def test_user_profile_report_reuses_pipeline_tokens(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_fictional_chat(
        input_path,
        [
            _raw_message(1704099600, "Fictional-Alice", "Python Python 数据分析"),
            _raw_message(1704103200, "Fictional-Bob", "项目 讨论"),
        ],
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    profiles = {
        profile.speaker: profile
        for profile in result.reports.user_profiles.profiles
    }
    alice_words = {word.word: word.count for word in profiles["Fictional-Alice"].top_words}
    assert alice_words.get("Python") == 2
    assert profiles["Fictional-Bob"].top_words != ()


def test_distinctive_report_reuses_pipeline_tokens_and_stable_sender_keys(
    tmp_path: Path,
) -> None:
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    message_module = importlib.import_module("qq_chat_analyzer.message")
    stopwords_path = tmp_path / "private-stopwords.txt"
    stopwords_path.write_text("", encoding="utf-8")
    messages = []
    for member_index, sender_id in enumerate(("stable-a", "stable-b", "stable-c")):
        for message_index in range(30):
            messages.append(
                message_module.ChatMessage(
                    timestamp=1704099600 + message_index,
                    sender=f"Alias-{member_index}-{message_index % 2}",
                    sender_id=sender_id,
                    message_type="text",
                    text=(
                        f"common common common signature{member_index} "
                        f"signature{member_index} support{member_index} "
                        f"third{member_index}"
                    ),
                    conversation_type="group",
                )
            )

    analyzed = service_module._analyze_kept_messages(messages, stopwords_path)
    reports = service_module._build_reports(
        messages,
        analyzed.sender_tokens,
        conversation_type="group",
    )

    assert reports.distinctive_words is not None
    assert reports.distinctive_words.available is True
    assert {member.speaker_key for member in reports.distinctive_words.members} == {
        "stable-a",
        "stable-b",
        "stable-c",
    }


def test_unknown_conversation_does_not_infer_group_distinctive_words(
    tmp_path: Path,
) -> None:
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )

    reports = service_module._build_reports(
        [],
        [],
        conversation_type="unknown",
    )

    assert reports.distinctive_words is not None
    assert reports.distinctive_words.available is False
    assert reports.distinctive_words.availability.value == "not_group"


def test_explicit_message_conversation_type_is_used_when_request_is_unknown() -> None:
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    message_module = importlib.import_module("qq_chat_analyzer.message")
    messages = [
        message_module.ChatMessage(
            timestamp=1,
            sender="Fictional-Alice",
            message_type="text",
            text="hello",
            conversation_type="group",
        )
    ]

    assert service_module._resolve_conversation_type(messages, "unknown") == "group"


def test_unknown_message_conversation_type_stays_unknown() -> None:
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    message_module = importlib.import_module("qq_chat_analyzer.message")
    messages = [
        message_module.ChatMessage(
            timestamp=1,
            sender="Fictional-Alice",
            message_type="text",
            text="hello",
            conversation_type="unknown",
        )
    ]

    assert service_module._resolve_conversation_type(messages, "unknown") == "unknown"


def _text_category_count(report) -> int:
    for item in report.categories:
        if item.category == "文本":
            return item.count
    return 0


def test_execute_attaches_message_composition_with_type_counts(
    tmp_path: Path,
) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_fictional_chat(
        input_path,
        [
            _raw_message(1704099600, "Fictional-Alice", "hello"),
            _raw_message(
                1704103200,
                "Fictional-Alice",
                "world",
                message_type="reply",
            ),
            _raw_message(1704106800, "Fictional-Bob", "python"),
            _raw_message(
                1704110400,
                "Fictional-Bob",
                "project",
                message_type="reply",
            ),
        ],
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )
    reports = result.reports

    assert result.status is application.AnalysisStatus.COMPLETED
    assert reports.message_composition is not None
    assert reports.message_composition.total_count == 4
    assert _text_category_count(reports.message_composition) == 4
    assert (
        sum(item.count for item in reports.message_composition.categories)
        == 4
    )


def test_execute_with_no_messages_keeps_empty_reports_bundle(
    tmp_path: Path,
) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    _write_fictional_chat(input_path, [])

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is not application.AnalysisStatus.COMPLETED
    assert result.reports == application.AnalysisReports()
    assert result.reports.message_composition is None


def test_execute_generates_echo_report_json_artifact(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_fictional_chat(
        input_path,
        [
            _raw_message(1704099600, "Fictional-Alice", "Python 数据分析 很有趣"),
            _raw_message(1704103200, "Fictional-Alice", "Python 项目 讨论"),
            _raw_message(1704106800, "Fictional-Bob", "Python 项目 讨论 很好"),
        ],
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    assert ("echo_report_json", "echo-report.json") in {
        (artifact.kind, artifact.filename) for artifact in result.artifacts
    }
    report_path = output_directory / "echo-report.json"
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "echo-report.v0.7"


def test_expression_report_reaches_echo_pipeline_from_qce(
    tmp_path: Path,
) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-expression-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_qce_chat(input_path)

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    expression = result.reports.expression
    assert expression is not None
    assert expression.expression_message_count == 2
    assert expression.expression_only_message_count == 1
    assert expression.unique_expression_count == 3
    assert {item.expression_key for item in expression.top_expressions} == {
        "😀",
        "1",
        "2",
    }
    payload = json.loads(
        (output_directory / "echo-report.json").read_text(encoding="utf-8")
    )
    assert payload["expression_culture"] is not None
    assert payload["expression_culture"]["expression_message_count"] == 2


def test_market_face_reaches_expression_report_from_qce(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-market-face-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_qce_market_face_chat(input_path)

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    expression = result.reports.expression
    assert expression is not None
    assert expression.top_expressions[0].expression_key == "market-1"
    assert expression.top_expressions[0].kind == "sticker"
    assert expression.top_expressions[0].with_text_message_count == 1


def test_sticker_only_chat_returns_expression_only_with_echo_artifacts(
    tmp_path: Path,
) -> None:
    application = _application_module()
    input_path = tmp_path / "sticker-only.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_wechat_db_sticker_export(input_path)

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.EXPRESSION_ONLY
    assert result.valid_text_count == 0
    assert result.reports.expression is not None
    assert result.reports.expression.expression_message_count == 2
    assert {artifact.kind for artifact in result.artifacts} == {
        "echo_report_json",
        "echo_report_html",
    }
    assert (output_directory / "wordcloud.png").exists() is False
    payload = json.loads(
        (output_directory / "echo-report.json").read_text(encoding="utf-8")
    )
    assert payload["expression_culture"]["expression_message_count"] == 2
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "stickeronly" not in serialized
    assert "md5" not in serialized
    assert "expression_key" not in serialized
    culture = payload["expression_culture"]
    assert culture["top_expressions"] == []
    assert all(
        not member["top_expressions"] for member in culture["members"]
    )
    assert "微信自定义表情" not in serialized


def test_wechat_text_official_emoji_reaches_expression_report(
    tmp_path: Path,
) -> None:
    application = _application_module()
    input_path = tmp_path / "wechat-text-emoji.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_wechat_db_text_emoji_export(input_path)

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    expression = result.reports.expression
    assert expression is not None
    by_key = {item.expression_key: item for item in expression.top_expressions}
    assert by_key["捂脸"].kind == "platform_face"
    assert by_key["捂脸"].with_text_message_count == 2
    assert by_key["旺柴"].expression_key == "旺柴"
    profile_words = [
        word.word
        for profile in result.reports.user_profiles.profiles
        for word in profile.top_words
    ]
    assert "哈哈" in profile_words
    assert "expression:捂脸" in profile_words
    assert "expression:旺柴" in profile_words
    assert "捂脸" not in profile_words
    payload = json.loads(
        (output_directory / "echo-report.json").read_text(encoding="utf-8")
    )
    top = payload["expression_culture"]["top_expressions"]
    assert any(item["asset_key"] == "wechat:捂脸" for item in top)
    assert any(item["display_text"] == "捂脸" for item in top)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "[捂脸]" not in serialized
    assert "expression_key" not in serialized


def test_expression_only_failure_falls_back_without_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application_module()
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    input_path = tmp_path / "sticker-fallback.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_wechat_db_sticker_export(input_path)

    def fail_echo_export(*args, **kwargs):
        raise OSError("fictional export failure")

    monkeypatch.setattr(
        service_module,
        "_export_echo_artifacts",
        fail_echo_export,
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.NO_TOKENS
    assert result.artifacts == ()
    assert (output_directory / "echo-report.json").exists() is False
    assert (output_directory / "echo-report.html").exists() is False


def test_execute_generates_echo_report_html_artifact(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_fictional_chat(
        input_path,
        [
            _raw_message(1704099600, "Fictional-Alice", "Python 数据分析 很有趣"),
            _raw_message(1704103200, "Fictional-Alice", "Python 项目 讨论"),
            _raw_message(1704106800, "Fictional-Bob", "Python 项目 讨论 很好"),
        ],
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    artifact_pairs = {
        (artifact.kind, artifact.filename) for artifact in result.artifacts
    }
    assert ("echo_report_html", "echo-report.html") in artifact_pairs
    assert ("echo_report_json", "echo-report.json") in artifact_pairs
    html_path = output_directory / "echo-report.html"
    json_path = output_directory / "echo-report.json"
    assert html_path.is_file()
    assert json_path.is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "window.ECHO_DATA" in html
    assert "Fictional-Alice" in html
    assert "fetch(" not in html
    assert "assets/branding" not in html
    assert "frontend/echo_report" not in html
    assert "带表达的消息" in html
    assert "这段交流最常用的表达" in html
    assert "带表情的消息" not in html
    assert "不同表情" not in html


def test_echo_report_json_fields_are_correct(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_fictional_chat(
        input_path,
        [
            _raw_message(1704099600, "Fictional-Alice", "Python 数据分析 很有趣"),
            _raw_message(1704103200, "Fictional-Alice", "Python 项目 讨论"),
            _raw_message(1704106800, "Fictional-Bob", "Python 项目 讨论 很好"),
        ],
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )
    assert result.status is application.AnalysisStatus.COMPLETED
    payload = json.loads(
        (output_directory / "echo-report.json").read_text(encoding="utf-8")
    )

    assert payload["overview"]["total_message_count"] == 3
    assert payload["overview"]["participant_count"] == 2
    assert payload["conversation"]["name"]
    assert len(payload["activity"]["hourly"]) == 24
    assert len(payload["activity"]["weekday"]) == 7
    assert len(payload["members"]) == 2
    for member in payload["members"]:
        assert member["display_name"]
        assert member["message_count"] >= 1
        assert member["average_length"] >= 0
        assert member["active_period"] is not None
