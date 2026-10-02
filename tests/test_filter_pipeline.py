"""Tests for applying filtering decisions to parsed messages."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.candidates import Candidate
from qq_chat_analyzer.decision_engine import create_filter_decisions
from qq_chat_analyzer.filter_decisions import FilterDecision
from qq_chat_analyzer.filter_pipeline import FilterPipeline
from qq_chat_analyzer import filter_pipeline
from qq_chat_analyzer.parser import ParsedMessage


def test_sender_ignore_filters_matching_sender_messages() -> None:
    ignored_message = _message("虚构签到助手", "签到成功", 1)
    kept_message = _message("虚构普通用户", "今天讨论测试方案", 2)
    decision = _decision(
        target="虚构签到助手",
        target_type="sender",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [ignored_message, kept_message],
        [decision],
    )

    assert result.kept_messages == [kept_message]
    assert result.filtered_messages == [ignored_message]
    assert result.applied_decisions == [decision]


def test_template_ignore_filters_matching_template_messages() -> None:
    ignored_message = _message(
        "虚构欢迎助手",
        "欢迎   虚构新成员   加入群聊！",
        1,
    )
    kept_message = _message("虚构普通用户", "欢迎大家讨论新主题", 2)
    decision = _decision(
        target="欢迎 {variable} 加入群聊",
        target_type="template",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [ignored_message, kept_message],
        [decision],
    )

    assert result.kept_messages == [kept_message]
    assert result.filtered_messages == [ignored_message]
    assert result.applied_decisions == [decision]


def test_number_fingerprint_ignore_filters_matching_message() -> None:
    ignored_message = _message(
        "虚构运势助手",
        "综合指数:42.5 财运指数:68",
        1,
    )
    decision = _decision(
        target="综合指数:{number} 财运指数:{number}",
        target_type="template",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [ignored_message],
        [decision],
    )

    assert result.filtered_messages == [ignored_message]
    assert result.applied_decisions == [decision]


def test_id_fingerprint_ignore_filters_matching_message() -> None:
    ignored_message = _message(
        "虚构查询助手",
        "查询编号123456",
        1,
    )
    decision = _decision(
        target="查询编号{id}",
        target_type="template",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [ignored_message],
        [decision],
    )

    assert result.filtered_messages == [ignored_message]
    assert result.applied_decisions == [decision]


def test_user_fingerprint_ignore_filters_matching_message() -> None:
    ignored_message = _message(
        "虚构运势助手",
        "@虚构用户 今日运势:99",
        1,
    )
    decision = _decision(
        target="@{user} 今日运势:{number}",
        target_type="template",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [ignored_message],
        [decision],
    )

    assert result.filtered_messages == [ignored_message]
    assert result.applied_decisions == [decision]


def test_url_fingerprint_ignore_filters_matching_message() -> None:
    ignored_message = _message(
        "虚构查询助手",
        "详情:https://example.test/a/42，版本:3",
        1,
    )
    decision = _decision(
        target="详情:{url}，版本:{number}",
        target_type="template",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [ignored_message],
        [decision],
    )

    assert result.filtered_messages == [ignored_message]
    assert result.applied_decisions == [decision]


def test_fingerprint_ignore_keeps_different_static_structure() -> None:
    kept_message = _message(
        "虚构普通用户",
        "综合指数:42 事业指数:68",
        1,
    )
    decision = _decision(
        target="综合指数:{number} 财运指数:{number}",
        target_type="template",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [kept_message],
        [decision],
    )

    assert result.kept_messages == [kept_message]
    assert result.filtered_messages == []
    assert result.applied_decisions == []


def test_number_fingerprint_does_not_match_long_integer_id() -> None:
    kept_message = _message(
        "虚构查询助手",
        "综合指数:123456",
        1,
    )
    decision = _decision(
        target="综合指数:{number}",
        target_type="template",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [kept_message],
        [decision],
    )

    assert result.kept_messages == [kept_message]
    assert result.filtered_messages == []
    assert result.applied_decisions == []


def test_keep_decision_does_not_filter_messages() -> None:
    message = _message("虚构助手", "保留这条虚构消息", 1)
    decision = _decision(
        target="虚构助手",
        target_type="sender",
        action="keep",
    )

    result = FilterPipeline().apply_filter_decisions(
        [message],
        [decision],
    )

    assert result.kept_messages == [message]
    assert result.filtered_messages == []
    assert result.applied_decisions == []


def test_review_decision_does_not_filter_messages() -> None:
    message = _message("虚构待复核用户", "这是一条虚构消息", 1)
    decision = _decision(
        target="虚构待复核用户",
        target_type="sender",
        action="review",
    )

    result = FilterPipeline().apply_filter_decisions(
        [message],
        [decision],
    )

    assert result.kept_messages == [message]
    assert result.filtered_messages == []
    assert result.applied_decisions == []


def test_no_decisions_keeps_every_message_in_original_order() -> None:
    first = _message("虚构用户甲", "第一条虚构消息", 1)
    second = _message("虚构用户乙", "第二条虚构消息", 2)

    result = FilterPipeline().apply_filter_decisions(
        [first, second],
        [],
    )

    assert result.kept_messages == [first, second]
    assert result.filtered_messages == []
    assert result.applied_decisions == []


def test_filtering_result_tracks_each_matching_ignore_decision_once() -> None:
    first = _message("虚构机器人甲", "固定播报", 1)
    second = _message("虚构机器人甲", "固定播报", 2)
    sender_decision = _decision(
        target="虚构机器人甲",
        target_type="sender",
        action="ignore",
    )
    unmatched_decision = _decision(
        target="虚构机器人乙",
        target_type="sender",
        action="ignore",
    )

    result = FilterPipeline().apply_filter_decisions(
        [first, second],
        [sender_decision, unmatched_decision],
    )

    assert result.kept_messages == []
    assert result.filtered_messages == [first, second]
    assert result.applied_decisions == [sender_decision]


def test_automation_source_sender_ignore_reuses_sender_filtering() -> None:
    ignored_message = _message(
        "虚构交互助手",
        "这是一条虚构自动响应",
        1,
    )
    kept_message = _message(
        "虚构普通用户",
        "这是一条虚构普通消息",
        2,
    )
    decisions = create_filter_decisions(
        [
                Candidate(
                    target="虚构交互助手",
                    candidate_type="automation_source",
                    score=0.95,
                    metadata={
                        "source_kind": "interactive_bot",
                        "metrics": {
                            "mention_count": 100,
                            "response_rate": 0.95,
                            "unique_trigger_source_count": 20,
                            "concentrated_in_short_window": False,
                        },
                    },
                )
            ]
        )

    result = FilterPipeline().apply_filter_decisions(
        [ignored_message, kept_message],
        decisions,
    )

    assert result.kept_messages == [kept_message]
    assert result.filtered_messages == [ignored_message]
    assert result.applied_decisions == decisions


def _message(sender: str, text: str, timestamp: int) -> ParsedMessage:
    return ParsedMessage(
        timestamp=timestamp,
        sender=sender,
        message_type="text",
        text=text,
    )


def _decision(
    target: str,
    target_type: str,
    action: str,
) -> FilterDecision:
    return FilterDecision(
        target=target,
        target_type=target_type,
        action=action,
        confidence=1.0,
        reason="synthetic_test_decision",
        source="user",
    )


def _legacy_apply(messages, decisions):
    """The original exhaustive scan, retained as an equivalence oracle."""
    decisions = list(decisions)
    kept, filtered = [], []
    applied = [False] * len(decisions)
    for message in messages:
        should_filter = False
        for index, decision in enumerate(decisions):
            if decision.action != "ignore":
                continue
            if filter_pipeline._decision_matches_message(decision, message):
                should_filter = True
                applied[index] = True
        (filtered if should_filter else kept).append(message)
    return kept, filtered, [d for d, matched in zip(decisions, applied) if matched]


def test_mixed_decisions_preserve_every_match_and_metadata() -> None:
    messages = [
        _message("bot_a", "Welcome  Alice!", 1),
        _message("bot_b", "Ticket 123456", 2),
        _message("person", "Welcome Bob", 3),
        _message("person", "ordinary", 4),
    ]
    sender_a = FilterDecision("bot_a", "sender", "ignore", 0.91, "robot_a", "auto", {"category": "robot"})
    sender_b = FilterDecision("bot_b", "sender", "ignore", 0.92, "robot_b", "auto", {"category": "robot"})
    template_welcome = FilterDecision("Welcome {user}", "template", "ignore", 0.93, "welcome", "auto", {"category": "template"})
    template_ticket = FilterDecision("Ticket {id}", "template", "ignore", 0.94, "ticket", "auto", {"category": "template"})
    duplicate_sender = FilterDecision("bot_a", "sender", "ignore", 0.95, "other_reason", "user", {"category": "manual"})
    inert = [
        FilterDecision("person", "sender", "keep", 1.0, "manual_keep", "user"),
        FilterDecision("ordinary", "template", "review", 0.5, "review", "auto"),
        FilterDecision("ordinary", "stopword", "ignore", 1.0, "unknown_type", "auto"),
    ]
    decisions = [template_ticket, sender_a, *inert, template_welcome, sender_b, duplicate_sender]
    expected = _legacy_apply(messages, decisions)
    result = FilterPipeline().apply_filter_decisions(iter(messages), iter(decisions))
    assert (result.kept_messages, result.filtered_messages, result.applied_decisions) == expected
    assert result.applied_decisions == [template_ticket, sender_a, template_welcome, sender_b, duplicate_sender]
    assert result.applied_decisions[1] is sender_a
    assert result.applied_decisions[-1] is duplicate_sender


def test_decision_order_changes_applied_order_but_not_partition() -> None:
    message = _message("bot", "Welcome Alice", 1)
    sender = FilterDecision("bot", "sender", "ignore", 0.8, "sender", "auto")
    template = FilterDecision("Welcome {user}", "template", "ignore", 0.9, "template", "auto")
    first = FilterPipeline().apply_filter_decisions([message], [sender, template])
    second = FilterPipeline().apply_filter_decisions([message], [template, sender])
    assert first.filtered_messages == second.filtered_messages == [message]
    assert first.applied_decisions == [sender, template]
    assert second.applied_decisions == [template, sender]


def test_empty_messages_match_legacy_result() -> None:
    decision = _decision("bot", "sender", "ignore")
    result = FilterPipeline().apply_filter_decisions([], [decision])
    assert (result.kept_messages, result.filtered_messages, result.applied_decisions) == _legacy_apply([], [decision])


def test_template_preparation_happens_once_per_ignore_decision(monkeypatch) -> None:
    pattern_calls = []
    compile_calls = []
    original_pattern = filter_pipeline._template_pattern
    original_compile = filter_pipeline.re.compile

    def track_pattern(template):
        pattern_calls.append(template)
        return original_pattern(template)

    def track_compile(pattern, *args, **kwargs):
        compile_calls.append(pattern)
        return original_compile(pattern, *args, **kwargs)

    monkeypatch.setattr(filter_pipeline, "_template_pattern", track_pattern)
    monkeypatch.setattr(filter_pipeline.re, "compile", track_compile)
    decisions = [
        _decision("Welcome {user}", "template", "ignore"),
        _decision("Ticket {id}", "template", "ignore"),
        _decision("Unused {number}", "template", "keep"),
    ]
    messages = [_message("person", f"Welcome User{i}", i) for i in range(20)]
    FilterPipeline().apply_filter_decisions(messages, decisions)
    assert len(pattern_calls) == 2
    assert len(compile_calls) == 2
