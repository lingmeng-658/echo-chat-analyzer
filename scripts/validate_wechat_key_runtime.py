"""Privacy-safe local validation of automatic WeChat key and DB access."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application.wechat_environment_config import (  # noqa: E402
    WeChatEnvironmentConfig,
    WeChatEnvironmentConfigLoader,
)
from qq_chat_analyzer.application.wechat_key_service import (  # noqa: E402
    WeChatKeyService,
    WeChatKeyUnavailable,
)
from qq_chat_analyzer.application.wechat_provider_factory import (  # noqa: E402
    WeChatProviderFactory,
    default_provider_builder,
)


@dataclass(frozen=True)
class WeChatKeyRuntimeReport:
    key_acquired: bool
    database_open: bool
    schema_available: bool
    session_count: int
    messages_read: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.key_acquired and self.database_open and self.schema_available and self.messages_read


def validate_wechat_key_runtime(
    *,
    config_loader: Any,
    key_service: Any,
    provider_factory: Any,
    provider_builder: Callable[[WeChatEnvironmentConfig], Any] = default_provider_builder,
) -> WeChatKeyRuntimeReport:
    """Run the key-to-provider smoke test without exposing private data."""
    try:
        config = config_loader.load()
    except Exception as error:
        if error.__class__.__name__ == "WeChatConfigNotFound":
            config = WeChatEnvironmentConfig()
        else:
            return WeChatKeyRuntimeReport(
                False, False, False, 0, False, "微信连接设置不可用。"
            )
    key_acquired = bool(config.db_key and config.db_key.strip())
    if not key_acquired:
        try:
            key = key_service.acquire()
        except WeChatKeyUnavailable:
            return WeChatKeyRuntimeReport(False, False, False, 0, False, "微信连接准备失败，请重试。")
        except Exception:
            return WeChatKeyRuntimeReport(False, False, False, 0, False, "微信连接准备失败，请重试。")
        config = replace(config, db_key=key)
        key_acquired = True

    try:
        provider = provider_builder(config)
        sessions = provider.list_sessions()
        session_count = len(sessions)
        if not sessions:
            return WeChatKeyRuntimeReport(True, True, True, 0, False, "未找到微信会话。")
        first_session = getattr(sessions[0], "session_id", None)
        if not isinstance(first_session, str) or not first_session:
            return WeChatKeyRuntimeReport(True, True, False, session_count, False, "微信会话结构不可用。")
        provider.read_session_rows(first_session, limit=1)
    except Exception:
        return WeChatKeyRuntimeReport(True, False, False, 0, False, "微信数据库读取失败。")

    return WeChatKeyRuntimeReport(True, True, True, session_count, True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验证微信自动密钥与数据库读取链路。")
    parser.add_argument("--config", type=Path, default=None, help="可选配置文件路径。")
    args = parser.parse_args(argv)
    loader = WeChatEnvironmentConfigLoader(args.config)
    report = validate_wechat_key_runtime(
        config_loader=loader,
        key_service=WeChatKeyService(),
        provider_factory=WeChatProviderFactory(config_loader=loader),
    )
    print(f"key获取: {'成功' if report.key_acquired else '失败'}")
    print(f"数据库打开: {'成功' if report.database_open else '失败'}")
    print(f"表结构: {'可用' if report.schema_available else '不可用'}")
    print(f"session数量: {report.session_count}")
    if report.error:
        print(f"状态: {report.error}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
