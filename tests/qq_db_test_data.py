"""Synthetic protobuf data shared by QQ DB adapter and import tests."""

from __future__ import annotations


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
