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
                          DistinctiveWordAvailability,
                          ExpressionCombinationUsage,
                          ExpressionReport,
                          ExpressionUsage,
    MessageLengthReport,
    UserProfile,
    UserProfileReport,
)
from ..analysis.conversation_sessions import ConversationSessionReport
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
from .expression_assets import resolve_wechat_asset_key
from ..analysis.conversation_sessions import (
    ConversationSession,
)
from .models import (
    ChartData,
    ChartKind,
    ChartPoint,
    ChartSeries,
    ConversationCard,
    DashboardView,
                          EchoMemberCard,
                          EchoExpressionCombination,
                          EchoExpressionCombinationMember,
                          EchoExpressionCulture,
    EchoExpressionItem,
    EchoMemberExpression,
    EchoLanguageMember,
    EchoLanguageProfile,
    EchoConversationSession,
    EchoConversationSessions,
    EchoExpressionHabits,
    EchoReportView,
    EchoSharedWord,
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
ECHO_LANGUAGE_PRIMARY_WORD_LIMIT = 5
ECHO_LANGUAGE_CONTEXT_WORD_LIMIT = 3
ECHO_GROUP_INSUFFICIENT_REASON = "样本不足，暂时无法比较成员特色词。"
ECHO_PRIVATE_INSUFFICIENT_REASON = "需要双方都有可用资料，才能展示两种声音。"
ECHO_UNKNOWN_CONVERSATION_REASON = "当前会话类型无法确定，暂不展示语言画像。"
ECHO_PRIVATE_SHARED_TOP_LIMIT = 8
ECHO_PRIVATE_SIDE_TOP_LIMIT = 6
ECHO_PRIVATE_SIDE_MIN_OCCURRENCE = 2
ECHO_EXPRESSION_TOP_LIMIT = 5
ECHO_EXPRESSION_MEMBER_TOP_LIMIT = 3
ECHO_EXPRESSION_MIN_COUNT = 2
ECHO_EXPRESSION_COMBINATION_TOP_LIMIT = 3
ECHO_EXPRESSION_COMBINATION_MIN_COUNT = 2
ECHO_EXPRESSION_COMBINATION_MEMBER_LIMIT = 4
ECHO_EXPRESSION_COMBINATION_MEMBER_SHARE_MIN = 20.0


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
            conversation_sessions=_build_echo_sessions(
                reports.conversation_sessions,
                members=members,
            ),
            language_profile=_build_echo_language_profile(
                reports,
                members=members,
                conversation_kind=conversation_kind,
                viewer_speaker_key=viewer_speaker_key,
            ),
            expression_culture=_build_echo_expression_culture(
                reports.expression,
                members=members,
            ),
            empty_description="" if has_data else EMPTY_DESCRIPTION,
            active_days=(reports.activity.active_days if reports.activity else 0),
            average_messages_per_active_day=(
                reports.activity.average_messages_per_active_day
                if reports.activity
                else 0.0
            ),
        )


