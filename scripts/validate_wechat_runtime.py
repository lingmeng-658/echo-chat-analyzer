"""Development-only validation entry for the real WeChat database chain.

Usage:
    python scripts/validate_wechat_runtime.py \
        --data-root "D:\\WeChatData\\xwechat_files" \
        --db-key "64-hex-db-key" \
        --wcdb-cli "build\\wcdb_cli\\Release\\wcdb_cli.exe" \
        --wcdb-dll "path\\to\\WCDB.dll"

The script never opens the GUI, never uploads data, and never prints chat
content, account identifiers, or database keys.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
os.environ.setdefault(
    "MPLCONFIGDIR",
    str(PROJECT_ROOT / "build" / "matplotlib-config"),
)
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.providers.wechat_database_provider import (  # noqa: E402
    WeChatDatabaseProvider,
)
from qq_chat_analyzer.validation.wechat_runtime_validator import (  # noqa: E402
    WeChatRuntimeValidation,
    validate_wechat_runtime,
)


class _PrivacySafeArgumentParser(argparse.ArgumentParser):
    """Avoid echoing command-line values when an argument is invalid."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(
            "\u9519\u8bef\uff1a\u547d\u4ee4\u884c\u53c2\u6570\u65e0\u6548\u3002",
            file=sys.stderr,
        )
        raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one WeChat runtime validation and print the report."""
    parser = _PrivacySafeArgumentParser(
        prog="validate_wechat_runtime",
        description=(
            "\u9a8c\u8bc1\u5fae\u4fe1\u6570\u636e\u5e93\u8bfb\u53d6\u94fe\u8def"
            "\u662f\u5426\u53ef\u4ee5\u5b8c\u6210\u5206\u6790\u95ed\u73af\u3002"
        ),
    )
    parser.add_argument(
        "--data-root",
        required=True,
        help="\u5fae\u4fe1 4.x \u6570\u636e\u6839\u76ee\u5f55\u3002",
    )
    parser.add_argument(
        "--db-key",
        default=None,
        help="\u5fae\u4fe1\u6570\u636e\u5e93\u5bc6\u94a5\uff0c"
        "\u4e5f\u53ef\u4ee5\u4f7f\u7528 WX_DB_KEY \u73af\u5883\u53d8\u91cf\u3002",
    )
    parser.add_argument(
        "--wcdb-cli",
        default=None,
        help="wcdb_cli.exe \u8def\u5f84\uff0c\u7f3a\u7701\u81ea\u52a8\u641c\u7d22\u3002",
    )
    parser.add_argument(
        "--wcdb-dll",
        default=None,
        help="WCDB.dll \u8def\u5f84\uff0c\u7f3a\u7701\u65f6\u4f1a\u62a5 runtime \u4e0d\u53ef\u7528\u3002",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="\u53ef\u9009\uff1a\u6307\u5b9a\u8981\u9a8c\u8bc1\u7684\u4f1a\u8bdd\u3002",
    )
    parser.add_argument(
        "--message-limit",
        type=int,
        default=50,
        help="\u53ea\u8bfb\u53d6\u524d N \u6761\u6d88\u606f\uff0c\u9ed8\u8ba4 50\u3002",
    )
    arguments = parser.parse_args(argv)

    db_key = arguments.db_key or os.environ.get("WX_DB_KEY")
    if not db_key:
        print(
            "\u9519\u8bef\uff1a\u7f3a\u5c11\u5fae\u4fe1\u6570\u636e\u5e93\u5bc6\u94a5"
            "\uff0c\u8bf7\u4f7f\u7528 --db-key \u6216\u8bbe\u7f6e WX_DB_KEY\u3002",
            file=sys.stderr,
        )
        return 2
    if arguments.message_limit <= 0:
        print(
            "\u9519\u8bef\uff1a--message-limit \u5fc5\u987b\u5927\u4e8e 0\u3002",
            file=sys.stderr,
        )
        return 2

    provider = WeChatDatabaseProvider(
        data_root=arguments.data_root,
        db_key=db_key,
        wcdb_cli_path=arguments.wcdb_cli,
        wcdb_dll_path=arguments.wcdb_dll,
    )
    try:
        report = validate_wechat_runtime(
            provider,
            session_id=arguments.session_id,
            message_limit=arguments.message_limit,
        )
    except Exception:
        print(
            "\u9519\u8bef\uff1a\u9a8c\u8bc1\u8fc7\u7a0b\u53d1\u751f"
            "\u672a\u9884\u671f\u95ee\u9898\u3002",
            file=sys.stderr,
        )
        return 2

    _print_report(report)
    return 0 if report.ok else 1


def _print_report(report: WeChatRuntimeValidation) -> None:
    print(
        "\u9a8c\u8bc1\u73af\u5883: "
        + ("\u901a\u8fc7" if report.environment_ok else "\u5931\u8d25")
    )
    print(
        "\u4f1a\u8bdd\u8bfb\u53d6: "
        + ("\u901a\u8fc7" if report.session_read else "\u5931\u8d25")
    )
    print(
        "\u6d88\u606f\u8bfb\u53d6: "
        + ("\u901a\u8fc7" if report.message_read else "\u5931\u8d25")
    )
    print(f"\u539f\u59cb\u6d88\u606f\u6570\u91cf: {report.raw_message_count}")
    print(f"ChatMessage \u6570\u91cf: {report.chat_message_count}")
    print(
        "\u5206\u6790\u670d\u52a1: "
        + ("\u901a\u8fc7" if report.analysis_ok else "\u5931\u8d25")
    )
    if report.analysis_status:
        print(f"\u5206\u6790\u72b6\u6001: {report.analysis_status}")
    for error in report.errors:
        print(f"\u9519\u8bef: {error}")


if __name__ == "__main__":
    raise SystemExit(main())
