"""Synthetic protobuf data shared by QQ DB adapter and import tests."""

from __future__ import annotations

import base64


def encode_varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def length_delimited_field(field_number: int, value: bytes) -> bytes:
    return (
        encode_varint((field_number << 3) | 2)
        + encode_varint(len(value))
        + value
    )


def synthetic_text_message_blob(text: str) -> bytes:
    segment = (
        encode_varint((45002 << 3) | 0)
        + encode_varint(1)
        + length_delimited_field(45101, text.encode("utf-8"))
    )
    return length_delimited_field(40800, segment)


def scalar_field(tag: int, value: int) -> bytes:
    return encode_varint(tag << 3) + encode_varint(value)


def qq_db_record(text="", *, sender_id="100000001", nickname="Fictional Alice",
                 timestamp=1760000000, message_id="fictional-message", faces=(),
                 stickers=(), mention=None, reply_sequence=None):
    segments = []
    if reply_sequence is not None:
        segments.append(scalar_field(45002, 7) + scalar_field(47402, reply_sequence)
                        + scalar_field(47404, 100))
    if mention is not None:
        segments.append(scalar_field(45002, 1)
                        + length_delimited_field(45101, mention.encode())
                        + scalar_field(45102, 2))
    if text:
        segments.append(scalar_field(45002, 1)
                        + length_delimited_field(45101, text.encode()))
    segments.extend(scalar_field(45002, 6) + scalar_field(47601, int(key))
                    + length_delimited_field(47602, label.encode()) for key, label in faces)
    segments.extend(scalar_field(45002, 11)
                    + length_delimited_field(45600, key.encode())
                    + length_delimited_field(80900, label.encode()) for key, label in stickers)
    return {
        "record_id": message_id,
        "fields": {"40033": sender_id, "40050": timestamp},
        "sender": {"nickname": nickname},
        "blob_encoding": "base64",
        "message_blob": base64.b64encode(b"".join(
            length_delimited_field(40800, segment) for segment in segments
        )).decode(),
    }


def qq_db_payload(records, *, session_type="group", session_id="fictional-room", self_uin=None):
    payload = {
        "format": "qq-db-json", "format_version": 0,
        "source": "qq", "source_type": "qq-db-json",
        "query": {"session_type": session_type, "session_object": session_id},
        "records": records,
    }
    if self_uin is not None:
        payload["self"] = {"namespace": "qq_uin", "value": self_uin}
    return payload
