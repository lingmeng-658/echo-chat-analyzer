"""Chinese tokenization and stopword filtering."""

from __future__ import annotations

import re
from pathlib import Path

import jieba


_WORD_CONTENT_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")
_SINGLE_CHINESE_CHARACTER_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
)
_HYPHENATED_ASCII_RE = re.compile(
    r"(?<![A-Za-z0-9-])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+(?![A-Za-z0-9-])"
)
_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s\uFF0C\u3002\uFF01\uFF1F\u3001\uFF1B\uFF1A]+",
    re.IGNORECASE,
)
_URL_PLACEHOLDER = "QQCHATURLPLACEHOLDER"
_SINGLE_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_SHORT_INTEGER_RE = re.compile(r"[0-9]{1,2}")
_DECK_QUANTITY_RE = re.compile(r"[0-9]+x", re.IGNORECASE)


def tokenize(
    text: str,
    stopwords_path: str | None = None,
    user_dict_path: str | None = None,
) -> list[str]:
    """Tokenize text and remove stopped or low-information tokens."""
    if not isinstance(text, str) or not text.strip():
        return []

    _load_user_dictionary(user_dict_path)
    stopwords = _load_stopwords(stopwords_path)
    protected_text, protected_tokens = _protect_hyphenated_ascii(text)
    url_masked_text = _URL_RE.sub(_URL_PLACEHOLDER, protected_text)
    tokens: list[str] = []

    for raw_token in jieba.lcut(url_masked_text):
        token = raw_token.strip()
        token = protected_tokens.get(token, token)
        if not token or token == _URL_PLACEHOLDER:
            continue
        if token.lower() in stopwords:
            continue
        if _WORD_CONTENT_RE.search(token) is None:
            continue
        if _is_single_chinese_character(token):
            continue
        if _is_low_information_token(token):
            continue
        tokens.append(token)

    return tokens


def _protect_hyphenated_ascii(text: str) -> tuple[str, dict[str, str]]:
    placeholder_prefix = "QQCHATHYPHENPLACEHOLDER"
    while placeholder_prefix in text:
        placeholder_prefix += "X"

    protected_tokens: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        placeholder = f"{placeholder_prefix}{len(protected_tokens)}TOKEN"
        protected_tokens[placeholder] = match.group(0)
        return placeholder

    protected_text = _HYPHENATED_ASCII_RE.sub(replace, text)
    return protected_text, protected_tokens


def _load_stopwords(stopwords_path: str | None) -> set[str]:
    if stopwords_path is None:
        return set()

    try:
        with Path(stopwords_path).open("r", encoding="utf-8") as file:
            return {
                line.strip().lower()
                for line in file
                if line.strip()
            }
    except (OSError, TypeError, UnicodeError):
        return set()


def _load_user_dictionary(user_dict_path: str | None) -> None:
    if user_dict_path is None:
        return

    try:
        path = Path(user_dict_path)
        if path.is_file():
            jieba.load_userdict(str(path))
    except (OSError, TypeError, UnicodeError, ValueError):
        return


def _is_single_chinese_character(token: str) -> bool:
    return (
        len(token) == 1
        and _SINGLE_CHINESE_CHARACTER_RE.fullmatch(token) is not None
    )


def _is_low_information_token(token: str) -> bool:
    """Return whether an ASCII token carries too little value for a word cloud."""
    return any(
        pattern.fullmatch(token) is not None
        for pattern in (
            _SINGLE_ASCII_LETTER_RE,
            _SHORT_INTEGER_RE,
            _DECK_QUANTITY_RE,
        )
    )
