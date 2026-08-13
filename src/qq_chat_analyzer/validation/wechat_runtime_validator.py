"""Development-only validation for the real WeChat database chain.

This module is not part of the product flow. It gives a developer one entry
point to verify that a real WeChat data directory, key, and native runtime can
feed the existing provider -> service -> adapter -> analysis pipeline without
opening the GUI or reading chat content beyond the small sample requested.

No parsing logic is changed here. The validator reuses existing providers,
services, adapters, and analysis code, and its report only contains aggregate
counts plus user-safe error messages.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..application.dto import AnalysisRequestDTO
from ..application.wechat_connection_service import WeChatConnectionService
from ..application.wechat_export_import_service import (
    WeChatExportImportRequest,
    WeChatExportImportService,
)
from ..resources import resources_dir


DEFAULT_MESSAGE_LIMIT = 50
DEFAULT_ANALYSIS_TOP = 20
STOPWORDS_FILENAME = "stopwords.txt"

# Minimum MSVCP140.dll major/minor derived from the build toolchain (MSVC 14.43).
# Echo native components are built with that toolset; older x64 redistributables
# (e.g. 14.16) crash natively with 0xC0000005.
MSVC_RUNTIME_MINIMUM = (14, 43)
MSVCP140_X64_PATH = Path(
    os.environ.get("SystemRoot", r"C:\Windows")
) / "System32" / "msvcp140.dll"
VC_RUNTIME_ERROR_MESSAGE = (
    "Microsoft Visual C++ Runtime ????????"
    "???/?? Microsoft Visual C++ 2015-2022 Redistributable (x64)?"
)


@dataclass(frozen=True, slots=True)
class WeChatRuntimeValidation:
    """Aggregate result of one WeChat runtime validation run.

    The report contains counts and user-safe messages only. It never contains
    chat content, account identifiers, or database keys.
    """

    environment_ok: bool
    session_read: bool
    message_read: bool
    chat_message_count: int
    analysis_ok: bool
    analysis_status: str | None = None
    raw_message_count: int = 0
    session_count: int = 0
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return bool(
            self.environment_ok
            and self.session_read
            and self.message_read
            and self.analysis_ok
        )


def _read_file_version(path: Path) -> tuple[int, int, int, int] | None:
    """Read a Windows DLL file version tuple, or None when unavailable."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    version = ctypes.windll.version
    version.GetFileVersionInfoSizeW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    version.GetFileVersionInfoW.restype = wintypes.BOOL
    version.VerQueryValueW.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.UINT),
    ]
    version.VerQueryValueW.restype = wintypes.BOOL

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", wintypes.DWORD),
            ("dwStrucVersion", wintypes.DWORD),
            ("dwFileVersionMS", wintypes.DWORD),
            ("dwFileVersionLS", wintypes.DWORD),
            ("dwProductVersionMS", wintypes.DWORD),
            ("dwProductVersionLS", wintypes.DWORD),
            ("dwFileFlagsMask", wintypes.DWORD),
            ("dwFileFlags", wintypes.DWORD),
            ("dwFileOS", wintypes.DWORD),
            ("dwFileType", wintypes.DWORD),
            ("dwFileSubtype", wintypes.DWORD),
            ("dwFileDateMS", wintypes.DWORD),
            ("dwFileDateLS", wintypes.DWORD),
        ]

    size = version.GetFileVersionInfoSizeW(str(path), None)
    if size == 0:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
        return None
    value_ptr = ctypes.c_void_p()
    value_len = wintypes.UINT()
    if not version.VerQueryValueW(
        buffer, "\\", ctypes.byref(value_ptr), ctypes.byref(value_len)
    ):
        return None
    info = ctypes.cast(value_ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    return (
        info.dwFileVersionMS >> 16,
        info.dwFileVersionMS & 0xFFFF,
        info.dwFileVersionLS >> 16,
        info.dwFileVersionLS & 0xFFFF,
    )


def check_vc_runtime(
    *,
    platform: str | None = None,
    dll_path: Path | None = None,
    version_reader: Callable[[Path], tuple[int, int, int, int] | None] | None = None,
    minimum: tuple[int, int] = MSVC_RUNTIME_MINIMUM,
) -> tuple[bool, str | None]:
    """Check that the x64 VC++ Runtime (MSVCP140.dll) is present and new enough.

    Returns ``(ok, error_message)``. Non-Windows platforms always pass so the
    check never misjudges other operating systems. All inputs are injectable
    for tests; the defaults read the real x64 redistributable on Windows.
    """
    if (platform or sys.platform) != "win32":
        return True, None
    reader = version_reader or _read_file_version
    path = dll_path or MSVCP140_X64_PATH
    version = reader(path)
    if version is None:
        return False, VC_RUNTIME_ERROR_MESSAGE
    if (version[0], version[1]) < minimum:
        return False, VC_RUNTIME_ERROR_MESSAGE
    return True, None


class _LimitedExportProvider:
    """Forward provider calls while capping export size for validation."""

    def __init__(self, provider: Any, limit: int) -> None:
        self._provider = provider
        self._limit = limit

    def list_sessions(self) -> list[Any]:
        return self._provider.list_sessions()

    def export_session_json(
        self,
        session_id: str,
        output_path: Any,
        start_time: Any = None,
        end_time: Any = None,
    ) -> Any:
        return self._provider.export_session_json(
            session_id,
            output_path,
            start_time=start_time,
            end_time=end_time,
            limit=self._limit,
        )


def validate_wechat_runtime(
    provider: Any,
    *,
    session_id: str | None = None,
    message_limit: int = DEFAULT_MESSAGE_LIMIT,
    analysis_service: Any | None = None,
    stopwords_path: Path | None = None,
    vc_runtime_check: Callable[[], tuple[bool, str | None]] | None = None,
) -> WeChatRuntimeValidation:
    """Run the complete WeChat chain against one local provider.

    ``provider`` is expected to satisfy the same surface as
    :class:`~qq_chat_analyzer.providers.wechat_database_provider
    .WeChatDatabaseProvider`: resolver probes, session listing, and JSON
    export. The function never raises; failures are normalised into the
    returned report.
    """
    errors: list[str] = []
    runtime_check = vc_runtime_check or check_vc_runtime
    runtime_ok, runtime_error = runtime_check()
    if not runtime_ok:
        errors.append(runtime_error or VC_RUNTIME_ERROR_MESSAGE)
        return _report(
            environment_ok=False,
            session_read=False,
            message_read=False,
            chat_message_count=0,
            analysis_ok=False,
            errors=errors,
        )
    effective_limit = (
        message_limit
        if isinstance(message_limit, int)
        and not isinstance(message_limit, bool)
        and message_limit > 0
        else DEFAULT_MESSAGE_LIMIT
    )

    environment = WeChatConnectionService(provider).check_status()
    if not environment.available:
        errors.append(environment.message)
        if environment.action_hint:
            errors.append(environment.action_hint)
        return _report(
            environment_ok=False,
            session_read=False,
            message_read=False,
            chat_message_count=0,
            analysis_ok=False,
            errors=errors,
        )

    try:
        sessions = provider.list_sessions()
    except Exception as error:
        errors.append(_normalize_error(error))
        return _report(
            environment_ok=True,
            session_read=False,
            message_read=False,
            chat_message_count=0,
            analysis_ok=False,
            errors=errors,
        )

    if not sessions:
        errors.append("\u672a\u627e\u5230\u4f1a\u8bdd\u3002")
        return _report(
            environment_ok=True,
            session_read=False,
            message_read=False,
            chat_message_count=0,
            analysis_ok=False,
            errors=errors,
        )

    target_session = _resolve_session(sessions, session_id)
    if target_session is None:
        errors.append("\u672a\u627e\u5230\u6307\u5b9a\u4f1a\u8bdd\u3002")
        return _report(
            environment_ok=True,
            session_read=False,
            message_read=False,
            chat_message_count=0,
            analysis_ok=False,
            errors=errors,
        )

    with tempfile.TemporaryDirectory(
        prefix="wechat-runtime-validation-"
    ) as scratch:
        scratch_dir = Path(scratch)
        export_path = scratch_dir / "wechat_export.json"
        try:
            service = WeChatExportImportService(
                _LimitedExportProvider(provider, effective_limit)
            )
            outcome = service.execute(
                WeChatExportImportRequest(
                    session_id=target_session,
                    output_path=export_path,
                )
            )
        except Exception as error:
            errors.append(_normalize_error(error))
            return _report(
                environment_ok=True,
                session_read=True,
                message_read=False,
                chat_message_count=0,
                analysis_ok=False,
                errors=errors,
            )

        raw_message_count = (
            getattr(outcome, "processed_message_count", 0) or 0
        )
        messages = getattr(outcome, "messages", ()) or ()
        chat_message_count = len(messages)
        message_read = raw_message_count > 0 and chat_message_count > 0
        if not message_read:
            errors.append(
                "\u672a\u8bfb\u53d6\u5230\u53ef\u8f6c\u6362\u7684"
                "\u6587\u672c\u6d88\u606f\u3002"
            )

        analysis_ok = False
        analysis_status: str | None = None
        try:
            from ..application.analysis_service import (
                AnalysisApplicationService,
            )

            service_instance = analysis_service or AnalysisApplicationService()
            request = AnalysisRequestDTO(
                input_path=export_path,
                output_directory=scratch_dir / "analysis_output",
                stopwords_path=(
                    stopwords_path
                    or resources_dir() / STOPWORDS_FILENAME
                ),
                top=DEFAULT_ANALYSIS_TOP,
            )
            result = service_instance.execute(request)
            analysis_ok = True
            status = getattr(result, "status", None)
            analysis_status = getattr(status, "value", None)
        except Exception as error:
            errors.append(_normalize_error(error))

        return _report(
            environment_ok=True,
            session_read=True,
            message_read=message_read,
            chat_message_count=chat_message_count,
            analysis_ok=analysis_ok,
            analysis_status=analysis_status,
            raw_message_count=raw_message_count,
            session_count=len(sessions),
            errors=errors,
        )


def _resolve_session(
    sessions: list[Any],
    requested_session_id: str | None,
) -> str | None:
    if requested_session_id:
        for session in sessions:
            candidate = getattr(session, "session_id", None)
            if candidate == requested_session_id:
                return candidate
        return None
    first = sessions[0]
    return getattr(first, "session_id", None)


def _normalize_error(error: Exception) -> str:
    message = getattr(error, "public_message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    return "\u53d1\u751f\u672a\u9884\u671f\u7684\u9519\u8bef\u3002"


def _report(
    *,
    environment_ok: bool,
    session_read: bool,
    message_read: bool,
    chat_message_count: int,
    analysis_ok: bool,
    analysis_status: str | None = None,
    raw_message_count: int = 0,
    session_count: int = 0,
    errors: list[str] | tuple[str, ...] = (),
) -> WeChatRuntimeValidation:
    return WeChatRuntimeValidation(
        environment_ok=environment_ok,
        session_read=session_read,
        message_read=message_read,
        chat_message_count=chat_message_count,
        analysis_ok=analysis_ok,
        analysis_status=analysis_status,
        raw_message_count=raw_message_count,
        session_count=session_count,
        errors=tuple(errors),
    )


__all__ = [
    "MSVC_RUNTIME_MINIMUM",
    "MSVCP140_X64_PATH",
    "VC_RUNTIME_ERROR_MESSAGE",
    "WeChatRuntimeValidation",
    "check_vc_runtime",
    "validate_wechat_runtime",
]