def _build_echo_language_profile(
    reports: AnalysisReports,
    *,
    members: tuple[EchoMemberCard, ...],
    conversation_kind: str,
    viewer_speaker_key: str | None,
) -> EchoLanguageProfile:
    member_by_key = {member.speaker_key: member for member in members}

    if conversation_kind == "group":
        report = reports.distinctive_words
        if report is None or not report.available:
            reason = (
                ECHO_GROUP_INSUFFICIENT_REASON
                if report is not None
                and report.availability
                is DistinctiveWordAvailability.INSUFFICIENT_MEMBERS
                else "暂无可用的群聊特色词分析。"
            )
            return EchoLanguageProfile(
                mode="group_distinctive",
                available=False,
                unavailable_reason=reason,
            )
        language_members = []
        for distinctive_member in report.members:
            member = member_by_key.get(distinctive_member.speaker_key)
            if member is None:
                continue
            language_members.append(
                EchoLanguageMember(
                    speaker_key=member.speaker_key,
                    display_name=member.display_name,
                    heading=member.display_name,
                    primary_words=tuple(
                        word.word
                        for word in distinctive_member.words[
                            :ECHO_LANGUAGE_PRIMARY_WORD_LIMIT
                        ]
                    ),
                    context_words=member.top_words[
                        :ECHO_LANGUAGE_CONTEXT_WORD_LIMIT
                    ],
                )
            )
        return EchoLanguageProfile(
            mode="group_distinctive",
            available=bool(language_members),
            members=tuple(language_members),
            unavailable_reason=(
                "" if language_members else "暂无可展示的成员特色词。"
            ),
        )

    if conversation_kind == "private":
        known_viewer_key = (
            viewer_speaker_key
            if any(member.is_viewer for member in members)
            else None
        )
        profile_by_key = {
            (profile.speaker_key or profile.speaker): profile
            for profile in (
                reports.user_profiles.profiles
                if reports.user_profiles is not None
                else ()
            )
        }
        language_members = tuple(
            EchoLanguageMember(
                speaker_key=member.speaker_key,
                display_name=member.display_name,
                heading=_private_voice_heading(
                    member,
                    viewer_speaker_key=known_viewer_key,
                ),
                primary_words=member.top_words[
                    :ECHO_LANGUAGE_PRIMARY_WORD_LIMIT
                ],
                expression_habits=_echo_expression_habits(
                    profile_by_key.get(member.speaker_key)
                ),
            )
            for member in members
        )
        available = len(language_members) == 2
        shared_words, side_words = _private_shared_word_layers(
            reports.private_language,
            viewer_key=known_viewer_key,
            member_keys={
                member.speaker_key for member in language_members
            },
        )
        return EchoLanguageProfile(
            mode="private_common",
            available=available,
            members=language_members if available else (),
            unavailable_reason=(
                "" if available else ECHO_PRIVATE_INSUFFICIENT_REASON
            ),
            shared_words=shared_words if available else (),
            side_preference_words=side_words if available else (),
        )

    return EchoLanguageProfile(
        mode="unavailable",
        available=False,
        unavailable_reason=ECHO_UNKNOWN_CONVERSATION_REASON,
    )


def _private_voice_heading(
    member: EchoMemberCard,
    *,
    viewer_speaker_key: str | None,
) -> str:
    if viewer_speaker_key is None:
        return f"{member.display_name} 常说"
    if member.is_viewer:
        return "你常说"
    return "TA 常说"


def _echo_expression_habits(
    profile: object | None,
) -> EchoExpressionHabits | None:
    """Map a core UserProfile to display-ready expression habits."""
    if profile is None or getattr(profile, "consecutive_runs", None) is None:
        return None
    runs = profile.consecutive_runs
    return EchoExpressionHabits(
        median_length=profile.median_length,
        average_length=profile.average_length,
        max_length=profile.max_length,
        run_count=runs.run_count,
        average_run_length=runs.average_run_length,
        median_run_length=runs.median_run_length,
        single_message_run_count=runs.single_message_run_count,
        multi_message_run_count=runs.multi_message_run_count,
    )


def _private_shared_word_layers(
    report: object | None,
    *,
    viewer_key: str | None,
    member_keys: set[str],
) -> tuple[tuple[EchoSharedWord, ...], tuple[EchoSharedWord, ...]]:
    """Split core private shared words into 同频 and 谁更常这样说 lists."""
    if report is None or viewer_key is None:
        return (), ()

    shared_items = [
        item
        for item in report.shared_words
        if item.speaker_a in member_keys and item.speaker_b in member_keys
    ]
    shared_words = tuple(
        _to_echo_shared_word(item, viewer_key, emphasis="shared")
        for item in shared_items[:ECHO_PRIVATE_SHARED_TOP_LIMIT]
    )

    side_items = [
        item
        for item in shared_items
        if item.preferred_speaker_key is not None
        and item.occurrence_support >= ECHO_PRIVATE_SIDE_MIN_OCCURRENCE
    ]
    side_items.sort(
        key=lambda item: (
            -abs(item.rate_a - item.rate_b),
            -item.common_strength,
            item.word,
        )
    )
    side_words = tuple(
        _to_echo_shared_word(item, viewer_key)
        for item in side_items[:ECHO_PRIVATE_SIDE_TOP_LIMIT]
    )
    return shared_words, side_words


def _to_echo_shared_word(
    item: object,
    viewer_key: str,
    *,
    emphasis: str | None = None,
) -> EchoSharedWord:
    if viewer_key == item.speaker_a:
        self_count, peer_count = item.count_a, item.count_b
    else:
        self_count, peer_count = item.count_b, item.count_a
    if emphasis is None:
        if item.preferred_speaker_key == viewer_key:
            emphasis = "self"
        elif item.preferred_speaker_key is not None:
            emphasis = "peer"
        else:
            emphasis = "shared"
    return EchoSharedWord(
        word=item.word,
        self_count=self_count,
        peer_count=peer_count,
        emphasis=emphasis,
    )


