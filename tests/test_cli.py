"""End-to-end tests for the local command-line analysis pipeline."""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "sample_chat.json"
JSONL_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "sample_chat.jsonl"
STOPWORDS_PATH = PROJECT_ROOT / "stopwords.txt"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer import cli as cli_module
from qq_chat_analyzer.cli import main


def test_simplified_arguments_use_default_profile_top_and_output() -> None:
    input_path = Path("data") / "fictional group"

    configuration = cli_module._parse_cli_configuration([str(input_path)])

    assert configuration.input_path == input_path
    assert configuration.stopwords_path == PROJECT_ROOT / "stopwords.txt"
    assert configuration.output_directory == Path("output") / "fictional group"
    assert configuration.top == 100


@pytest.mark.parametrize(
    ("profile", "expected_filename"),
    [
        ("topic", "stopwords_topic.txt"),
        ("culture", "stopwords_culture.txt"),
    ],
)
def test_simplified_profile_maps_to_existing_stopwords_file(
    profile: str,
    expected_filename: str,
) -> None:
    configuration = cli_module._parse_cli_configuration(
        ["fictional-chat.jsonl", profile, "200"]
    )

    assert configuration.stopwords_path == PROJECT_ROOT / expected_filename
    assert configuration.top == 200


def test_legacy_arguments_keep_previous_defaults() -> None:
    configuration = cli_module._parse_cli_configuration(
        ["--input", "fictional-chat.json"]
    )

    assert configuration.input_path == Path("fictional-chat.json")
    assert configuration.output_directory == Path("output")
    assert configuration.stopwords_path == Path("stopwords.txt")
    assert configuration.top == 50


def test_simplified_file_input_uses_filename_without_json_suffix() -> None:
    configuration = cli_module._parse_cli_configuration(
        ["fictional chat.jsonl"]
    )

    assert configuration.output_directory == Path("output") / "fictional chat"


def test_simplified_cli_path_with_spaces_uses_automatic_output_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_dir = tmp_path / "fictional group"
    input_dir.mkdir()
    shutil.copyfile(FIXTURE_PATH, input_dir / "sample.json")
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            str(input_dir),
            "--font-path",
            str(_available_chinese_font()),
        ]
    )

    captured = capsys.readouterr()
    output_dir = tmp_path / "output" / "fictional group"
    assert exit_code == 0
    assert (output_dir / "word_frequency.csv").is_file()
    assert (output_dir / "wordcloud.png").is_file()
    assert (output_dir / "word_speaker_summary.csv").is_file()
    assert (output_dir / "word_speaker_frequency.csv").is_file()
    assert (output_dir / "word_top_speakers.png").is_file()
    assert "Top 100" in captured.out


