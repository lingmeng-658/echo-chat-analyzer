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
