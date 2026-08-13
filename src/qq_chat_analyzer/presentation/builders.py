"""Builders that turn analysis reports into display-ready view models.

The builder only reshapes and labels values that the analysis layer already
computed. It performs no counting, averaging, or sorting of raw messages.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..analysis.models import (
    ActivityReport,
    AnalysisReports,
    ConversationReport,
    MessageLengthReport,
    UserProfile,
    UserProfileReport,
)
from .formatters import (
    format_active_period,
    format_average,
    format_count,
    format_duration,
    format_hour,
    format_length_bucket,
    format_percent,
    format_weekday,
)
from .models import (
    ChartData,
    ChartKind,
    ChartPoint,
    ChartSeries,
    ConversationCard,
    DashboardView,
    EchoMemberCard,
    EchoReportView,
    MetricCard,
    UserCard,
)


DEFAULT_TITLE = "\u804a\u5929\u8bb0\u5f55\u5206\u6790\u6982\u89c8"
EMPTY_DESCRIPTION = "\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u5206\u6790\u7ed3\u679c\u3002"

DEFAULT_USER_CARD_LIMIT = 10
DEFAULT_CONVERSATION_CARD_LIMIT = 10
DEFAULT_TOP_WORD_LIMIT = 20
DEFAULT_PROFILE_WORD_LIMIT = 5
ECHO_REPORT_TITLE = "Echo Report"


class DashboardBuilder:
    """Assemble a :class:`DashboardView` from finished analysis reports."""

    def __init__(
        self,
        *,
        user_card_limit: int = DEFAULT_USER_CARD_LIMIT,
        conversation_card_limit: int = DEFAULT_CONVERSATION_CARD_LIMIT,
        top_word_limit: int = DEFAULT_TOP_WORD_LIMIT,
        profile_word_limit: int = DEFAULT_PROFILE_WORD_LIMIT,
    ) -> None:
        self._user_card_limit = max(0, user_card_limit)
        self._conversation_card_limit = max(0, conversation_card_limit)
        self._top_word_limit = max(0, top_word_limit)
        self._profile_word_limit = max(0, profile_word_limit)

    def build(
        self,
        reports: AnalysisReports | None,
        *,
        top_words: Sequence[object] = (),
        title: str = DEFAULT_TITLE,
    ) -> DashboardView:
        """Build the dashboard view for one analysis run.

        ``top_words`` accepts any sequence of objects exposing ``word`` and
        ``count`` attributes, so the caller may pass the existing word
        frequency results without the presentation layer depending on them.
        """
        reports = reports or AnalysisReports()
        activity = reports.activity
        message_length = reports.message_length
        user_profiles = reports.user_profiles
        conversations = reports.conversations

        summary_metrics = _build_summary_metrics(
            activity,
            message_length,
            user_profiles,
            conversations,
        )
        charts = _build_charts(
            activity,
            message_length,
            user_profiles,
            top_words,
            self._top_word_limit,
        )
        user_cards = _build_user_cards(
            user_profiles,
            self._user_card_limit,
            self._profile_word_limit,
        )
        conversation_cards = _build_conversation_cards(
            conversations,
            self._conversation_card_limit,
        )

        has_data = bool(
            summary_metrics or user_cards or conversation_cards
        ) or any(not chart.is_empty for chart in charts)

        return DashboardView(
            title=title,
            has_data=has_data,
            summary_metrics=summary_metrics,
            charts=charts,
            user_cards=user_cards,
            conversation_cards=conversation_cards,
            empty_description="" if has_data else EMPTY_DESCRIPTION,
        )


def build_dashboard_view(
    reports: AnalysisReports | None,
    *,
    top_words: Sequence[object] = (),
    title: str = DEFAULT_TITLE,
) -> DashboardView:
    """Convenience wrapper around :class:`DashboardBuilder`."""
    return DashboardBuilder().build(reports, top_words=top_words, title=title)


class EchoReportBuilder:
    """Reshape finished reports into the Phase A Echo presentation model."""

    def build(
        self,
        reports: AnalysisReports | None,
        *,
        viewer_speaker_key: str | None = None,
        conversation_kind: str = "unknown",
        title: str = ECHO_REPORT_TITLE,
    ) -> EchoReportView:
        reports = reports or AnalysisReports()
        activity = reports.activity
        profiles = reports.user_profiles
        conversation = (
            reports.conversations.conversations[0]
            if reports.conversations
            and reports.conversations.conversations
            else None
        )

        hourly_activity = tuple(
            ChartPoint(label=format_hour(entry.hour), value=float(entry.count))
            for entry in (activity.hourly_counts if activity else ())
        )
        weekday_activity = tuple(
            ChartPoint(
                label=format_weekday(entry.weekday),
                value=float(entry.count),
            )
            for entry in (activity.weekday_counts if activity else ())
        )
        members = tuple(
            _build_echo_member(profile, viewer_speaker_key, conversation_kind)
            for profile in (profiles.profiles if profiles else ())
        )
        total_message_count = activity.total_message_count if activity else 0
        participant_count = profiles.speaker_count if profiles else 0
        has_data = (
            activity is not None
            or profiles is not None
            or conversation is not None
        )

        return EchoReportView(
            title=title,
            has_data=has_data,
            conversation_kind=conversation_kind,
            conversation_name=(
                conversation.resolved_display_name if conversation else ""
            ),
            time_span=(
                format_duration(conversation.duration_seconds)
                if conversation
                else ""
            ),
            total_message_count=total_message_count,
            participant_count=participant_count,
            hourly_activity=hourly_activity,
            weekday_activity=weekday_activity,
            members=members,
            empty_description="" if has_data else EMPTY_DESCRIPTION,
        )


def build_echo_report_view(
    reports: AnalysisReports | None,
    *,
    viewer_speaker_key: str | None = None,
    conversation_kind: str = "unknown",
    title: str = ECHO_REPORT_TITLE,
) -> EchoReportView:
    """Build an Echo report, highlighting only an explicitly supplied key."""
    return EchoReportBuilder().build(
        reports,
        viewer_speaker_key=viewer_speaker_key,
        conversation_kind=conversation_kind,
        title=title,
    )


def _build_echo_member(
    profile: UserProfile,
    viewer_speaker_key: str | None,
    conversation_kind: str = "unknown",
) -> EchoMemberCard:
    speaker_key = profile.speaker_key or profile.speaker
    primary_name, secondary_name, contextual_name = resolve_member_names(
        remark=profile.remark,
        contextual_name=profile.contextual_name,
        nickname=profile.nickname,
        safe_display_fallback=profile.resolved_display_name,
        conversation_kind=conversation_kind,
    )
    return EchoMemberCard(
        speaker_key=speaker_key,
        display_name=primary_name,
        primary_name=primary_name,
        secondary_name=secondary_name,
        remark=profile.remark,
        contextual_name=contextual_name,
        is_viewer=(
            viewer_speaker_key is not None
            and speaker_key == viewer_speaker_key
        ),
        message_count=profile.message_count,
        message_share_percent=profile.message_share_percent,
        average_length=profile.average_length,
        max_length=profile.max_length,
        active_period=format_active_period(
            profile.busiest_hour,
            profile.busiest_weekday,
        ),
        hourly_activity=tuple(
            ChartPoint(label=format_hour(entry.hour), value=float(entry.count))
            for entry in profile.hourly_counts
        ),
        weekday_activity=tuple(
            ChartPoint(
                label=format_weekday(entry.weekday),
                value=float(entry.count),
            )
            for entry in profile.weekday_counts
        ),
        top_words=tuple(word.word for word in profile.top_words),
    )


def resolve_member_names(
    *,
    remark: str | None,
    contextual_name: str | None,
    nickname: str | None,
    safe_display_fallback: str,
    conversation_kind: str = "unknown",
) -> tuple[str, str | None, str | None]:
    """Resolve primary/secondary display names in the Python report layer."""
    if conversation_kind == "private":
        contextual = _first_non_empty(nickname, contextual_name)
    else:
        contextual = _first_non_empty(contextual_name, nickname)

    primary = (
        _first_non_empty(remark, contextual, safe_display_fallback)
        or safe_display_fallback
    )
    secondary = None
    if remark and contextual:
        if contextual.strip().casefold() != primary.strip().casefold():
            secondary = contextual
    return primary, secondary, contextual


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _build_summary_metrics(
    activity: ActivityReport | None,
    message_length: MessageLengthReport | None,
    user_profiles: UserProfileReport | None,
    conversations: ConversationReport | None,
) -> tuple[MetricCard, ...]:
    metrics: list[MetricCard] = []

    if activity is not None:
        metrics.append(
            MetricCard(
                key="total_messages",
                title="\u6d88\u606f\u6570\u91cf",
                value=format_count(activity.total_message_count),
                description="\u7eb3\u5165\u5206\u6790\u7684\u6d88\u606f\u603b\u6570\u3002",
            )
        )
        metrics.append(
            MetricCard(
                key="busiest_hour",
                title="\u6d3b\u8dc3\u65f6\u6bb5",
                value=format_hour(activity.busiest_hour),
                description="\u6d88\u606f\u6570\u91cf\u6700\u591a\u7684\u5c0f\u65f6\u3002",
            )
        )
        metrics.append(
            MetricCard(
                key="busiest_weekday",
                title="\u6d3b\u8dc3\u661f\u671f",
                value=format_weekday(activity.busiest_weekday),
                description="\u6d88\u606f\u6570\u91cf\u6700\u591a\u7684\u661f\u671f\u3002",
            )
        )

    if user_profiles is not None:
        metrics.append(
            MetricCard(
                key="speaker_count",
                title="\u53c2\u4e0e\u4eba\u6570",
                value=format_count(user_profiles.speaker_count),
                description="\u53d1\u8fc7\u6d88\u606f\u7684\u4eba\u6570\u3002",
            )
        )

    if message_length is not None:
        metrics.append(
            MetricCard(
                key="average_length",
                title="\u5e73\u5747\u957f\u5ea6",
                value=format_average(message_length.average_length),
                description="\u5355\u6761\u6d88\u606f\u7684\u5e73\u5747\u5b57\u6570\u3002",
            )
        )
        metrics.append(
            MetricCard(
                key="max_length",
                title="\u6700\u957f\u6d88\u606f",
                value=format_count(message_length.max_length),
                description="\u6700\u957f\u4e00\u6761\u6d88\u606f\u7684\u5b57\u6570\u3002",
            )
        )

    if conversations is not None:
        metrics.append(
            MetricCard(
                key="conversation_count",
                title="\u4f1a\u8bdd\u6570\u91cf",
                value=format_count(conversations.conversation_count),
                description="\u5206\u6790\u8986\u76d6\u7684\u4f1a\u8bdd\u6570\u3002",
            )
        )

    return tuple(metrics)


def _build_charts(
    activity: ActivityReport | None,
    message_length: MessageLengthReport | None,
    user_profiles: UserProfileReport | None,
    top_words: Sequence[object],
    top_word_limit: int,
) -> tuple[ChartData, ...]:
    charts: list[ChartData] = []

    if activity is not None:
        hourly_points = tuple(
            ChartPoint(label=format_hour(entry.hour), value=float(entry.count))
            for entry in activity.hourly_counts
        )
        charts.append(
            ChartData(
                key="activity_hourly",
                kind=ChartKind.LINE,
                title="\u6bcf\u5c0f\u65f6\u6d88\u606f\u5206\u5e03",
                series=(
                    ChartSeries(name="\u6d88\u606f\u6570", points=hourly_points),
                ),
                x_axis_label="\u5c0f\u65f6",
                y_axis_label="\u6d88\u606f\u6570",
            )
        )
        charts.append(
            ChartData(
                key="activity_hourly_heatmap",
                kind=ChartKind.HEATMAP,
                title="\u6d3b\u8dc3\u5ea6\u70ed\u529b\u56fe",
                series=(
                    ChartSeries(name="\u6d88\u606f\u6570", points=hourly_points),
                ),
                x_axis_label="\u5c0f\u65f6",
                y_axis_label="\u6d3b\u8dc3\u5ea6",
                description="\u6309\u5c0f\u65f6\u5c55\u793a\u6d88\u606f\u5bc6\u5ea6\u3002",
            )
        )
        charts.append(
            ChartData(
                key="activity_weekday",
                kind=ChartKind.BAR,
                title="\u6bcf\u661f\u671f\u6d88\u606f\u5206\u5e03",
                series=(
                    ChartSeries(
                        name="\u6d88\u606f\u6570",
                        points=tuple(
                            ChartPoint(
                                label=format_weekday(entry.weekday),
                                value=float(entry.count),
                            )
                            for entry in activity.weekday_counts
                        ),
                    ),
                ),
                x_axis_label="\u661f\u671f",
                y_axis_label="\u6d88\u606f\u6570",
            )
        )

    if message_length is not None:
        charts.append(
            ChartData(
                key="message_length_buckets",
                kind=ChartKind.BAR,
                title="\u6d88\u606f\u957f\u5ea6\u5206\u5e03",
                series=(
                    ChartSeries(
                        name="\u6d88\u606f\u6570",
                        points=tuple(
                            ChartPoint(
                                label=format_length_bucket(
                                    bucket.lower_bound,
                                    bucket.upper_bound,
                                ),
                                value=float(bucket.count),
                            )
                            for bucket in message_length.buckets
                        ),
                    ),
                ),
                x_axis_label="\u5b57\u6570\u533a\u95f4",
                y_axis_label="\u6d88\u606f\u6570",
            )
        )

    if user_profiles is not None:
        charts.append(
            ChartData(
                key="user_ranking",
                kind=ChartKind.RANKING,
                title="\u53d1\u8a00\u6570\u91cf\u6392\u884c",
                series=(
                    ChartSeries(
                        name="\u6d88\u606f\u6570",
                        points=tuple(
                            ChartPoint(
                                label=profile.resolved_display_name,
                                value=float(profile.message_count),
                            )
                            for profile in user_profiles.profiles
                        ),
                    ),
                ),
                x_axis_label="\u53d1\u8a00\u4eba",
                y_axis_label="\u6d88\u606f\u6570",
            )
        )

    word_points = tuple(
        ChartPoint(
            label=str(getattr(entry, "word", "")),
            value=float(getattr(entry, "count", 0)),
        )
        for entry in tuple(top_words)[:top_word_limit]
    )
    if word_points:
        charts.append(
            ChartData(
                key="top_words",
                kind=ChartKind.RANKING,
                title="\u9ad8\u9891\u8bcd",
                series=(ChartSeries(name="\u8bcd\u9891", points=word_points),),
                x_axis_label="\u8bcd\u8bed",
                y_axis_label="\u51fa\u73b0\u6b21\u6570",
            )
        )

    return tuple(charts)


def _build_user_cards(
    user_profiles: UserProfileReport | None,
    limit: int,
    profile_word_limit: int,
) -> tuple[UserCard, ...]:
    if user_profiles is None:
        return ()

    return tuple(
        UserCard(
            rank=index,
            sender=profile.resolved_display_name,
            message_count=profile.message_count,
            percentage=profile.message_share_percent,
            average_length=profile.average_length,
            percentage_display=format_percent(profile.message_share_percent),
            average_length_display=format_average(profile.average_length),
            active_period=format_active_period(
                profile.busiest_hour,
                profile.busiest_weekday,
            ),
            top_words=tuple(
                word.word for word in profile.top_words[:profile_word_limit]
            ),
        )
        for index, profile in enumerate(user_profiles.profiles[:limit], start=1)
    )


def _build_conversation_cards(
    conversations: ConversationReport | None,
    limit: int,
) -> tuple[ConversationCard, ...]:
    if conversations is None:
        return ()

    return tuple(
        ConversationCard(
            conversation_id=summary.resolved_display_name,
            message_count=summary.message_count,
            participant_count=summary.speaker_count,
            time_span=format_duration(summary.duration_seconds),
        )
        for summary in conversations.conversations[:limit]
    )
