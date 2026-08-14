"""RED/GREEN suite for Release Slice 1A identity semantics.

Every fixture below is fictional. No real QQ/WeChat account data appears here.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.legacy_projection import project_legacy_message
from qq_chat_analyzer.message import ChatMessage
from qq_chat_analyzer.rich_message import RichMessage, SenderIdentity, TextContent


def _message(
    sender: str,
    *,
    sender_id: str | None = None,
    conversation_id: str | None = None,
    conversation_type: str = "unknown",
    is_self: bool | None = None,
    text: str = "hello",
) -> ChatMessage:
    return ChatMessage(
        timestamp=1,
        sender=sender,
        message_type="text",
        text=text,
        sender_id=sender_id,
        conversation_id=conversation_id,
        conversation_type=conversation_type,
        is_self=is_self,
    )


def _user_profile_analyzer():
    return importlib.import_module(
        "qq_chat_analyzer.analysis.analyzers.user_profile_analyzer"
    ).UserProfileAnalyzer()


def _conversation_analyzer():
    return importlib.import_module(
        "qq_chat_analyzer.analysis.analyzers.conversation_analyzer"
    ).ConversationAnalyzer()


def _qce_row(
    message_id: str,
    uid: str,
    nickname: str,
) -> dict[str, object]:
    return {
        "id": message_id,
        "timestamp": 1750000000000,
        "sender": {"uid": uid, "uin": uid, "nickname": nickname},
        "type": "text",
        "content": {"text": "fictional message", "elements": [], "mentions": []},
        "recalled": False,
        "system": False,
    }


def _write_qce(path: Path, chat_info: dict[str, object], rows: list[object]) -> None:
    path.write_text(
        json.dumps({"chatInfo": chat_info, "messages": rows}, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_wechat_db(
    path: Path,
    username: str,
    rows: list[object],
    *,
    self_username: str | None = None,
) -> None:
    conversation: dict[str, object] = {"username": username}
    if self_username is not None:
        conversation["self_username"] = self_username
    path.write_text(
        json.dumps(
            {"source": "wechat-db", "conversation": conversation, "messages": rows},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _db_row(username: str, content: str = "fictional db text") -> dict[str, object]:
    return {
        "local_id": 1,
        "server_id": 900001,
        "local_type": 1,
        "create_time": 1753412807,
        "message_content": content,
        "user_name": username,
    }


def _write_detailed_wechat(
    path: Path,
    *,
    session_id: str,
    is_group: bool,
    messages: list[dict[str, object]],
) -> None:
    path.write_text(
        json.dumps(
            {
                "exportInfo": {"format": "detailed-json"},
                "session": {
                    "wxid": session_id,
                    "platform": "wechat",
                    "isGroup": is_group,
                },
                "messages": messages,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _detailed_message(
    username: str,
    display_name: str,
    *,
    is_send: int,
) -> dict[str, object]:
    return {
        "localId": 1,
        "platformMessageId": "fictional-message-001",
        "createTime": 1783223281,
        "type": "文本消息",
        "localType": 1,
        "content": "fictional detailed text",
        "isSend": is_send,
        "senderUsername": username,
        "senderDisplayName": display_name,
    }


def _write_chatlab(
    path: Path,
    *,
    group_id: str,
    conversation_type: str,
    messages: list[dict[str, object]],
) -> None:
    lines = [
        {
            "_type": "header",
            "meta": {
                "name": "Fictional Group",
                "platform": "wechat",
                "type": conversation_type,
                "groupId": group_id,
            },
        }
    ]
    lines.extend(messages)
    path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )


def _chatlab_message(username: str, *, is_send: int) -> dict[str, object]:
    return {
        "_type": "message",
        "sender": username,
        "accountName": "Fictional Sender",
        "timestamp": 1753412807,
        "type": 0,
        "content": "fictional chatlab text",
        "platformMessageId": "fictional-chatlab-001",
        "isSend": is_send,
    }


def _import_outcome(input_path: Path, platform: str):
    application = importlib.import_module("qq_chat_analyzer.application")
    return application.ImportService().execute(
        application.ImportRequest(input_path=input_path, platform=platform)
    )


def _request_dto(tmp_path: Path, input_path: Path):
    dto = importlib.import_module("qq_chat_analyzer.application.dto")
    return dto.AnalysisRequestDTO(
        input_path=input_path,
        output_directory=tmp_path / "private-output",
        stopwords_path=tmp_path / "private-stopwords.txt",
        font_path=None,
        top=5,
        conversation_kind="private",
        viewer_speaker_key="wxid_fictional_me",
    )


# ------------------------------------------------------------------ model


def test_chat_message_backward_compatible_defaults() -> None:
    message = ChatMessage(
        timestamp=1,
        sender="Fictional Alice",
        message_type="text",
        text="hello",
    )

    assert message.conversation_type == "unknown"
    assert message.is_self is None


def test_legacy_projection_preserves_identity_semantics() -> None:
    rich_message = RichMessage(
        message_id="fictional-message-001",
        source="qq",
        conversation_id="fictional-room",
        sender=SenderIdentity(
            identity_id="u-fictional-1",
            display_name="Fictional Alice",
        ),
        timestamp=1,
        message_type="text",
        contents=(TextContent(text="hello"),),
        conversation_type="group",
        is_self=True,
    )

    message = project_legacy_message(rich_message)

    assert message.conversation_type == "group"
    assert message.is_self is True


# ------------------------------------------------------ stable aggregation


def test_user_profiles_merge_same_stable_id_across_renames() -> None:
    messages = [
        _message("Fictional Alice", sender_id="u-fictional-1", text="hello"),
        _message("Fictional Alice Renamed", sender_id="u-fictional-1", text="world"),
    ]

    report = _user_profile_analyzer().analyze(messages)

    assert len(report.profiles) == 1
    profile = report.profiles[0]
    assert profile.speaker_key == "u-fictional-1"
    assert profile.message_count == 2


def test_user_profiles_keep_same_display_name_with_distinct_ids() -> None:
    messages = [
        _message("Fictional Alice", sender_id="u-fictional-1"),
        _message("Fictional Alice", sender_id="u-fictional-2"),
    ]

    report = _user_profile_analyzer().analyze(messages)

    assert len(report.profiles) == 2
    assert {profile.speaker_key for profile in report.profiles} == {
        "u-fictional-1",
        "u-fictional-2",
    }


def test_conversation_analyzer_counts_stable_participants() -> None:
    messages = [
        _message("Fictional Alice", sender_id="u-1", conversation_id="room-1"),
        _message("Fictional Alice Renamed", sender_id="u-1", conversation_id="room-1"),
        _message("Fictional Alice Renamed", sender_id="u-2", conversation_id="room-1"),
        _message("Fictional Alice", sender_id="u-3", conversation_id="room-1"),
    ]

    summary = _conversation_analyzer().analyze(messages).conversations[0]

    assert summary.speaker_count == 3


def test_word_speaker_tokens_use_stable_sender_key(tmp_path: Path) -> None:
    analysis_service = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    stopwords_path = tmp_path / "empty-stopwords.txt"
    stopwords_path.write_text("", encoding="utf-8")
    messages = [
        _message("Fictional Alice", sender_id="u-1", text="hello"),
        _message("Fictional Alice Renamed", sender_id="u-1", text="world"),
    ]

    analyzed = analysis_service._analyze_kept_messages(messages, stopwords_path)

    assert {sender for sender, _tokens in analyzed.sender_tokens} == {"u-1"}


# -------------------------------------------------------------- QQ wiring


def test_qq_private_export_sets_conversation_type(tmp_path: Path) -> None:
    export_path = tmp_path / "qq-private.json"
    _write_qce(
        export_path,
        {"chatType": 1, "peerUid": "u-fictional-peer"},
        [_qce_row("m1", "u-fictional-self", "Fictional Self")],
    )

    outcome = _import_outcome(export_path, "qq")

    assert outcome.messages[0].conversation_type == "private"


def test_qq_group_export_sets_conversation_type(tmp_path: Path) -> None:
    export_path = tmp_path / "qq-group.json"
    _write_qce(
        export_path,
        {"type": "group", "groupCode": "fictional-group"},
        [_qce_row("m1", "u-fictional-member", "Fictional Member")],
    )

    outcome = _import_outcome(export_path, "qq")

    assert outcome.messages[0].conversation_type == "group"


def test_qq_missing_conversation_type_stays_unknown(tmp_path: Path) -> None:
    export_path = tmp_path / "qq-unknown.json"
    _write_qce(export_path, {}, [_qce_row("m1", "u-fictional-1", "Fictional 1")])

    outcome = _import_outcome(export_path, "qq")

    assert outcome.messages[0].conversation_type == "unknown"


def test_qq_self_identity_only_when_reliable_identity_supplied() -> None:
    qq_adapter = importlib.import_module("qq_chat_analyzer.qq_chat_exporter_adapter")
    rows = [
        _qce_row("m1", "u-fictional-self", "Fictional Self"),
        _qce_row("m2", "u-fictional-peer", "Fictional Peer"),
    ]

    known_messages, _warnings = qq_adapter.parse_qce_messages(
        rows,
        self_identity="u-fictional-self",
    )
    unknown_messages, _warnings = qq_adapter.parse_qce_messages(rows)

    assert [message.is_self for message in known_messages] == [True, False]
    assert [message.is_self for message in unknown_messages] == [None, None]


def test_qq_export_self_uid_flows_through_import(tmp_path: Path) -> None:
    export_path = tmp_path / "qq-self-uid.json"
    _write_qce(
        export_path,
        {
            "chatType": 2,
            "groupCode": "fictional-group",
            "selfUid": "u-fictional-self",
            "selfUin": "fictional-self-uin",
        },
        [
            _qce_row("m1", "u-fictional-self", "Fictional Self"),
            _qce_row("m2", "u-fictional-peer", "Fictional Peer"),
        ],
    )

    outcome = _import_outcome(export_path, "qq")

    assert [message.is_self for message in outcome.messages] == [True, False]


def test_qq_export_self_uin_fallback_flows_through_import(
    tmp_path: Path,
) -> None:
    export_path = tmp_path / "qq-self-uin.json"
    _write_qce(
        export_path,
        {
            "chatType": 1,
            "peerUid": "u-fictional-peer",
            "selfUin": "100000001",
        },
        [
            _qce_row("m1", "u-fictional-self", "Fictional Self"),
            _qce_row("m2", "u-fictional-peer", "Fictional Peer"),
        ],
    )
    rows = json.loads(export_path.read_text(encoding="utf-8"))["messages"]
    rows[0]["sender"]["uin"] = "100000001"
    rows[1]["sender"]["uin"] = "100000002"
    export_path.write_text(
        json.dumps(
            {"chatInfo": json.loads(export_path.read_text(encoding="utf-8"))["chatInfo"], "messages": rows},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    outcome = _import_outcome(export_path, "qq")

    assert [message.is_self for message in outcome.messages] == [True, False]


def test_qq_export_matches_all_reliable_self_identity_aliases(
    tmp_path: Path,
) -> None:
    export_path = tmp_path / "qq-self-aliases.json"
    self_row = _qce_row("m1", "u-fictional-current", "Fictional Self")
    self_row["sender"]["uin"] = "100000001"
    peer_row = _qce_row("m2", "u-fictional-peer", "Fictional Peer")
    peer_row["sender"]["uin"] = "100000002"
    _write_qce(
        export_path,
        {
            "type": "private",
            "selfUid": "u-fictional-stale",
            "selfUin": "100000001",
        },
        [self_row, peer_row],
    )

    outcome = _import_outcome(export_path, "qq")

    assert [message.is_self for message in outcome.messages] == [True, False]


# ----------------------------------------------------------- WeChat wiring


def test_wechat_db_private_and_group_conversation_types(
    tmp_path: Path,
) -> None:
    private_path = tmp_path / "wechat-private.json"
    _write_wechat_db(
        private_path,
        "wxid_fictional_friend",
        [_db_row("wxid_fictional_friend")],
    )
    group_path = tmp_path / "wechat-group.json"
    _write_wechat_db(
        group_path,
        "fictional-room@chatroom",
        [_db_row("wxid_fictional_member")],
    )

    private_outcome = _import_outcome(private_path, "wechat")
    group_outcome = _import_outcome(group_path, "wechat")

    assert private_outcome.messages[0].conversation_type == "private"
    assert group_outcome.messages[0].conversation_type == "group"


def test_wechat_db_self_identity_uses_conversation_self_username(
    tmp_path: Path,
) -> None:
    known_path = tmp_path / "wechat-known-self.json"
    _write_wechat_db(
        known_path,
        "wxid_fictional_friend",
        [
            _db_row("wxid_fictional_me", content="mine"),
            _db_row("wxid_fictional_peer", content="theirs"),
        ],
        self_username="wxid_fictional_me",
    )
    unknown_path = tmp_path / "wechat-unknown-self.json"
    _write_wechat_db(
        unknown_path,
        "wxid_fictional_friend",
        [_db_row("wxid_fictional_sender")],
    )

    known_outcome = _import_outcome(known_path, "wechat")
    unknown_outcome = _import_outcome(unknown_path, "wechat")

    assert [message.is_self for message in known_outcome.messages] == [True, False]
    assert unknown_outcome.messages[0].is_self is None


def test_wechat_cli_direction_maps_self_and_keeps_conversation_id() -> None:
    cli_adapter = importlib.import_module("qq_chat_analyzer.wechat_cli_adapter")
    rows = [
        {
            "localId": 1,
            "serverId": 900001,
            "createTime": 1753412807,
            "sortSeq": 1,
            "direction": "out",
            "senderUsername": "wxid_fictional_me",
            "type": 1,
            "content": "mine",
        },
        {
            "localId": 2,
            "serverId": 900002,
            "createTime": 1753412810,
            "sortSeq": 2,
            "direction": "in",
            "senderUsername": "wxid_fictional_peer",
            "type": 1,
            "content": "theirs",
        },
        {
            "localId": 3,
            "serverId": 900003,
            "createTime": 1753412820,
            "sortSeq": 3,
            "direction": "unknown",
            "senderUsername": "wxid_fictional_other",
            "type": 1,
            "content": "unknown",
        },
    ]

    messages = cli_adapter.parse_messages(
        rows,
        conversation_id="fictional-cli-session",
    )

    assert [message.is_self for message in messages] == [True, False, None]
    assert [message.conversation_id for message in messages] == [
        "fictional-cli-session",
    ] * 3


def test_wechat_detailed_json_session_context_and_is_send(tmp_path: Path) -> None:
    export_path = tmp_path / "wechat-detailed.json"
    _write_detailed_wechat(
        export_path,
        session_id="fictional-chatroom",
        is_group=True,
        messages=[
            _detailed_message("wxid_fictional_me", "Fictional Me", is_send=1),
            _detailed_message("wxid_fictional_peer", "Fictional Peer", is_send=0),
        ],
    )

    outcome = _import_outcome(export_path, "wechat")

    assert [message.conversation_id for message in outcome.messages] == [
        "fictional-chatroom",
    ] * 2
    assert [message.conversation_type for message in outcome.messages] == [
        "group",
        "group",
    ]
    assert [message.is_self for message in outcome.messages] == [True, False]


def test_wechat_chatlab_header_context_and_is_send(tmp_path: Path) -> None:
    export_path = tmp_path / "chatlab.jsonl"
    _write_chatlab(
        export_path,
        group_id="fictional-chatroom",
        conversation_type="group",
        messages=[
            _chatlab_message("wxid_fictional_me", is_send=1),
            _chatlab_message("wxid_fictional_peer", is_send=0),
        ],
    )

    outcome = _import_outcome(export_path, "wechat")

    assert [message.conversation_id for message in outcome.messages] == [
        "fictional-chatroom",
    ] * 2
    assert [message.conversation_type for message in outcome.messages] == [
        "group",
        "group",
    ]
    assert [message.is_self for message in outcome.messages] == [True, False]


# ---------------------------------------------------------------- Echo


def test_analysis_request_dto_carries_echo_identity_options(tmp_path: Path) -> None:
    dto = importlib.import_module("qq_chat_analyzer.application.dto")
    request = dto.AnalysisRequestDTO(
        input_path=tmp_path / "input.json",
        output_directory=tmp_path / "private-output",
        stopwords_path=tmp_path / "private-stopwords.txt",
        conversation_kind="private",
        viewer_speaker_key="wxid_fictional_me",
    )

    assert request.conversation_kind == "private"
    assert request.viewer_speaker_key == "wxid_fictional_me"
    assert "wxid_fictional_me" not in repr(request)


def test_identity_diagnostics_log_is_anonymized(caplog) -> None:
    analysis_service = importlib.import_module(
        "qq_chat_analyzer.application.analysis_service"
    )
    messages = [
        ChatMessage(
            timestamp=1,
            sender="Fictional Alice",
            message_type="text",
            text="secret fictional body",
            platform="qq",
            sender_id="u-fictional-self",
            conversation_id="fictional-room",
            conversation_type="private",
            is_self=True,
        )
    ]

    with caplog.at_level(
        "INFO",
        logger="qq_chat_analyzer.desktop.identity",
    ):
        analysis_service._log_identity_diagnostics(messages)

    assert (
        "[identity] source=qq conversation_type=private "
        "self_identity=resolved sender_identity_coverage=resolved"
        in caplog.text
    )
    for secret in (
        "u-fictional-self",
        "fictional-room",
        "Fictional Alice",
        "secret fictional body",
    ):
        assert secret not in caplog.text


def test_echo_report_html_hides_raw_speaker_key(tmp_path: Path) -> None:
    presentation = importlib.import_module("qq_chat_analyzer.presentation")
    view = presentation.EchoReportView(
        title="Echo Report",
        has_data=True,
        members=(
            presentation.EchoMemberCard(
                speaker_key="internal-id-123",
                display_name="Fictional Alice",
                is_viewer=False,
                message_count=1,
                message_share_percent=100.0,
                average_length=3.0,
                max_length=3,
                active_period="",
            ),
        ),
    )
    html_path = tmp_path / "echo-report.html"
    json_path = tmp_path / "echo-report.json"

    presentation.export_echo_report_html(view, html_path)
    presentation.export_echo_report_json(view, json_path)

    html = html_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    match = re.search(
        r"window\.ECHO_DATA = (\{.*?\});",
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    assert "internal-id-123" in match.group(1)
    rendered_without_data = html.replace(match.group(0), "")
    assert "internal-id-123" not in rendered_without_data
    assert payload["members"][0]["speaker_key"] == "internal-id-123"


def test_analysis_service_echo_artifact_uses_kind_and_viewer(
    tmp_path: Path,
) -> None:
    application = importlib.import_module("qq_chat_analyzer.application")
    input_path = tmp_path / "wechat-detailed.json"
    _write_detailed_wechat(
        input_path,
        session_id="wxid_fictional_friend",
        is_group=False,
        messages=[
            _detailed_message("wxid_fictional_me", "Fictional Me", is_send=1),
            _detailed_message("wxid_fictional_peer", "Fictional Peer", is_send=0),
        ],
    )
    output_directory = tmp_path / "private-output"
    output_directory.mkdir()
    stopwords_path = tmp_path / "private-stopwords.txt"
    stopwords_path.write_text("", encoding="utf-8")
    request = application.AnalysisRequestDTO(
        input_path=input_path,
        output_directory=output_directory,
        stopwords_path=stopwords_path,
        font_path=None,
        top=5,
        conversation_kind="private",
        viewer_speaker_key="wxid_fictional_me",
    )

    result = application.AnalysisApplicationService().execute(request)

    assert result.status is application.AnalysisStatus.COMPLETED
    payload = json.loads(
        (output_directory / "echo-report.json").read_text(encoding="utf-8")
    )
    assert payload["conversation"]["kind"] == "private"
    members = {member["speaker_key"]: member for member in payload["members"]}
    assert members["wxid_fictional_me"]["is_viewer"] is True
    assert members["wxid_fictional_peer"]["is_viewer"] is False
