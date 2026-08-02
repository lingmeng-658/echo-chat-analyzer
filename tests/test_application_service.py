"""Behavior tests for the privacy-safe analysis application service."""

from __future__ import annotations

import builtins
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


def _service_module():
    return importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )


def _write_fictional_chat(path: Path, messages: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False),
        encoding="utf-8",
    )


def _request(
    application,
    tmp_path: Path,
    input_path: Path,
    *,
    stopwords: str = "",
    top: int = 5,
):
    stopwords_path = tmp_path / "private-stopwords.txt"
    stopwords_path.write_text(stopwords, encoding="utf-8")
    return application.AnalysisRequestDTO(
        input_path=input_path,
        output_directory=tmp_path / "private-output",
        stopwords_path=stopwords_path,
        font_path=None,
        top=top,
    )


def test_execute_returns_completed_privacy_safe_result_without_cli_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    application = _application_module()
    service_module = _service_module()
    input_path = tmp_path / "fictional-chat.json"
    output_directory = tmp_path / "private-output"
    stopwords_path = tmp_path / "private-stopwords.txt"
    private_senders = ("Fictional-Alice", "Fictional-Bob")
    _write_fictional_chat(
        input_path,
        [
            {
                "timestamp": 1,
                "sender": {"nickname": private_senders[0]},
                "type": "text",
                "content": {"text": "Python Python analytics"},
            },
            {
                "timestamp": 2,
                "sender": {"nickname": private_senders[1]},
                "type": "text",
                "content": {"text": "Python project"},
            },
        ],
    )
    stopwords_path.write_text("", encoding="utf-8")

    generated_filenames: list[str] = []

    def record_export(*args: object) -> None:
        generated_filenames.append(Path(str(args[-1])).name)

    def record_chart(*args: object) -> None:
        generated_filenames.append(Path(str(args[1])).name)

    monkeypatch.setattr(
        service_module,
        "export_word_frequency_csv",
        record_export,
    )
    monkeypatch.setattr(
        service_module,
        "export_word_speaker_summary_csv",
        record_export,
    )
    monkeypatch.setattr(
        service_module,
        "export_word_speaker_frequency_csv",
        record_export,
    )
    monkeypatch.setattr(
        service_module,
        "generate_word_top_speakers_chart",
        record_chart,
    )
    monkeypatch.setattr(
        service_module,
        "generate_wordcloud",
        record_chart,
    )

    tokenizer_module = importlib.import_module("qq_chat_analyzer.tokenizer")
    tokenizer_module.tokenize("warmup")
    capsys.readouterr()

    result = service_module.AnalysisApplicationService().execute(
        application.AnalysisRequestDTO(
            input_path=input_path,
            output_directory=output_directory,
            stopwords_path=stopwords_path,
            font_path=None,
            top=5,
        )
    )

    captured = capsys.readouterr()
    assert result.status is application.AnalysisStatus.COMPLETED
    assert result.processed_message_count == 2
    assert result.valid_text_count == 2
    assert result.top_words[0] == application.WordFrequencyDTO(
        word="Python",
        count=3,
    )
    assert {(artifact.kind, artifact.filename) for artifact in result.artifacts} == {
        ("word_frequency_csv", "word_frequency.csv"),
        ("wordcloud", "wordcloud.png"),
        ("word_speaker_summary_csv", "word_speaker_summary.csv"),
        ("word_speaker_frequency_csv", "word_speaker_frequency.csv"),
        ("word_top_speakers_chart", "word_top_speakers.png"),
    }
    assert set(generated_filenames) == {
        "word_frequency.csv",
        "wordcloud.png",
        "word_speaker_summary.csv",
        "word_speaker_frequency.csv",
        "word_top_speakers.png",
    }
    assert captured.out == ""
    assert captured.err == ""
    result_repr = repr(result)
    assert str(tmp_path) not in result_repr
    for private_sender in private_senders:
        assert private_sender not in result_repr


