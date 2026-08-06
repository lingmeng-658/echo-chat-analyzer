"""Contract tests for the ImportRequest domain model."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import ImportRequest


def test_import_request_preserves_fields() -> None:
    request = ImportRequest(
        input_path=Path("chat.json"),
        platform="wechat",
    )

    assert request.input_path == Path("chat.json")
    assert request.platform == "wechat"


def test_import_request_defaults_platform_to_none() -> None:
    request = ImportRequest(input_path=Path("chat.json"))

    assert request.input_path == Path("chat.json")
    assert request.platform is None


def test_import_request_is_immutable_and_uses_slots() -> None:
    request = ImportRequest(input_path=Path("chat.json"))

    assert not hasattr(request, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.platform = "qq"
