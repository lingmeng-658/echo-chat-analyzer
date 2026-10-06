"""Integration tests for extended reports on the analysis service."""

from __future__ import annotations

import importlib
import json
import hashlib
from qq_db_test_data import qq_db_payload, qq_db_record
from chat_input_test_data import detailed_payload
import re
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
        json.dumps(detailed_payload(messages), ensure_ascii=False),
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


def _write_qq_db_chat(path: Path) -> None:
    records = [
        qq_db_record("\u4eca\u5929 \U0001f600 \u5f00\u5fc3", sender_id="1", nickname="Fictional Alice", timestamp=1704099600,
                     message_id="fictional-expression-1", faces=((1, "[\u7b11]"),)),
        qq_db_record(sender_id="2", nickname="Fictional Bob", timestamp=1704099660,
                     message_id="fictional-expression-2", faces=((2, "[\u8d5e]"),)),
    ]
    path.write_text(json.dumps(qq_db_payload(records), ensure_ascii=False), encoding="utf-8")


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


def _write_wechat_expression_placeholder_export(path: Path) -> None:
    payload = {
        "source": "wechat-db",
        "conversation": {
            "username": "wxid_fictional_room@chatroom",
            "session_type": "group",
        },
        "messages": [
            {
                "local_id": 4,
                "server_id": 9004,
                "local_type": 1,
                "create_time": 1704099600,
                "message_content": "哈哈 [表情]",
                "user_name": "wxid_fictional_sender",
            },
            {
                "local_id": 5,
                "server_id": 9005,
                "local_type": 1,
                "create_time": 1704099660,
                "message_content": "😂",
                "user_name": "wxid_fictional_sender",
            },
            {
                "local_id": 6,
                "server_id": 9006,
                "local_type": 1,
                "create_time": 1704099720,
                "message_content": "表情",
                "user_name": "wxid_fictional_sender",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_qq_db_sticker_chat(path: Path) -> None:
    records = [qq_db_record("\u6765\u4e00\u4e2a", stickers=(("market-1", "[\u8098\u51fb]"),))]
    path.write_text(json.dumps(qq_db_payload(records), ensure_ascii=False), encoding="utf-8")


def _write_private_qq_db_expression_export(path: Path) -> None:
    records = [qq_db_record(sender_id=str(index), nickname=name,
                           message_id=f"fictional-private-{index}", timestamp=1704099600 + index * 60,
                           stickers=(("market-facepalm", "Facepalm"),))
               for index, name in enumerate(("Fictional Alice", "Fictional Bob"), start=1)]
    path.write_text(json.dumps(qq_db_payload(records, session_type="private"), ensure_ascii=False), encoding="utf-8")


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


def test_analysis_logs_each_timing_stage_without_private_content(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-chat.json"
    (tmp_path / "private-output").mkdir()
    _write_fictional_chat(input_path, [
        _raw_message(1704099600, "Fictional-Alice", "Python 数据分析 很有趣"),
        _raw_message(1704099500, "Fictional-Bob", "fictional long text " * 10),
        _raw_message(1704099660, "Fictional-Bob", "Python 项目 讨论"),
        _raw_message(1704099720, "Fictional-Carol", "Python 项目 讨论 很好"),
    ])
    caplog.set_level("INFO")

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    timing_lines = [
        record.message for record in caplog.records
        if record.message.startswith("[analysis-timing]")
    ]
    expected = {
        "import", "scope_filter", "smart_profile", "message_quality_filter",
        "text_analysis", "ExpressionAnalyzer.preflight", "word_ranking",
        "report_build", "word_speaker_analysis", "artifact_export", "total",
        "ActivityAnalyzer", "MessageLengthAnalyzer", "UserProfileAnalyzer",
        "ConversationAnalyzer", "MessageCompositionAnalyzer",
        "conversation_sessions", "DistinctiveWordAnalyzer",
        "PrivateLanguageAnalyzer", "ExpressionAnalyzer.report",
        "robot_detector", "template_detector", "interactive_bot_detector",
        "decision_engine", "filter_pipeline",
    }
    actual = {re.search(r"stage=([^ ]+)", line).group(1) for line in timing_lines}
    assert actual == expected
    assert all(re.search(r"elapsed_ms=\d+", line) for line in timing_lines)
    assert all("Fictional-" not in line for line in timing_lines)


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


def test_analysis_loads_stopwords_once_per_run_and_refreshes_next_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    message_module = importlib.import_module("qq_chat_analyzer.message")
    stopwords_path = tmp_path / "fictional-stopwords.txt"
    stopwords_path.write_text("alpha\n", encoding="utf-8")
    messages = [
        message_module.ChatMessage(
            timestamp=1704099600 + index,
            sender="Fictional Alice",
            message_type="text",
            text="alpha beta",
        )
        for index in range(3)
    ]
    original_open = Path.open
    stopword_opens = 0

    def counting_open(path: Path, *args: object, **kwargs: object):
        nonlocal stopword_opens
        if path == stopwords_path and args and args[0] == "r":
            stopword_opens += 1
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)

    first = service_module._analyze_kept_messages(messages, stopwords_path)
    assert first.tokens == ["beta"] * len(messages)
    assert stopword_opens == 1

    stopwords_path.write_text("beta\n", encoding="utf-8")
    second = service_module._analyze_kept_messages(messages, stopwords_path)
    assert second.tokens == ["alpha"] * len(messages)
    assert stopword_opens == 2


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


def test_expression_report_reaches_echo_pipeline_from_qq_db(
    tmp_path: Path,
) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-expression-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_qq_db_chat(input_path)

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


def test_completed_analysis_reuses_expression_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application_module()
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    input_path = tmp_path / "fictional-expression-chat.json"
    (tmp_path / "private-output").mkdir()
    _write_qq_db_chat(input_path)
    original_analyze = service_module.ExpressionAnalyzer.analyze
    expression_reports = []

    def counting_analyze(self, messages, *, rich_messages=(), rich_by_instance=None):
        report = original_analyze(
            self, messages, rich_messages=rich_messages,
            rich_by_instance=rich_by_instance,
        )
        expression_reports.append(report)
        return report

    monkeypatch.setattr(
        service_module.ExpressionAnalyzer, "analyze", counting_analyze
    )

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    assert len(expression_reports) == 1
    assert result.reports.expression is expression_reports[0]
    assert result.reports.expression.expression_message_count == 2


def test_market_face_reaches_expression_report_from_qq_db(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-market-face-chat.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_qq_db_sticker_chat(input_path)

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    expression = result.reports.expression
    assert expression is not None
    assert expression.top_expressions[0].expression_key == "qq-marketface:sha256:" + hashlib.sha256(b"market-1").hexdigest()
    assert expression.top_expressions[0].kind == "sticker"
    assert expression.top_expressions[0].with_text_message_count == 1


def test_private_qq_db_expression_labels_does_not_leak_into_voice_words(
    tmp_path: Path,
) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-private-expression-fallback.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_private_qq_db_expression_export(input_path)

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    expression = result.reports.expression
    assert expression is not None
    assert expression.expression_occurrence_count == 2
    assert expression.top_expressions[0].expression_key == "qq-marketface:sha256:" + hashlib.sha256(b"market-facepalm").hexdigest()
    assert all(word.word != "Facepalm" for word in result.top_words)

    profile_words = [
        word.word
        for profile in result.reports.user_profiles.profiles
        for word in profile.top_words
    ]
    private_words = [
        word.word for word in result.reports.private_language.shared_words
    ]
    assert "Facepalm" not in profile_words
    assert "Facepalm" not in private_words
    assert profile_words == []
    assert private_words == []


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
    assert all(not word.startswith("expression:") for word in profile_words)
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


def test_wechat_expression_placeholders_are_not_language_words(
    tmp_path: Path,
) -> None:
    application = _application_module()
    input_path = tmp_path / "wechat-expression-placeholder.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_wechat_expression_placeholder_export(input_path)

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    assert result.reports.expression is not None
    profile_words = [
        word.word
        for profile in result.reports.user_profiles.profiles
        for word in profile.top_words
    ]
    assert "哈哈" in profile_words
    assert result.reports.expression.expression_occurrence_count > 0
    assert all(not word.startswith("expression:") for word in profile_words)
    assert "表情" not in profile_words


@pytest.mark.parametrize("source", ["wechat", "qq"])
def test_private_expression_tokens_do_not_reenter_language_profile(tmp_path: Path, source: str) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-private-expressions.json"
    (tmp_path / "private-output").mkdir()
    if source == "qq":
        _write_private_qq_db_expression_export(input_path)
    else:
        rows = []
        for sender in ("wxid_fictional_self", "wxid_fictional_peer"):
            for kind, text in (
                (1, "公园散步[表情]"), (1, "表情"),
                (1, "[Facepalm]😂"), (47, '<msg><emoji md5="fictional-sticker"/></msg>'),
            ):
                rows.append({
                    "local_id": len(rows) + 1,
                    "server_id": 9000 + len(rows),
                    "create_time": 1704099600 + len(rows) * 60,
                    "local_type": kind, "message_content": text, "user_name": sender,
                })
        input_path.write_text(json.dumps({
            "source": "wechat-db",
            "conversation": {"username": "wxid_fictional_peer", "session_type": "private", "self_username": "wxid_fictional_self"},
            "messages": rows,
        }, ensure_ascii=False), encoding="utf-8")

    result = application.AnalysisApplicationService().execute(_request(application, tmp_path, input_path))
    assert result.status in {application.AnalysisStatus.COMPLETED, application.AnalysisStatus.EXPRESSION_ONLY}
    assert result.reports.expression.expression_occurrence_count > 0
    assert all(word.word != "表情" and not word.word.startswith("expression:") for word in result.top_words)
    profile = result.echo_report_view.language_profile
    assert profile.available
    assert all(not word.startswith("expression:") for member in profile.members for word in member.primary_words)
    assert all(not word.word.startswith("expression:") for word in (*profile.shared_words, *profile.side_preference_words))
    payload = json.loads((tmp_path / "private-output" / "echo-report.json").read_text(encoding="utf-8"))
    assert payload["expression_culture"] is not None
    assert '"表情"' not in json.dumps(payload["language_profile"], ensure_ascii=False)


def test_private_semantic_expression_word_remains_a_language_word(tmp_path: Path) -> None:
    application = _application_module()
    input_path = tmp_path / "fictional-semantic-expression-word.json"
    (tmp_path / "private-output").mkdir()
    rows = [{
        "local_id": index + 1, "server_id": 9000 + index,
        "create_time": 1704099600 + index * 60, "local_type": 1,
        "message_content": "你的表情很自然",
        "user_name": "wxid_fictional_self" if index % 2 else "wxid_fictional_peer",
    } for index in range(8)]
    input_path.write_text(json.dumps({
        "source": "wechat-db",
        "conversation": {"username": "wxid_fictional_peer", "session_type": "private", "self_username": "wxid_fictional_self"},
        "messages": rows,
    }, ensure_ascii=False), encoding="utf-8")
    result = application.AnalysisApplicationService().execute(_request(application, tmp_path, input_path))
    assert "表情" in {word.word for word in result.top_words}
    assert all("表情" in member.primary_words for member in result.echo_report_view.language_profile.members)
    assert "表情" in {word.word for word in result.echo_report_view.language_profile.shared_words}


@pytest.mark.parametrize("failure_type", [PermissionError, OSError, ValueError])
def test_content_report_export_failure_becomes_safe_application_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[Exception],
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
        raise failure_type(r"fictional export failure: C:\Users\Fictional\Private\report.json")

    monkeypatch.setattr(service_module, "_export_echo_artifacts", fail_echo_export)
    with pytest.raises(application.ArtifactGenerationFailed) as caught:
        application.AnalysisApplicationService().execute(
            _request(application, tmp_path, input_path)
        )

    assert caught.value.code == "artifact_generation_failed"
    assert "Fictional" not in caught.value.public_message
    assert caught.value.__cause__ is None
    assert not (output_directory / "echo-report.json").exists()
    assert not (output_directory / "echo-report.html").exists()


@pytest.mark.parametrize("with_expression", [False, True])
def test_empty_word_ranking_preserves_result_and_report_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_expression: bool,
) -> None:
    application = _application_module()
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    input_path = tmp_path / "empty-ranking.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    text = "Python 项目讨论" + (" 😀" if with_expression else "")
    _write_fictional_chat(
        input_path,
        [_raw_message(1704099600, "Fictional-Alice", text)],
    )
    monkeypatch.setattr(service_module, "top_words", lambda tokens, top: [])

    result = service_module.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    expected_status = (
        application.AnalysisStatus.EXPRESSION_ONLY
        if with_expression
        else application.AnalysisStatus.NO_TOKENS
    )
    assert result.status is expected_status
    assert result.top_words == ()
    assert result.valid_text_count == 1
    assert bool(result.artifacts) is with_expression
    assert (output_directory / "echo-report.json").exists() is with_expression
    assert (output_directory / "echo-report.html").exists() is with_expression


def test_content_report_failure_removes_partially_written_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application_module()
    service_module = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    input_path = tmp_path / "partial-report.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_wechat_db_sticker_export(input_path)

    def partially_export(request, *args, **kwargs):
        (request.output_directory / "echo-report.json").write_text("{}")
        (request.output_directory / "echo-report.html").write_text("partial")
        raise OSError("fictional export failure")

    monkeypatch.setattr(service_module, "_export_echo_artifacts", partially_export)
    with pytest.raises(application.ArtifactGenerationFailed):
        service_module.AnalysisApplicationService().execute(
            _request(application, tmp_path, input_path)
        )

    assert not (output_directory / "echo-report.json").exists()
    assert not (output_directory / "echo-report.html").exists()


@pytest.mark.parametrize("failure_kind", ["unexpected", "application"])
def test_content_report_builder_failure_propagates_without_a_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_kind: str,
) -> None:
    application = _application_module()
    service_module = importlib.import_module("qq_chat_analyzer.application.analysis_service")
    input_path = tmp_path / "fictional-builder-failure.json"
    (tmp_path / "private-output").mkdir()
    _write_wechat_db_sticker_export(input_path)
    original = (
        RuntimeError("fictional report builder failure")
        if failure_kind == "unexpected" else application.ApplicationServiceError()
    )

    def fail_build(*args, **kwargs):
        raise original

    monkeypatch.setattr(service_module, "_build_reports", fail_build)
    with pytest.raises(type(original)) as caught:
        application.AnalysisApplicationService().execute(
            _request(application, tmp_path, input_path)
        )

    assert caught.value is original
    assert not (tmp_path / "private-output" / "echo-report.json").exists()
    assert not (tmp_path / "private-output" / "echo-report.html").exists()


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


def test_normal_analysis_forwards_expression_source_for_echo_artifacts(
    tmp_path: Path,
) -> None:
    """Regression: the normal analysis path must forward its platform source.

    ``_export_artifacts`` already holds the authoritative platform, so the
    normal (COMPLETED) path must hand it to ``_export_echo_artifacts`` instead
    of raising ``TypeError`` for a missing ``expression_source``.
    """
    application = _application_module()
    input_path = tmp_path / "wechat-normal-analysis.json"
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    _write_wechat_db_text_emoji_export(input_path)

    result = application.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result.status is application.AnalysisStatus.COMPLETED
    assert result.echo_report_view is not None
    artifact_pairs = {
        (artifact.kind, artifact.filename) for artifact in result.artifacts
    }
    assert ("echo_report_json", "echo-report.json") in artifact_pairs
    assert ("echo_report_html", "echo-report.html") in artifact_pairs
    payload = json.loads(
        (output_directory / "echo-report.json").read_text(encoding="utf-8")
    )
    top = payload["expression_culture"]["top_expressions"]
    assert any(item["asset_key"] == "wechat:捂脸" for item in top)
