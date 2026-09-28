"""Unit coverage for the QQ Direct DB canonical self identity."""

from __future__ import annotations

import pytest

from qq_chat_analyzer.qq_db_identity import (
    QQ_DB_SELF_NAMESPACE,
    canonical_qq_uin,
)


def test_namespace_is_qq_uin() -> None:
    assert QQ_DB_SELF_NAMESPACE == "qq_uin"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100000001", "100000001"),
        (100000001, "100000001"),
        ("  100000001  ", "100000001"),
        (0, None),
        ("0", None),
        ("", None),
        (None, None),
        (True, None),
        (False, None),
        (1.0, "1.0"),
    ],
)
def test_canonical_qq_uin(raw: object, expected: str | None) -> None:
    assert canonical_qq_uin(raw) == expected


def test_canonical_qq_uin_rejects_non_scalar() -> None:
    assert canonical_qq_uin([]) is None
    assert canonical_qq_uin({}) is None
    assert canonical_qq_uin(object()) is None
