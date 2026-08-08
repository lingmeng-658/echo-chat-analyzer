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
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "sender": {"nickname": nickname},
        "type": "text",
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