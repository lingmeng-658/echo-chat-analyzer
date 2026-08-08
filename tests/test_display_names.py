"""Behavior tests for the sender/conversation display-name mapping.

The mapping is injected by callers so the analysis core never learns about
QQ or WeChat. Every fixture below is fictional.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


def _presentation():
    return importlib.import_module("qq_chat_analyzer.presentation")


def _analysis_models():
    return importlib.import_module("qq_chat_analyzer.analysis.models")


def _user_profile_analyzer():
    module = importlib.import_module(
        "qq_chat_analyzer.analysis.analyzers.user_profile_analyzer"
    )
    return module.UserProfileAnalyzer()


def _conversation_analyzer():
    module = importlib.import_module(
        "qq_chat_analyzer.analysis.analyzers.conversation_analyzer"
    )
    return module.ConversationAnalyzer()


def _message(
    sender: str,
    text: str = "hello",
    timestamp: int = 1704099600,
    conversation_id: str | None = None,
):
    message_module = importlib.import_module("qq_chat_analyzer.message")
    return message_module.ChatMessage(
        timestamp=timestamp,
        sender=sender,
        message_type="text",
        text=text,
        conversation_id=conversation_id,
    )


def _reports_from(profile_report):
    models = _analysis_models()
    return models.AnalysisReports(user_profiles=profile_report)


# ------------------------------------------------------- analyzer level


def test_profile_uses_the_injected_display_name() -> None:
    report = _user_profile_analyzer().analyze(
        [_message("wxid_a")],
        speaker_names={"wxid_a": "\u5f20\u4e09"},
    )

    profile = report.profiles[0]
    assert profile.speaker == "wxid_a"
    assert profile.display_name == "\u5f20\u4e09"
    assert profile.resolved_display_name == "\u5f20\u4e09"


def test_profile_falls_back_to_the_raw_sender() -> None:
    report = _user_profile_analyzer().analyze([_message("wxid_a")])

    profile = report.profiles[0]
    assert profile.display_name is None
    assert profile.resolved_display_name == "wxid_a"


def test_partial_mapping_only_renames_known_senders() -> None:
    report = _user_profile_analyzer().analyze(
        [_message("wxid_a"), _message("wxid_b")],
        speaker_names={"wxid_a": "\u5f20\u4e09"},
    )

    resolved = {
        profile.speaker: profile.resolved_display_name
        for profile in report.profiles
    }
    assert resolved == {"wxid_a": "\u5f20\u4e09", "wxid_b": "wxid_b"}


def test_blank_display_names_are_ignored() -> None:
    report = _user_profile_analyzer().analyze(
        [_message("wxid_a")],
        speaker_names={"wxid_a": "   "},
    )

    assert report.profiles[0].resolved_display_name == "wxid_a"


def test_conversation_uses_the_injected_display_name() -> None:
    report = _conversation_analyzer().analyze(
        [_message("wxid_a", conversation_id="room@chatroom")],
        conversation_names={"room@chatroom": "\u865a\u6784\u4ea4\u6d41\u7fa4"},
    )

    summary = report.conversations[0]
    assert summary.conversation_id == "room@chatroom"
    assert summary.resolved_display_name == "\u865a\u6784\u4ea4\u6d41\u7fa4"


def test_conversation_without_mapping_hides_the_raw_id() -> None:
    report = _conversation_analyzer().analyze(
        [_message("wxid_a", conversation_id="room@chatroom")]
    )

    summary = report.conversations[0]
    assert summary.resolved_display_name == "\u672a\u77e5\u4f1a\u8bdd"


# --------------------------------------------------- presentation level


def test_user_card_shows_the_mapped_display_name() -> None:
    presentation = _presentation()
    report = _user_profile_analyzer().analyze(
        [_message("wxid_a")],
        speaker_names={"wxid_a": "\u5f20\u4e09"},
    )

    view = presentation.build_dashboard_view(_reports_from(report))

    assert view.user_cards[0].sender == "\u5f20\u4e09"


def test_user_card_falls_back_to_the_raw_sender() -> None:
    presentation = _presentation()
    report = _user_profile_analyzer().analyze([_message("wxid_a")])

    view = presentation.build_dashboard_view(_reports_from(report))

    assert view.user_cards[0].sender == "wxid_a"


def test_user_ranking_chart_uses_display_names() -> None:
    presentation = _presentation()
    report = _user_profile_analyzer().analyze(
        [_message("wxid_a"), _message("wxid_a"), _message("wxid_b")],
        speaker_names={"wxid_a": "\u5f20\u4e09"},
    )

    view = presentation.build_dashboard_view(_reports_from(report))

    labels = {
        point.label
        for chart in view.charts
        for series in chart.series
        for point in series.points
    }
    assert "\u5f20\u4e09" in labels
    assert "wxid_a" not in labels


def test_conversation_card_never_exposes_the_internal_id() -> None:
    presentation = _presentation()
    models = _analysis_models()
    report = _conversation_analyzer().analyze(
        [_message("wxid_a", conversation_id="room@chatroom")],
        conversation_names={"room@chatroom": "\u865a\u6784\u4ea4\u6d41\u7fa4"},
    )

    view = presentation.build_dashboard_view(
        models.AnalysisReports(conversations=report)
    )

    card = view.conversation_cards[0]
    assert card.conversation_id == "\u865a\u6784\u4ea4\u6d41\u7fa4"
    assert "@chatroom" not in card.conversation_id


# ------------------------------------------- conversation id fallback


def test_display_name_wins_over_a_readable_conversation_id() -> None:
    models = _analysis_models()

    summary = models.ConversationSummary(
        conversation_id="fictional-room-1",
        message_count=1,
        speaker_count=1,
        display_name="\u865a\u6784\u4ea4\u6d41\u7fa4",
    )

    assert summary.resolved_display_name == "\u865a\u6784\u4ea4\u6d41\u7fa4"


def test_readable_conversation_id_is_used_as_fallback() -> None:
    models = _analysis_models()

    summary = models.ConversationSummary(
        conversation_id="fictional-room-1",
        message_count=1,
        speaker_count=1,
    )

    assert summary.resolved_display_name == "fictional-room-1"


def test_wxid_conversation_id_stays_hidden() -> None:
    models = _analysis_models()

    summary = models.ConversationSummary(
        conversation_id="wxid_abc123",
        message_count=1,
        speaker_count=1,
    )

    assert summary.resolved_display_name == "\u672a\u77e5\u4f1a\u8bdd"


def test_chatroom_conversation_id_stays_hidden() -> None:
    models = _analysis_models()

    summary = models.ConversationSummary(
        conversation_id="12345678@chatroom",
        message_count=1,
        speaker_count=1,
    )

    assert summary.resolved_display_name == "\u672a\u77e5\u4f1a\u8bdd"


def test_missing_conversation_id_stays_hidden() -> None:
    models = _analysis_models()

    summary = models.ConversationSummary(
        conversation_id=None,
        message_count=1,
        speaker_count=1,
    )

    assert summary.resolved_display_name == "\u672a\u77e5\u4f1a\u8bdd"


def test_internal_id_detection_is_case_insensitive() -> None:
    models = _analysis_models()

    assert not models.is_displayable_conversation_id("WXID_ABC")
    assert not models.is_displayable_conversation_id("1234@ChatRoom")
    assert not models.is_displayable_conversation_id("   ")
    assert models.is_displayable_conversation_id("fictional-room-1")
