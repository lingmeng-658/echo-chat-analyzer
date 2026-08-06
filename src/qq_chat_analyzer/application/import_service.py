"""Application-layer import pipeline foundation."""

from __future__ import annotations

from pathlib import Path

from ..message import ChatMessage
from ..parser import (
    load_messages as load_qq_messages,
    parse_messages as parse_qq_messages,
)
from ..wechat_parser import (
    is_wechat_export,
    load_messages as load_wechat_messages,
    parse_messages as parse_wechat_messages,
)
from .errors import InputPathNotFound, NoSupportedInput
from .import_outcome import ImportOutcome
from .import_request import ImportRequest
from .import_result import ImportResult


_SUPPORTED_INPUT_SUFFIXES = frozenset({".json", ".jsonl"})
_SUPPORTED_PLATFORMS = frozenset({"qq", "wechat"})


class ImportService:
    """Import local chat files into ChatMessage without running analysis."""

    def execute(self, request: ImportRequest) -> ImportOutcome:
        _validate_input_path(request.input_path)
        input_files = _find_supported_input_files(request.input_path)
        if not input_files:
            raise NoSupportedInput()

        messages: list[ChatMessage] = []
        warnings: list[str] = []
        formats: set[str] = set()
        detected_platforms: list[str] = []

        for input_file in input_files:
            platform, file_messages, file_format, file_warnings = _import_file(
                input_file,
                request.platform,
            )
            detected_platforms.append(platform)
            messages.extend(file_messages)
            warnings.extend(file_warnings)
            formats.add(file_format)

        valid_text_count = sum(1 for message in messages if message.text.strip())
        result = ImportResult(
            platform=request.platform or detected_platforms[0],
            message_count=len(messages),
            valid_text_count=valid_text_count,
            warnings=tuple(warnings),
            format=_single_format(formats),
        )
        return ImportOutcome(result=result, messages=tuple(messages))


def _validate_input_path(input_path: Path) -> None:
    if not input_path.exists():
        raise InputPathNotFound()


def _find_supported_input_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() in _SUPPORTED_INPUT_SUFFIXES:
            return [input_path]
        return []
    if not input_path.is_dir():
        return []
    return sorted(
        path
        for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in _SUPPORTED_INPUT_SUFFIXES
    )


def _import_file(
    input_file: Path,
    platform_hint: str | None,
) -> tuple[str, tuple[ChatMessage, ...], str, tuple[str, ...]]:
    if platform_hint == "wechat":
        return _import_wechat_file(input_file)
    if platform_hint == "qq":
        return _import_qq_file(input_file)
    if is_wechat_export(input_file):
        return _import_wechat_file(input_file)
    return _import_qq_file(input_file)


def _import_qq_file(
    input_file: Path,
) -> tuple[str, tuple[ChatMessage, ...], str, tuple[str, ...]]:
    raw_messages = load_qq_messages(input_file)
    warnings: tuple[str, ...] = ()
    if not raw_messages:
        warnings = (f"No messages loaded from {input_file.name}",)
    file_format = "jsonl" if input_file.suffix.lower() == ".jsonl" else "json"
    return (
        "qq",
        tuple(parse_qq_messages(raw_messages)),
        file_format,
        warnings,
    )


def _import_wechat_file(
    input_file: Path,
) -> tuple[str, tuple[ChatMessage, ...], str, tuple[str, ...]]:
    raw_messages = load_wechat_messages(input_file)
    warnings: tuple[str, ...] = ()
    if not raw_messages:
        warnings = (f"No messages loaded from {input_file.name}",)
    return (
        "wechat",
        tuple(parse_wechat_messages(raw_messages)),
        "detailed-json",
        warnings,
    )


def _single_format(formats: set[str]) -> str | None:
    if len(formats) == 1:
        return next(iter(formats))
    return None
