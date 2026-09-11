"""Build a display-ready Echo share card from an existing Echo report view.

This module only reshapes values that the Echo report already computed. It
never reads messages, runs analyzers, or recomputes statistics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..formatters import format_count, format_duration
from ..models import (
    EchoExpressionCulture,
    EchoLanguageProfile,
    EchoReportView,
)


SHARE_TITLE = "ECHO"
SHARE_SUBTITLE = "这段聊天的回声"
SHARE_FOOTER = "每一句聊天，都会留下余音。"
SHARE_FOOTER_BRAND = "Echo · 本地生成"

_LOGGER = logging.getLogger("qq_chat_analyzer.presentation.share.builder")

_PRIVATE_LABEL = "私聊"
_GROUP_LABEL = "群聊"
_UNKNOWN_LABEL = "这段聊天"
_UNKNOWN_NAME = "一起留下的聊天"
_EMPTY_MESSAGE = "再多聊一阵，就能生成你们的聊天回声纪念卡。"
_LANGUAGE_FALLBACK = "样本还不够，暂时看不清这段聊天的语言印记。"
_EXPRESSION_FALLBACK = "表达样本还不够，等更多表情出现后再生成。"

_CN_NUMBERS = (
    "零",
    "一",
    "二",
    "三",
    "四",
    "五",
    "六",
    "七",
    "八",
    "九",
    "十",
    "十一",
    "十二",
)


@dataclass(frozen=True, slots=True)
class ShareExpressionCombo:
    """One representative expression pair shown on the share card."""

    primary_text: str = ""
    primary_asset_key: str | None = None
    secondary_text: str | None = None
    secondary_asset_key: str | None = None
    count: int | None = None


@dataclass(frozen=True, slots=True)
class ShareSessions:
    """Human-ready chat-session facts for the share card."""

    available: bool
    headline: str = ""
    average_label: str = "平均每轮"
    average_value: str = ""
    longest_label: str = "最长的一轮"
    longest_value: str = ""


@dataclass(frozen=True, slots=True)
class ShareRhythm:
    """Peak-time phrases selected from the existing activity distribution."""

    available: bool
    hour_label: str = "一天中最热闹的时候"
    hour_value: str = ""
    weekday_label: str = "你们最常聊天的一天"
    weekday_value: str = ""


@dataclass(frozen=True, slots=True)
class ShareLanguage:
    """Language-profile content for one share card."""

    available: bool
    heading: str = "留下你们痕迹的词"
    words: tuple[str, ...] = ()
    self_heading: str | None = None
    self_words: tuple[str, ...] = ()
    peer_heading: str | None = None
    peer_words: tuple[str, ...] = ()
    fallback: str = _LANGUAGE_FALLBACK


@dataclass(frozen=True, slots=True)
class ShareExpressions:
    """Expression-culture content for one share card."""

    available: bool
    heading: str = "你们最有来有回的表达"
    combos: tuple[ShareExpressionCombo, ...] = ()
    fallback: str = _EXPRESSION_FALLBACK


@dataclass(frozen=True, slots=True)
class ShareCardData:
    """Complete display payload for the Echo share card template."""

    has_data: bool
    title: str = SHARE_TITLE
    subtitle: str = SHARE_SUBTITLE
    conversation_label: str = _UNKNOWN_LABEL
    conversation_name: str = _UNKNOWN_NAME
    message_count_display: str = "0"
    time_span_display: str = "刚刚开始"
    sessions: ShareSessions | None = None
    rhythm: ShareRhythm | None = None
    language: ShareLanguage | None = None
    expressions: ShareExpressions | None = None
    footer: str = SHARE_FOOTER
    footer_brand: str = SHARE_FOOTER_BRAND
    empty_message: str = _EMPTY_MESSAGE


def build_share_card_data(view: EchoReportView | None) -> ShareCardData:
    """Turn one Echo report view into share-card display content."""
    if view is None:
        return ShareCardData(has_data=False)

    has_data = bool(view.has_data and view.total_message_count > 0)
    _LOGGER.info("[share] building image has_data=%s", has_data)
    conversation_label, conversation_name = _conversation_header(view)
    return ShareCardData(
        has_data=has_data,
        conversation_label=conversation_label,
        conversation_name=conversation_name,
        message_count_display=format_count(view.total_message_count),
        time_span_display=view.time_span or "刚刚开始",
        sessions=_build_sessions(view.conversation_sessions),
        rhythm=_build_rhythm(view.hourly_activity, view.weekday_activity),
        language=_build_language(view.language_profile),
        expressions=_build_expressions(view.expression_culture),
    )


def _conversation_header(
    view: EchoReportView,
) -> tuple[str, str]:
    if view.conversation_kind == "private":
        return _PRIVATE_LABEL, _private_names(view)
    if view.conversation_kind == "group":
        return _GROUP_LABEL, view.conversation_name or "这个群聊"
    return _UNKNOWN_LABEL, view.conversation_name or _UNKNOWN_NAME


def _private_names(view: EchoReportView) -> str:
    members = tuple(view.members or ())
    if len(members) >= 2:
        viewer = next((member for member in members if member.is_viewer), None)
        if viewer is not None:
            peer = next(
                (member for member in members if member is not viewer),
                None,
            )
            peer_name = peer.display_name if peer is not None else "TA"
            return f"你 & {peer_name}"
        return f"{members[0].display_name} & {members[1].display_name}"
    if view.conversation_name:
        return view.conversation_name
    return "你 & TA"


def _build_sessions(sessions: object | None) -> ShareSessions | None:
    if sessions is None or getattr(sessions, "session_count", 0) <= 0:
        return None
    headline = f"你们一共聊了 {format_count(sessions.session_count)} 轮"
    average_value = ""
    if sessions.average_message_count > 0:
        average_value = f"{sessions.average_message_count:.1f} 条消息"
    longest_value = ""
    if sessions.longest_duration_seconds > 0:
        longest_value = format_duration(sessions.longest_duration_seconds)
    return ShareSessions(
        available=True,
        headline=headline,
        average_value=average_value,
        longest_value=longest_value,
    )


def _build_rhythm(
    hourly: object,
    weekday: object,
) -> ShareRhythm | None:
    hour_point = _peak_point(hourly)
    weekday_point = _peak_point(weekday)
    if hour_point is None and weekday_point is None:
        return None
    return ShareRhythm(
        available=True,
        hour_value=_hour_phrase(_hour_from_label(hour_point.label))
        if hour_point is not None
        else "",
        weekday_value=weekday_point.label if weekday_point is not None else "",
    )


def _peak_point(points: object):
    values = tuple(points or ())
    if not values:
        return None
    return max(values, key=lambda point: point.value)


def _hour_from_label(label: str) -> int | None:
    try:
        return int(label.split(":", 1)[0])
    except (ValueError, TypeError, IndexError):
        return None


def _hour_phrase(hour: int | None) -> str:
    if hour is None:
        return ""
    if hour == 0:
        phrase = "凌晨零点"
    elif 1 <= hour <= 5:
        phrase = f"凌晨{_CN_NUMBERS[hour]}点"
    elif 6 <= hour <= 11:
        phrase = f"上午{_CN_NUMBERS[hour]}点"
    elif hour == 12:
        phrase = "中午十二点"
    elif 13 <= hour <= 17:
        phrase = f"下午{_CN_NUMBERS[hour - 12]}点"
    else:
        phrase = f"晚上{_CN_NUMBERS[hour - 12]}点"
    return f"{phrase}左右"


def _build_language(profile: EchoLanguageProfile | None) -> ShareLanguage:
    if profile is None or not profile.available:
        fallback = (
            profile.unavailable_reason
            if profile is not None and profile.unavailable_reason
            else _LANGUAGE_FALLBACK
        )
        return ShareLanguage(available=False, fallback=fallback)

    if profile.mode == "private_common":
        return _private_language(profile)

    words: list[str] = []
    for member in profile.members:
        words.extend(member.primary_words)
    return ShareLanguage(
        available=bool(words),
        words=_dedupe(words, 8),
        fallback=profile.unavailable_reason or _LANGUAGE_FALLBACK,
    )


def _private_language(profile: EchoLanguageProfile) -> ShareLanguage:
    members = tuple(profile.members or ())
    if len(members) < 2:
        return ShareLanguage(
            available=False,
            fallback=profile.unavailable_reason or _LANGUAGE_FALLBACK,
        )
    self_member = next(
        (
            member
            for member in members
            if member.heading.startswith("你")
        ),
        None,
    )
    if self_member is None:
        words = _dedupe(
            [
                word
                for member in members
                for word in member.primary_words
            ],
            8,
        )
        return ShareLanguage(available=True, words=words)
    peer_member = next(
        (member for member in members if member is not self_member),
        None,
    )
    return ShareLanguage(
        available=True,
        self_heading="你的习惯表达",
        self_words=_dedupe(self_member.primary_words, 5),
        peer_heading="TA 的习惯表达",
        peer_words=(
            _dedupe(peer_member.primary_words, 5)
            if peer_member is not None
            else ()
        ),
    )


def _build_expressions(
    culture: EchoExpressionCulture | None,
) -> ShareExpressions:
    if culture is None or not culture.available:
        fallback = (
            culture.unavailable_reason
            if culture is not None and culture.unavailable_reason
            else _EXPRESSION_FALLBACK
        )
        return ShareExpressions(available=False, fallback=fallback)
    return ShareExpressions(
        available=True,
        combos=_expression_combos(culture),
    )


def _expression_combos(culture: EchoExpressionCulture) -> tuple[ShareExpressionCombo, ...]:
    combos: list[ShareExpressionCombo] = []
    for item in culture.top_expressions:
        secondary = next(
            (word for word in item.nearby_words if word),
            None,
        )
        combos.append(
            ShareExpressionCombo(
                primary_text=item.display_text or "表情",
                primary_asset_key=item.asset_key,
                secondary_text=secondary,
                count=item.count,
            )
        )
        if len(combos) >= 3:
            break
    if combos:
        return tuple(combos)

    for combination in culture.top_combinations:
        keys = tuple(getattr(combination, "asset_keys", ()) or ())
        combos.append(
            ShareExpressionCombo(
                primary_asset_key=keys[0] if keys else None,
                secondary_asset_key=keys[1] if len(keys) > 1 else None,
                count=combination.count,
            )
        )
        if len(combos) >= 3:
            break
    return tuple(combos)


def _dedupe(words: object, limit: int) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for word in words or ():
        if not isinstance(word, str) or not word:
            continue
        if word in seen:
            continue
        seen.add(word)
        result.append(word)
        if len(result) >= limit:
            break
    return tuple(result)


__all__ = [
    "SHARE_FOOTER",
    "SHARE_FOOTER_BRAND",
    "SHARE_SUBTITLE",
    "SHARE_TITLE",
    "ShareCardData",
    "ShareExpressionCombo",
    "ShareExpressions",
    "ShareLanguage",
    "ShareRhythm",
    "ShareSessions",
    "build_share_card_data",
]
