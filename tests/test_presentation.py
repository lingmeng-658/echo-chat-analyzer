"""Behavior tests for the analysis presentation layer."""

from __future__ import annotations

import dataclasses
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


def _hourly(counts: dict[int, int]):
    models = _analysis_models()
    return tuple(
        models.HourlyActivity(hour=hour, count=counts.get(hour, 0))
        for hour in range(24)
    )


def _weekday(counts: dict[int, int]):
    models = _analysis_models()
    return tuple(
        models.WeekdayActivity(weekday=weekday, count=counts.get(weekday, 0))
        for weekday in range(7)
    )


def _activity_report(
    *,
    total: int = 3,
    dated: int = 3,
    busiest_hour: int | None = 9,
    busiest_weekday: int | None = 0,
):
    models = _analysis_models()
    return models.ActivityReport(
        total_message_count=total,
        dated_message_count=dated,
        hourly_counts=_hourly({9: 2, 21: 1}),
        weekday_counts=_weekday({0: 3}),
        busiest_hour=busiest_hour,
        busiest_weekday=busiest_weekday,
    )


def _message_length_report():
    models = _analysis_models()
    return models.MessageLengthReport(
        message_count=3,
        average_length=6.0,
        max_length=10,
        buckets=(
            models.LengthBucket(lower_bound=0, upper_bound=10, count=2),
            models.LengthBucket(lower_bound=10, upper_bound=None, count=1),
        ),
        speaker_lengths=(
            models.SpeakerLength(
                speaker="Fictional-Alice",
                message_count=2,
                average_length=4.0,
                max_length=5,
            ),
        ),
    )


def _user_profile_report(profile_count: int = 2):
    models = _analysis_models()
    profiles = (
        models.UserProfile(
            speaker="Fictional-Alice",
            message_count=3,
            message_share_percent=75.0,
            average_length=4.0,
            max_length=5,
            busiest_hour=9,
            busiest_weekday=0,
            top_words=(
                models.ProfileWord(word="deck", count=2),
                models.ProfileWord(word="talk", count=1),
            ),
        ),
        models.UserProfile(
            speaker="Fictional-Bob",
            message_count=1,
            message_share_percent=25.0,
            average_length=6.0,
            max_length=6,
            busiest_hour=None,
            busiest_weekday=None,
        ),
    )[:profile_count]
    return models.UserProfileReport(
        total_message_count=sum(profile.message_count for profile in profiles),
        speaker_count=len(profiles),
        profiles=profiles,
    )


def _conversation_report(conversation_count: int = 2):
    models = _analysis_models()
    conversations = (
        models.ConversationSummary(
            conversation_id="fictional-room-1",
            message_count=2,
            speaker_count=2,
            start_timestamp=1704099600,
            end_timestamp=1704106800,
            duration_seconds=7200,
        ),
        models.ConversationSummary(
            conversation_id=None,
            message_count=1,
            speaker_count=1,
            duration_seconds=None,
        ),
    )[:conversation_count]
    return models.ConversationReport(
        conversation_count=len(conversations),
        conversations=conversations,
    )


def _full_reports():
    models = _analysis_models()
    return models.AnalysisReports(
        activity=_activity_report(),
        message_length=_message_length_report(),
        user_profiles=_user_profile_report(),
        conversations=_conversation_report(),
    )


def _chart_by_key(view, key: str):
    for chart in view.charts:
        if chart.key == key:
            return chart
    raise AssertionError(f"chart {key} not found")


def _metric_by_key(view, key: str):
    for metric in view.summary_metrics:
        if metric.key == key:
            return metric
    raise AssertionError(f"metric {key} not found")


def test_presentation_models_are_immutable_dataclasses() -> None:
    presentation = _presentation()

    for model_type in (
        presentation.DashboardView,
        presentation.MetricCard,
        presentation.ChartData,
        presentation.ChartPoint,
        presentation.ChartSeries,
        presentation.UserCard,
        presentation.ConversationCard,
        presentation.EchoReportView,
        presentation.EchoMemberCard,
    ):
        assert dataclasses.is_dataclass(model_type)

    card = presentation.MetricCard(key="k", title="t", value="1")
    assert not hasattr(card, "__dict__")


