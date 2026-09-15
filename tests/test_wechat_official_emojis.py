"""Contract tests for the vendored official WeChat emoji dictionary."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.wechat_official_emojis import (  # noqa: E402
    OFFICIAL_WECHAT_EMOJI_NAMES,
    WECHAT_EMOJI_ALIASES,
    canonical_wechat_emoji_name,
)


def test_dictionary_contains_target_official_emoji_names() -> None:
    assert {"捂脸", "旺柴", "裂开"} <= OFFICIAL_WECHAT_EMOJI_NAMES


def test_dictionary_matches_vendored_wechat_emoji_asset_count() -> None:
    assert len(OFFICIAL_WECHAT_EMOJI_NAMES) == 109


def test_dictionary_names_are_non_empty_without_brackets() -> None:
    assert all(name and "[" not in name and "]" not in name for name in OFFICIAL_WECHAT_EMOJI_NAMES)


def test_alias_map_only_normalizes_to_official_names() -> None:
    assert WECHAT_EMOJI_ALIASES
    assert set(WECHAT_EMOJI_ALIASES.values()) <= OFFICIAL_WECHAT_EMOJI_NAMES
    assert all(
        alias and "[" not in alias and "]" not in alias
        for alias in WECHAT_EMOJI_ALIASES
    )


def test_alias_lookup_is_case_insensitive_and_rejects_unknown_codes() -> None:
    assert canonical_wechat_emoji_name("Facepalm") == "捂脸"
    assert canonical_wechat_emoji_name("facepalm") == "捂脸"
    assert canonical_wechat_emoji_name("捂脸") == "捂脸"
    assert canonical_wechat_emoji_name("TODO") is None


#: English codes published for the current client whose canonical Chinese
#: names were previously missing from the alias map. Source: macOS client
#: ``newemoji-config.xml`` (key / cn-value / en-value), cross-checked against
#: the 109 codes measured on Android WeChat 8.0.48.
NEW_OFFICIAL_ENGLISH_ALIASES = {
    "Bye": "再见",
    "Salute": "抱拳",
    "Happy": "笑脸",
    "Sick": "生病",
    "Flushed": "脸红",
    "Lol": "破涕为笑",
    "Terror": "恐惧",
    "Let Down": "失望",
    "Duh": "无语",
    "MyBad": "打脸",
    "Boring": "翻白眼",
    "Awesome": "666",
    "LetMeSee": "让我看看",
    "Sigh": "叹气",
    "Hurt": "苦涩",
    "Broken": "裂开",
    "Party": "庆祝",
    "Packet": "红包",
    "Rich": "發",
    "Blessing": "福",
    "Fireworks": "烟花",
    "Firecracker": "爆竹",
    "Worship": "合十",
    "Blush": "囧",
}


@pytest.mark.parametrize(
    ("alias", "canonical"),
    sorted(NEW_OFFICIAL_ENGLISH_ALIASES.items()),
)
def test_previously_missing_english_alias_normalizes_to_canonical_name(
    alias: str,
    canonical: str,
) -> None:
    assert canonical_wechat_emoji_name(alias) == canonical


def test_english_alias_keys_never_shadow_a_canonical_name() -> None:
    assert not (set(WECHAT_EMOJI_ALIASES) & OFFICIAL_WECHAT_EMOJI_NAMES)


def test_spaced_let_down_and_joined_let_down_both_map_to_disappointment() -> None:
    assert canonical_wechat_emoji_name("LetDown") == "失望"
    assert canonical_wechat_emoji_name("Let Down") == "失望"


def test_awesome_normalizes_to_the_numeric_canonical_666() -> None:
    assert canonical_wechat_emoji_name("Awesome") == "666"
    assert "Awesome" in WECHAT_EMOJI_ALIASES


def test_legacy_english_aliases_are_preserved() -> None:
    for alias, canonical in (
        ("Wave", "再见"),
        ("Fight", "抱拳"),
        ("Sob", "流泪"),
        ("Facepalm", "捂脸"),
    ):
        assert canonical_wechat_emoji_name(alias) == canonical


def test_every_current_client_code_is_recognized() -> None:
    """Re-prove full coverage: every shipped code resolves to its canonical name."""
    recognized = [
        code
        for code in OFFICIAL_WECHAT_EMOJI_NAMES
        if canonical_wechat_emoji_name(code) == code
    ]

    assert len(recognized) == 109


@pytest.mark.parametrize(
    ("alias", "canonical"),
    sorted(WECHAT_EMOJI_ALIASES.items()),
)
def test_every_alias_resolves_to_declared_canonical(
    alias: str,
    canonical: str,
) -> None:
    """Consume the whole alias map, not just the canonical side of it."""
    assert canonical_wechat_emoji_name(alias) == canonical


def test_alias_keys_do_not_collide_after_case_folding() -> None:
    folded = [alias.lower() for alias in WECHAT_EMOJI_ALIASES]

    assert len(folded) == len(set(folded))