def _build_echo_sessions(
    report: ConversationSessionReport | None,
    *,
    members: tuple[EchoMemberCard, ...] = (),
) -> EchoConversationSessions | None:
    if report is None:
        return None
    private = report.private_stats
    group = report.group_stats
    top_member = (
        next(
            (
                member
                for member in members
                if group is not None
                and member.speaker_key == group.top_initiator_sender_key
            ),
            None,
        )
        if group is not None
        else None
    )
    return EchoConversationSessions(
        threshold_seconds=report.threshold_seconds,
        session_count=report.session_count,
        average_duration_seconds=report.average_duration_seconds,
        median_duration_seconds=report.median_duration_seconds,
        longest_duration_seconds=report.longest_duration_seconds,
        average_message_count=report.average_message_count,
        items=tuple(
            EchoConversationSession(
                start_timestamp=session.start_timestamp,
                end_timestamp=session.end_timestamp,
                duration_seconds=session.duration_seconds,
                message_count=session.message_count,
                participant_count=session.participant_count,
                initiator=session.initiator,
                initiator_sender_key=session.initiator_sender_key,
                self_message_count=session.self_message_count,
                peer_message_count=session.peer_message_count,
            )
            for session in report.sessions
        ),
        private_self_count=(private.self_initiated_count if private else None),
        private_peer_count=(private.peer_initiated_count if private else None),
        private_unknown_count=(
            private.unknown_initiated_count if private else None
        ),
        private_self_to_peer_ratio=(
            private.self_to_peer_ratio if private else None
        ),
        private_self_share=(private.self_initiated_share if private else None),
        private_peer_share=(private.peer_initiated_share if private else None),
        private_unknown_share=(
            private.unknown_initiated_share if private else None
        ),
        private_self_peak_start_hour=report.private_self_peak_start_hour,
        private_peer_peak_start_hour=report.private_peer_peak_start_hour,
        private_reply_median_self_to_peer_seconds=(
            report.private_reply_timing.self_to_peer_median_seconds
            if report.private_reply_timing is not None
            else None
        ),
        private_reply_median_peer_to_self_seconds=(
            report.private_reply_timing.peer_to_self_median_seconds
            if report.private_reply_timing is not None
            else None
        ),
        group_self_count=(group.self_initiated_count if group else None),
        group_self_share=(group.self_initiated_share if group else None),
        group_top_initiator_name=(
            top_member.display_name if top_member is not None else None
        ),
        group_top_initiator_count=(
            group.top_initiated_count
            if group is not None and top_member is not None
            else None
        ),
        group_top_initiator_share=(
            group.top_initiated_share
            if group is not None and top_member is not None
            else None
        ),
        viewer_identity_reliable=(
            group is not None and group.self_initiated_count is not None
        ),
        start_hour_distribution=tuple(
            ChartPoint(
                label=f"{h.hour:02d}:00-{h.hour:02d}:59",
                value=float(h.count),
            )
            for h in report.start_hour_counts
        ),
        peak_start_hour=report.peak_start_hour,
        session_character=_session_character_label(report.session_character),
        loudest_most_messages=(
            _session_to_echo(report.sessions[report.loudest_most_messages])
            if report.loudest_most_messages is not None
            else None
        ),
        loudest_longest_duration=(
            _session_to_echo(report.sessions[report.loudest_longest_duration])
            if report.loudest_longest_duration is not None
            else None
        ),
        loudest_most_participants=(
            _session_to_echo(report.sessions[report.loudest_most_participants])
            if report.loudest_most_participants is not None
            else None
        ),
        loudest_densest=(
            _session_to_echo(report.sessions[report.loudest_densest])
            if report.loudest_densest is not None
            else None
        ),
        loudest_most_back_and_forth=(
            _session_to_echo(report.sessions[report.loudest_most_back_and_forth])
            if report.loudest_most_back_and_forth is not None
            else None
        ),
    )