def test_echo_report_builder_reuses_reports_and_highlights_explicit_viewer() -> None:
    presentation = _presentation()

    view = presentation.EchoReportBuilder().build(
        _full_reports(),
        viewer_speaker_key="Fictional-Bob",
    )

    assert view.has_data is True
    assert view.total_message_count == 3
    assert view.participant_count == 2
    assert len(view.hourly_activity) == 24
    assert len(view.weekday_activity) == 7
    assert [card.speaker_key for card in view.members] == [
        "Fictional-Alice",
        "Fictional-Bob",
    ]
    alice, bob = view.members
    assert alice.is_viewer is False
    assert bob.is_viewer is True


def test_echo_report_builder_never_guesses_viewer_identity() -> None:
    presentation = _presentation()

    view = presentation.build_echo_report_view(_full_reports())

    assert all(not member.is_viewer for member in view.members)


def test_echo_member_card_carries_member_activity_without_recalculation() -> None:
    presentation = _presentation()
    models = _analysis_models()
    profile = models.UserProfile(
        speaker="Fictional-Alice",
        message_count=2,
        message_share_percent=100.0,
        average_length=4.0,
        max_length=5,
        hourly_counts=_hourly({9: 2}),
        weekday_counts=_weekday({0: 2}),
    )
    reports = models.AnalysisReports(
        activity=_activity_report(total=2, dated=2),
        user_profiles=models.UserProfileReport(
            total_message_count=2,
            speaker_count=1,
            profiles=(profile,),
        ),
        conversations=_conversation_report(conversation_count=1),
    )

    card = presentation.build_echo_report_view(reports).members[0]

    assert card.hourly_activity[9].value == 2.0
    assert card.weekday_activity[0].value == 2.0


def test_echo_report_handles_missing_reports() -> None:
    presentation = _presentation()

    view = presentation.build_echo_report_view(None, viewer_speaker_key="nobody")

    assert view.has_data is False
    assert view.total_message_count == 0
    assert view.participant_count == 0
    assert view.members == ()


def test_chart_kind_supports_every_required_shape() -> None:
    presentation = _presentation()

    kinds = {kind.value for kind in presentation.ChartKind}
    assert {"bar", "line", "heatmap", "ranking"} <= kinds


def test_build_dashboard_view_handles_empty_reports() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(None)

    assert view.has_data is False
    assert view.summary_metrics == ()
    assert view.charts == ()
    assert view.user_cards == ()
    assert view.conversation_cards == ()
    assert view.empty_description != ""
    assert view.title != ""


def test_build_dashboard_view_handles_reports_without_any_message() -> None:
    presentation = _presentation()
    models = _analysis_models()
    reports = models.AnalysisReports(
        activity=models.ActivityReport(
            total_message_count=0,
            dated_message_count=0,
            hourly_counts=_hourly({}),
            weekday_counts=_weekday({}),
        ),
        user_profiles=models.UserProfileReport(total_message_count=0),
        conversations=models.ConversationReport(conversation_count=0),
    )

    view = presentation.build_dashboard_view(reports)

    assert view.has_data is True
    assert _metric_by_key(view, "total_messages").value == "0"
    assert _metric_by_key(view, "busiest_hour").value == "\u65f6\u95f4\u672a\u77e5"
    assert view.user_cards == ()
    assert view.conversation_cards == ()
    assert _chart_by_key(view, "activity_hourly").is_empty is False


def test_build_dashboard_view_reports_single_user() -> None:
    presentation = _presentation()
    models = _analysis_models()
    reports = models.AnalysisReports(
        activity=_activity_report(),
        user_profiles=_user_profile_report(profile_count=1),
    )

    view = presentation.build_dashboard_view(reports)

    assert len(view.user_cards) == 1
    card = view.user_cards[0]
    assert card.rank == 1
    assert card.sender == "Fictional-Alice"
    assert card.message_count == 3
    assert card.percentage == 75.0
    assert card.percentage_display == "75.0%"
    assert card.average_length_display == "4.0 \u5b57"
    assert card.top_words == ("deck", "talk")
    assert _metric_by_key(view, "speaker_count").value == "1"


def test_build_dashboard_view_ranks_multiple_users() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(_full_reports())

    assert [card.sender for card in view.user_cards] == [
        "Fictional-Alice",
        "Fictional-Bob",
    ]
    assert [card.rank for card in view.user_cards] == [1, 2]
    ranking = _chart_by_key(view, "user_ranking")
    assert ranking.kind is presentation.ChartKind.RANKING
    assert ranking.series[0].points[0].label == "Fictional-Alice"
    assert ranking.series[0].points[0].value == 3.0


