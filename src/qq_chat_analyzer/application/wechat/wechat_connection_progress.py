"""Credential-acquisition milestones exposed to the WeChat GUI by Facade."""

from enum import Enum


class WeChatConnectionProgress(Enum):
    """One acquisition's progress, with no credentials or native diagnostics.

    WAITING_FOR_WECHAT_EXIT waits for every initial PID to disappear;
    WAITING_FOR_WECHAT_START accepts PIDs after that observed exit, including
    reused PID numbers.
    READY_FOR_LOGIN means listener initialization succeeded, not that WeChat
    is on its login screen. CREDENTIAL_RECEIVED ends acquisition progress;
    database verification and session loading still follow separately.
    """

    PREPARING = "preparing"
    WAITING_FOR_WECHAT_EXIT = "waiting_for_wechat_exit"
    WAITING_FOR_WECHAT_START = "waiting_for_wechat_start"
    READY_FOR_LOGIN = "ready_for_login"
    CREDENTIAL_RECEIVED = "credential_received"