def test_execute_returns_no_valid_text_without_exporting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application_module()
    service_module = _service_module()
    input_path = tmp_path / "system-only.json"
    _write_fictional_chat(
        input_path,
        [
            {
                "timestamp": 1,
                "sender": {"nickname": "Fictional-System"},
                "type": "system",
                "content": {"text": "Private system notice"},
            }
        ],
    )

    def fail_export(*args: object) -> None:
        raise AssertionError("empty analysis must not export artifacts")

    monkeypatch.setattr(service_module, "_export_artifacts", fail_export)

    result = service_module.AnalysisApplicationService().execute(
        _request(application, tmp_path, input_path)
    )

    assert result == application.AnalysisResultDTO(
        status=application.AnalysisStatus.NO_VALID_TEXT,
        processed_message_count=1,
        valid_text_count=0,
    )


def test_execute_returns_no_tokens_without_exporting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application_module()
    service_module = _service_module()
    input_path = tmp_path / "stopped-chat.json"
    _write_fictional_chat(
        input_path,
        [
            {
                "timestamp": 1,
                "sender": {"nickname": "Fictional-Alice"},
                "type": "text",
                "content": {"text": "Python Python"},
            }
        ],
    )

    def fail_export(*args: object) -> None:
        raise AssertionError("tokenless analysis must not export artifacts")

    monkeypatch.setattr(service_module, "_export_artifacts", fail_export)

    result = service_module.AnalysisApplicationService().execute(
        _request(
            application,
            tmp_path,
            input_path,
            stopwords="Python\n",
        )
    )

    assert result == application.AnalysisResultDTO(
        status=application.AnalysisStatus.NO_TOKENS,
        processed_message_count=1,
        valid_text_count=1,
    )


def test_execute_rejects_non_positive_top(tmp_path: Path) -> None:
    application = _application_module()
    service_module = _service_module()
    input_path = tmp_path / "fictional-chat.json"
    _write_fictional_chat(input_path, [])

    with pytest.raises(application.InvalidAnalysisRequest):
        service_module.AnalysisApplicationService().execute(
            _request(application, tmp_path, input_path, top=0)
        )


def test_execute_rejects_missing_input_without_exposing_path(
    tmp_path: Path,
) -> None:
    application = _application_module()
    service_module = _service_module()
    missing_path = tmp_path / "private-missing-chat.json"

    with pytest.raises(application.InputPathNotFound) as captured:
        service_module.AnalysisApplicationService().execute(
            _request(application, tmp_path, missing_path)
        )

    assert str(missing_path) not in str(captured.value)


def test_execute_rejects_existing_unsupported_input(tmp_path: Path) -> None:
    application = _application_module()
    service_module = _service_module()
    unsupported_path = tmp_path / "private-chat.txt"
    unsupported_path.write_text("private body", encoding="utf-8")

    with pytest.raises(application.NoSupportedInput):
        service_module.AnalysisApplicationService().execute(
            _request(application, tmp_path, unsupported_path)
        )


def test_export_failure_becomes_safe_application_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application_module()
    service_module = _service_module()
    input_path = tmp_path / "fictional-chat.json"
    _write_fictional_chat(
        input_path,
        [
            {
                "timestamp": 1,
                "sender": {"nickname": "Fictional-Alice"},
                "type": "text",
                "content": {"text": "Python project"},
            }
        ],
    )
    private_failure = str(tmp_path / "private-output" / "word_frequency.csv")

    def fail_export(*args: object) -> None:
        raise OSError(f"cannot write {private_failure}")

    monkeypatch.setattr(
        service_module,
        "export_word_frequency_csv",
        fail_export,
    )

    with pytest.raises(application.ArtifactGenerationFailed) as captured:
        service_module.AnalysisApplicationService().execute(
            _request(application, tmp_path, input_path)
        )

    assert private_failure not in str(captured.value)
    assert captured.value.__cause__ is None


def test_importing_service_does_not_import_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_name = "qq_chat_analyzer.application.analysis_service"
    sys.modules.pop(module_name, None)
    real_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ):
        if name == "qq_chat_analyzer.cli" or name.endswith(".cli"):
            raise AssertionError("application service must not import CLI")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    imported = importlib.import_module(module_name)

    assert imported.AnalysisApplicationService is not None
