"""Integration tests for extended reports on the analysis service."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


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
    assert payload["schema_version"] == "echo-report.v0.2"


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
