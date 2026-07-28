"""End-to-end tests for the local command-line analysis pipeline."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "sample_chat.json"
JSONL_FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "sample_chat.jsonl"
STOPWORDS_PATH = PROJECT_ROOT / "stopwords.txt"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.cli import main


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