def test_invalid_simplified_profile_returns_friendly_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["fictional-chat.json", "smart"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "profile" in captured.err
    assert "smart" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("invalid_top", ["many", "0", "-2"])
def test_invalid_simplified_top_returns_friendly_error(
    invalid_top: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["fictional-chat.json", "culture", invalid_top])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "top" in captured.err.lower()
    assert invalid_top in captured.err
    assert "Traceback" not in captured.err


def test_module_cli_file_input_generates_outputs_without_printing_chat(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "fictional-chat.json"
    shutil.copyfile(FIXTURE_PATH, input_path)
    output_dir = tmp_path / "generated-output"
    font_path = _available_chinese_font()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC_ROOT)
    environment["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qq_chat_analyzer.cli",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--stopwords",
            str(STOPWORDS_PATH),
            "--font-path",
            str(font_path),
            "--top",
            "10",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    assert (output_dir / "word_frequency.csv").is_file()
    assert (output_dir / "wordcloud.png").is_file()
    assert "处理消息数量: 7" in result.stdout
    assert "有效文本数量: 3" in result.stdout
    assert "今天一起学习 Python 数据分析" not in result.stdout
    assert "好呀，下午两点开始吧" not in result.stdout


def test_cli_generates_word_speaker_csvs_for_fictional_senders(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "fictional-multi-sender.json"
    input_path.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "timestamp": 1767317100,
                        "sender": {"nickname": "小青"},
                        "type": "text",
                        "content": {"text": "Python Python 数据分析"},
                    },
                    {
                        "timestamp": 1767317101,
                        "sender": {"nickname": "小白"},
                        "type": "text",
                        "content": {"text": "Python 数据分析"},
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    exit_code = main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--stopwords",
            str(STOPWORDS_PATH),
            "--font-path",
            str(_available_chinese_font()),
            "--top",
            "5",
        ]
    )

    captured = capsys.readouterr()
    summary_path = output_dir / "word_speaker_summary.csv"
    frequency_path = output_dir / "word_speaker_frequency.csv"
    chart_path = output_dir / "word_top_speakers.png"

    assert exit_code == 0
    assert (output_dir / "word_frequency.csv").is_file()
    assert (output_dir / "wordcloud.png").is_file()
    assert summary_path.is_file()
    assert frequency_path.is_file()
    assert chart_path.is_file()
    with Image.open(chart_path) as image:
        assert image.width > 0
        assert image.height > 0

    with summary_path.open("r", encoding="utf-8-sig", newline="") as file:
        summary_rows = list(csv.DictReader(file))
    assert {
        "word": "Python",
        "total_count": "3",
        "top_speaker": "小青",
        "top_speaker_count": "2",
        "top_speaker_share_percent": "66.67",
    } in summary_rows

    with frequency_path.open("r", encoding="utf-8-sig", newline="") as file:
        frequency_rows = list(csv.DictReader(file))
    assert [
        row
        for row in frequency_rows
        if row["word"] == "Python"
    ] == [
        {"word": "Python", "speaker": "小青", "count": "2"},
        {"word": "Python", "speaker": "小白", "count": "1"},
    ]

    assert "Python Python 数据分析" not in captured.out
    assert "Python 数据分析" not in captured.out
    assert "小青" not in captured.out
    assert "小白" not in captured.out


def test_directory_input_ignores_one_invalid_json_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    shutil.copyfile(FIXTURE_PATH, input_dir / "valid.json")
    (input_dir / "invalid.json").write_text("{not valid json", encoding="utf-8")
    output_dir = tmp_path / "output"

    exit_code = main(
        [
            "--input",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--stopwords",
            str(STOPWORDS_PATH),
            "--font-path",
            str(_available_chinese_font()),
            "--top",
            "5",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "处理消息数量: 7" in captured.out
    assert (output_dir / "word_frequency.csv").is_file()
    assert (output_dir / "wordcloud.png").is_file()


def test_jsonl_file_input_generates_outputs_without_printing_chat(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "fictional-chat.jsonl"
    shutil.copyfile(JSONL_FIXTURE_PATH, input_path)
    output_dir = tmp_path / "output"

    exit_code = main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
            "--stopwords",
            str(STOPWORDS_PATH),
            "--font-path",
            str(_available_chinese_font()),
            "--top",
            "5",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "处理消息数量: 4" in captured.out
    assert "有效文本数量: 2" in captured.out
    assert "量子课程今天开课" not in captured.out
    assert "下午继续研究算法" not in captured.out
    assert (output_dir / "word_frequency.csv").is_file()
    assert (output_dir / "wordcloud.png").is_file()


def test_directory_input_recursively_discovers_jsonl(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chunks_dir = tmp_path / "export" / "chunks"
    chunks_dir.mkdir(parents=True)
    shutil.copyfile(JSONL_FIXTURE_PATH, chunks_dir / "c000001.jsonl")
    output_dir = tmp_path / "output"

    exit_code = main(
        [
            "--input",
            str(tmp_path / "export"),
            "--output-dir",
            str(output_dir),
            "--stopwords",
            str(STOPWORDS_PATH),
            "--font-path",
            str(_available_chinese_font()),
            "--top",
            "5",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "处理消息数量: 4" in captured.out
    assert (output_dir / "word_frequency.csv").is_file()
    assert (output_dir / "wordcloud.png").is_file()


def test_no_valid_text_does_not_create_output_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "system-only.json"
    input_path.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "timestamp": 1767317000,
                        "sender": {"nickname": "系统"},
                        "type": "system",
                        "content": {"text": "虚构系统通知"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    exit_code = main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "没有有效文本" in captured.out
    assert not (output_dir / "word_frequency.csv").exists()
    assert not (output_dir / "wordcloud.png").exists()
    assert not (output_dir / "word_speaker_summary.csv").exists()
    assert not (output_dir / "word_speaker_frequency.csv").exists()
    assert not (output_dir / "word_top_speakers.png").exists()


def test_missing_input_path_returns_clear_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_path = tmp_path / "missing.json"

    exit_code = main(["--input", str(missing_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "输入路径不存在" in captured.err


def _available_chinese_font() -> Path:
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = [
        windows_fonts / "msyh.ttc",
        windows_fonts / "msyhbd.ttc",
        windows_fonts / "simhei.ttf",
        windows_fonts / "simsun.ttc",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    pytest.skip("No Chinese font is available for the CLI test.")
