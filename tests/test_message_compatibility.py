"""Compatibility contract for the legacy ParsedMessage name."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.message import ChatMessage
from qq_chat_analyzer.parser import ParsedMessage


def test_parsed_message_is_chat_message_alias() -> None:
    assert ParsedMessage is ChatMessage
