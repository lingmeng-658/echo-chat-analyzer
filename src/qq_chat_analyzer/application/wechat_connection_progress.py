"""Credential-acquisition milestones exposed to the WeChat GUI by Facade."""

from enum import Enum


class WeChatConnectionProgress(Enum):
    """One acquisition's progress, with no credentials or native diagnostics.

    READY_FOR_LOGIN means listener initialization succeeded, not that WeChat
    is on its login screen. CREDENTIAL_RECEIVED ends acquisition progress;
    database verification and session loading still follow separately.
    """

    PREPARING = "preparing"
    READY_FOR_LOGIN = "ready_for_login"
    CREDENTIAL_RECEIVED = "credential_received"