def _build_echo_expression_culture(
    report: ExpressionReport | None,
    *,
    members: tuple[EchoMemberCard, ...] = (),
) -> EchoExpressionCulture | None:
    """Map the core expression report into the Echo expression chapter."""
    if report is None or report.expression_message_count <= 0:
        return None
    member_by_key = {member.speaker_key: member for member in members}
    culture_members = tuple(
        EchoMemberExpression(
            speaker_key=member.speaker_key,
            display_name=(
                member_by_key[member.speaker_key].display_name
                if member.speaker_key in member_by_key
                else member.speaker_key
            ),
            expression_occurrence_count=member.expression_occurrence_count,
            expression_message_count=member.expression_message_count,
            expression_share_percent=member.expression_share_percent,
            expression_only_message_count=member.expression_only_message_count,
            top_expressions=tuple(
                _to_echo_expression_item(item)
                for item in _display_expression_items(
                    member.top_expressions,
                    ECHO_EXPRESSION_MEMBER_TOP_LIMIT,
                )
            ),
        )
        for member in report.members
    )
    return EchoExpressionCulture(
        available=bool(culture_members),
        expression_message_count=report.expression_message_count,
        expression_only_message_count=report.expression_only_message_count,
        expression_only_rate=report.expression_only_rate,
        unique_expression_count=report.unique_expression_count,
        top_expressions=tuple(
            _to_echo_expression_item(item)
            for item in _display_expression_items(
                report.top_expressions,
                ECHO_EXPRESSION_TOP_LIMIT,
            )
        ),
        top_combinations=tuple(
            _to_echo_expression_combination(item, member_by_key)
            for item in report.top_combinations
            if item.count >= ECHO_EXPRESSION_COMBINATION_MIN_COUNT
            and all(
                resolve_wechat_asset_key(member.expression_key)
                for member in item.expressions
            )
        )[:ECHO_EXPRESSION_COMBINATION_TOP_LIMIT],
        members=culture_members,
        unavailable_reason=(
            "" if culture_members else "暂无可展示的表达文化。"
        ),
    )


def _display_expression_items(
    items,
    limit: int,
):
    """Keep presentation limited to recurring non-sticker expressions."""
    return [
        item
        for item in items
        if item.count >= ECHO_EXPRESSION_MIN_COUNT
        and item.kind != "sticker"
    ][:limit]


def _to_echo_expression_item(item: ExpressionUsage) -> EchoExpressionItem:
    asset_key = resolve_wechat_asset_key(item.expression_key)
    display_text = item.display_text or ""
    if asset_key:
        display_text = item.expression_key
    if (
        item.kind == "sticker"
        and not asset_key
        and (display_text in {"[贴图]", "[QQ贴图]"} or not display_text)
    ):
        display_text = "微信自定义表情"
    if not asset_key and display_text.startswith("["):
        display_text = "表情"
    return EchoExpressionItem(
        expression_key=item.expression_key,
        display_text=display_text,
        count=item.count,
        kind=item.kind,
        with_text_message_count=item.with_text_message_count,
        text_only_message_count=item.text_only_message_count,
        asset_key=asset_key,
        nearby_words=tuple(word.word for word in item.nearby_words[:5]),
    )


def _to_echo_expression_combination(
    item: ExpressionCombinationUsage,
    member_by_key: dict[str, EchoMemberCard],
) -> EchoExpressionCombination:
    total = item.count
    common_members = []
    for member_count in item.member_counts:
        member = member_by_key.get(member_count.speaker_key)
        if member is None:
            continue
        share_percent = (
            round(member_count.count * 100.0 / total, 1)
            if total > 0
            else 0.0
        )
        if share_percent < ECHO_EXPRESSION_COMBINATION_MEMBER_SHARE_MIN:
            continue
        common_members.append(
            EchoExpressionCombinationMember(
                display_name=member.display_name,
                count=member_count.count,
                share_percent=share_percent,
            )
        )
        if len(common_members) >= ECHO_EXPRESSION_COMBINATION_MEMBER_LIMIT:
            break
    return EchoExpressionCombination(
        asset_keys=tuple(
            resolve_wechat_asset_key(member.expression_key)
            for member in item.expressions
        ),
        count=item.count,
        common_members=tuple(common_members),
    )


def _session_to_echo(session: ConversationSession) -> EchoConversationSession:
    """Convert a core ConversationSession to an EchoConversationSession."""
    return EchoConversationSession(
        start_timestamp=session.start_timestamp,
        end_timestamp=session.end_timestamp,
        duration_seconds=session.duration_seconds,
        message_count=session.message_count,
        participant_count=session.participant_count,
        initiator=session.initiator,
        initiator_sender_key=session.initiator_sender_key,
        self_message_count=session.self_message_count,
        peer_message_count=session.peer_message_count,
    )


_SESSION_CHARACTER_LABELS: dict[str, str] = {
    "quick_and_brief": "来得快，也散得快",
    "long_running": "一旦聊开，就会聊很久",
    "mixed": "有长有短，节奏不一",
}


def _session_character_label(key: str | None) -> str | None:
    """Map a core session character key to its Chinese label."""
    if key is None:
        return None
    return _SESSION_CHARACTER_LABELS.get(key, key)


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