def test_user_card_describes_active_period_and_unknown_time() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(_full_reports())
    cards = {card.sender: card for card in view.user_cards}

    assert cards["Fictional-Alice"].active_period == "\u5468\u4e00 09:00-09:59"
    assert cards["Fictional-Bob"].active_period == "\u65f6\u95f4\u672a\u77e5"


def test_build_dashboard_view_reports_multiple_conversations() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(_full_reports())

    assert len(view.conversation_cards) == 2
    first, second = view.conversation_cards
    assert first.conversation_id == "fictional-room-1"
    assert first.message_count == 2
    assert first.participant_count == 2
    assert first.time_span == "2 \u5c0f\u65f6 0 \u5206\u949f"
    assert second.conversation_id == "\u672a\u77e5\u4f1a\u8bdd"
    assert second.time_span == "\u65f6\u95f4\u672a\u77e5"
    assert _metric_by_key(view, "conversation_count").value == "2"


def test_activity_report_converts_into_hourly_and_weekday_charts() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(_full_reports())
    hourly = _chart_by_key(view, "activity_hourly")
    weekday = _chart_by_key(view, "activity_weekday")

    assert hourly.kind is presentation.ChartKind.LINE
    assert len(hourly.series[0].points) == 24
    assert hourly.series[0].points[9].label == "09:00-09:59"
    assert hourly.series[0].points[9].value == 2.0
    assert weekday.kind is presentation.ChartKind.BAR
    assert len(weekday.series[0].points) == 7
    assert weekday.series[0].points[0].label == "\u5468\u4e00"
    assert weekday.series[0].points[0].value == 3.0


def test_activity_report_also_produces_a_heatmap_chart() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(_full_reports())
    heatmap = _chart_by_key(view, "activity_hourly_heatmap")

    assert heatmap.kind is presentation.ChartKind.HEATMAP
    assert len(heatmap.series[0].points) == 24


def test_message_length_buckets_convert_into_a_bar_chart() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(_full_reports())
    chart = _chart_by_key(view, "message_length_buckets")

    assert chart.kind is presentation.ChartKind.BAR
    assert [point.label for point in chart.series[0].points] == ["0-9", "10+"]
    assert [point.value for point in chart.series[0].points] == [2.0, 1.0]
    assert _metric_by_key(view, "average_length").value == "6.0 \u5b57"


def test_top_words_render_as_a_ranking_chart_when_supplied() -> None:
    presentation = _presentation()

    class _Word:
        def __init__(self, word: str, count: int) -> None:
            self.word = word
            self.count = count

    view = presentation.build_dashboard_view(
        _full_reports(),
        top_words=(_Word("deck", 5), _Word("trade", 2)),
    )
    chart = _chart_by_key(view, "top_words")

    assert chart.kind is presentation.ChartKind.RANKING
    assert [point.label for point in chart.series[0].points] == ["deck", "trade"]
    assert chart.series[0].points[0].value == 5.0


def test_top_words_chart_is_absent_without_supplied_words() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(_full_reports())

    assert all(chart.key != "top_words" for chart in view.charts)


def test_builder_limits_cards_and_words() -> None:
    presentation = _presentation()

    view = presentation.DashboardBuilder(
        user_card_limit=1,
        conversation_card_limit=1,
        profile_word_limit=1,
    ).build(_full_reports())

    assert len(view.user_cards) == 1
    assert view.user_cards[0].top_words == ("deck",)
    assert len(view.conversation_cards) == 1


def test_builder_accepts_a_custom_title() -> None:
    presentation = _presentation()

    view = presentation.build_dashboard_view(
        _full_reports(),
        title="\u865a\u6784\u62a5\u544a",
    )

    assert view.title == "\u865a\u6784\u62a5\u544a"


def test_duration_formatting_covers_common_spans() -> None:
    presentation = _presentation()

    assert presentation.format_duration(None) == "\u65f6\u95f4\u672a\u77e5"
    assert presentation.format_duration(30) == "30 \u79d2"
    assert presentation.format_duration(600) == "10 \u5206\u949f"
    assert presentation.format_duration(7200) == "2 \u5c0f\u65f6 0 \u5206\u949f"
    assert presentation.format_duration(172800) == "2 \u5929 0 \u5c0f\u65f6"


def test_presentation_layer_does_not_import_gui_frameworks() -> None:
    builders = importlib.import_module("qq_chat_analyzer.presentation.builders")
    source = Path(builders.__file__).read_text(encoding="utf-8")

    for forbidden in ("PyQt", "PySide", "tkinter", "flask", "django"):
        assert forbidden not in source
