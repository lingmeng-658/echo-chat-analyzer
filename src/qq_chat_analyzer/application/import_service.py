"""Application-layer import pipeline foundation."""

from __future__ import annotations

import json
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

_SIDECAR_FILE_NAMES = frozenset({"manifest.json", "avatars.json"})
_SIDECAR_DIR_NAMES = frozenset({"resources"})
_CHUNK_DIR_NAMES = frozenset({"chunks"})
_CHUNK_DATA_SUFFIXES = frozenset({".jsonl"})

WARNING_NO_MESSAGES_LOADED = "no_messages_loaded"
WARNING_UNSUPPORTED_FORMAT = "unsupported_format"
WARNING_PLATFORM_HINT_FORMAT_MISMATCH = "platform_hint_format_mismatch"

_UNKNOWN_PLATFORM = None


class ImportService:
    """Import local chat files into ChatMessage without running analysis."""

    def execute(self, request: ImportRequest) -> ImportOutcome:
        _validate_input_path(request.input_path)
        candidate_files = _find_candidate_input_files(request.input_path)
        if not candidate_files:
            raise NoSupportedInput()

        input_files = [
            path
            for path in candidate_files
            if not _is_sidecar(path, request.input_path)
        ]
        if not input_files:
            return _unsupported_outcome(request.platform)

        messages: list[ChatMessage] = []
        warnings: list[str] = []
        formats: set[str] = set()
        detected_platforms: list[str] = []
        processed_message_count = 0

        for input_file in input_files:
            (
                platform,
                file_messages,
                file_format,
                file_warnings,
                file_raw_count,
            ) = _import_file(
                input_file,
                request.platform,
            )
            warnings.extend(file_warnings)
            if platform is _UNKNOWN_PLATFORM:
                continue
            detected_platforms.append(platform)
            messages.extend(file_messages)
            if file_format is not None:
                formats.add(file_format)
            processed_message_count += file_raw_count

        valid_text_count = sum(1 for message in messages if message.text.strip())
        result = ImportResult(
            platform=_resolve_platform(request.platform, detected_platforms),
            message_count=len(messages),
            valid_text_count=valid_text_count,
            warnings=_dedupe_warnings(warnings),
            format=_single_format(formats),
        )
        return ImportOutcome(
            result=result,
            processed_message_count=processed_message_count,
            messages=tuple(messages),
        )


def _validate_input_path(input_path: Path) -> None:
    if not input_path.exists():
        raise InputPathNotFound()


def _find_candidate_input_files(input_path: Path) -> list[Path]:
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


def _unsupported_outcome(platform_hint: str | None) -> ImportOutcome:
    return ImportOutcome(
        result=ImportResult(
            platform=_resolve_platform(platform_hint, []),
            message_count=0,
            valid_text_count=0,
            warnings=(WARNING_UNSUPPORTED_FORMAT,),
            format=None,
        ),
        processed_message_count=0,
        messages=(),
    )


def _is_sidecar(path: Path, root: Path) -> bool:
    if path.name.lower() in _SIDECAR_FILE_NAMES:
        return True
    try:
        relative_parents = path.relative_to(root).parent.parts
    except ValueError:
        return False

    lowered_parents = [part.lower() for part in relative_parents]
    if any(part in _SIDECAR_DIR_NAMES for part in lowered_parents):
        return True
    if any(part in _CHUNK_DIR_NAMES for part in lowered_parents):
        return path.suffix.lower() not in _CHUNK_DATA_SUFFIXES
    return False


def _import_file(
    input_file: Path,
    platform_hint: str | None,
) -> tuple[str | None, tuple[ChatMessage, ...], str | None, tuple[str, ...], int]:
    if platform_hint == "wechat":
        return _import_wechat_file(input_file)
    if platform_hint == "qq":
        return _import_qq_file(input_file)
    if is_wechat_export(input_file):
        return _import_wechat_file(input_file)
    if _looks_like_qq_export(input_file):
        return _import_qq_file(input_file)
    return (
        _UNKNOWN_PLATFORM,
        (),
        None,
        (WARNING_UNSUPPORTED_FORMAT,),
        0,
    )


def _import_qq_file(
    input_file: Path,
) -> tuple[str, tuple[ChatMessage, ...], str, tuple[str, ...], int]:
    raw_messages = load_qq_messages(input_file)
    parsed_messages = tuple(parse_qq_messages(raw_messages))
    warnings = _import_warnings(input_file, "qq", raw_messages, parsed_messages)
    file_format = "jsonl" if input_file.suffix.lower() == ".jsonl" else "json"
    return (
        "qq",
        parsed_messages,
        file_format,
        warnings,
        len(raw_messages),
    )


def _import_wechat_file(
    input_file: Path,
) -> tuple[str, tuple[ChatMessage, ...], str, tuple[str, ...], int]:
    raw_messages = load_wechat_messages(input_file)
    parsed_messages = tuple(parse_wechat_messages(raw_messages))
    warnings = _import_warnings(
        input_file,
        "wechat",
        raw_messages,
        parsed_messages,
    )
    return (
        "wechat",
        parsed_messages,
        "detailed-json",
        warnings,
        len(raw_messages),
    )


def _import_warnings(
    input_file: Path,
    platform: str,
    raw_messages: list,
    parsed_messages: tuple[ChatMessage, ...],
) -> tuple[str, ...]:
    if parsed_messages:
        return ()
    if not _matches_platform_shape(input_file, platform):
        return (WARNING_PLATFORM_HINT_FORMAT_MISMATCH,)
    if not raw_messages:
        return (WARNING_NO_MESSAGES_LOADED,)
    return ()


def _matches_platform_shape(input_file: Path, platform: str) -> bool:
    if platform == "wechat":
        return is_wechat_export(input_file)
    return _looks_like_qq_export(input_file)


def _looks_like_qq_export(input_file: Path) -> bool:
    if input_file.suffix.lower() == ".jsonl":
        return bool(load_qq_messages(input_file))

    payload = _load_json_object(input_file)
    if payload is None:
        return False
    if is_wechat_export(input_file):
        return False
    return isinstance(payload.get("messages"), list)


def _load_json_object(input_file: Path) -> dict | None:
    try:
        with input_file.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _resolve_platform(
    platform_hint: str | None,
    detected_platforms: list[str],
) -> str | None:
    if platform_hint:
        return platform_hint
    if detected_platforms:
        return detected_platforms[0]
    return None


def _dedupe_warnings(warnings: list[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for warning in warnings:
        seen.setdefault(warning, None)
    return tuple(seen)


def _single_format(formats: set[str]) -> str | None:
    if len(formats) == 1:
        return next(iter(formats))
    return None
