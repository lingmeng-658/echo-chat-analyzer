"""Credential plumbing shared by the two local bridge RPC clients.

The credential itself is owned by ``QQRuntimeSession`` (application layer);
this module only knows how to read it from an injected session-like source and
how to present it on the wire.  Keeping the header in one place means the
Python client and the NapCat plugin cannot drift apart.

Providers must not import the application layer, so the session is consumed by
shape (``.credential()``) rather than by type.
"""

from __future__ import annotations

import re

AUTHORIZATION_HEADER = "Authorization"
BEARER_SCHEME = "Bearer "


def resolve_bridge_credential(source: object) -> str | None:
    """Return the current credential of ``source``, or ``None``.

    ``source`` is a session-like object exposing ``credential()``.  Anything
    else (including ``None``) means "no live credential": callers fail closed
    instead of sending an unauthenticated request.
    """
    if source is None:
        return None
    getter = getattr(source, "credential", None)
    if not callable(getter):
        return None
    value = getter()
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def authorization_headers(credential: str) -> dict[str, str]:
    """Return the request headers that present one credential."""
    return {AUTHORIZATION_HEADER: f"{BEARER_SCHEME}{credential}"}


__all__ = [
    "AUTHORIZATION_HEADER",
    "BEARER_SCHEME",
    "authorization_headers",
    "resolve_bridge_credential",
]
