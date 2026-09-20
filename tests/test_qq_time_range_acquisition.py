"""Regression tests for the QQ acquisition time-range bug.

Reported symptom: the GUI selects a short window ("last two days"), yet the
progress line reports a full-history acquisition ("已获取 185,823 条").
Root cause: the facade dropped the resolved scope when building the QQ export
request (``start_time=None`` / ``end_time=None``), so QCE exported every
message and the reported count was the whole conversation.

These tests pin the fixed contract:

* a dated scope reaches the QQ request as inclusive local-day milliseconds;
* the QCE page scan stops once the window is covered (no full-history scan);
* the "all time" scope keeps the previous unfiltered behavior.

Every collaborator is fictional: the QCE transport is faked, no real service
or chat data is contacted.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from qq_chat_analyzer.application import (
    ChatDataSnapshotManager,
    QQExportImportService,
)
from qq_chat_analyzer.application.dto import (
    AnalysisResultDTO,
    AnalysisStatus,
)
from qq_chat_analyzer.application.facade import (
    AnalysisConfig,
    ChatAnalyzerFacade,
    ChatSource,
)
from qq_chat_analyzer.application.scope_filter import AnalysisScope
from qq_chat_analyzer.providers.qq_chat_exporter_provider import (
    QQChatExporterProvider,
)


FAKE_TOKEN = "fictional-token-0000"
PAGE_SIZE = 100
ONE_DAY_MILLIS = 24 * 60 * 60 * 1000
# A deliberately huge fictional history: the point of the bug is that a
# two-day window must never walk all of it.
TOTAL_FICTIONAL_MESSAGES = 200_000


def _midnight_millis(value: date) -> int:
    """Local-time midnight of one calendar date in QCE milliseconds."""
    return int(datetime.combine(value, time.min).timestamp() * 1000)


def _inclusive_window(start: date, end: date) -> tuple[int, int]:
    """Inclusive local-day window in milliseconds, matching the scope filter."""
    return (
        _midnight_millis(start),
        _midnight_millis(end + timedelta(days=1)) - 1,
    )


def _analysis_result() -> AnalysisResultDTO:
    return AnalysisResultDTO(
        status=AnalysisStatus.COMPLETED,
        processed_message_count=2,
        valid_text_count=2,
    )


def _export_file(tmp_path: Path) -> Path:
    """Write a fictional one-message QCE export that exists on disk."""
    path = tmp_path / "qq-time-range-export.json"
    payload = {
        "metadata": {
            "exportedAt": "2026-08-11T00:00:00Z",
            "version": "4.0.0",
        },
        "chatInfo": {
            "chatType": 2,
            "peerUid": "700000001",
            "name": "Fictional Test Group",
        },
        "statistics": {"totalMessages": 1},
        "messages": [
            {
                "id": "fictional-1",
                "seq": 1,
                "timestamp": 1754841600000,
                "sender": {"uin": "1001", "name": "Fictional Alice"},
                "type": "text",
                "content": {"text": "Fictional line"},
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _acquisition(export_path: Path) -> object:
    return type(
        "FictionalAcquisition",
        (),
        {
            "payload_path": export_path,
            "snapshot_id": None,
            "acquired_at": None,
            "reused_snapshot": False,
        },
    )()


class _RecordingQQService:
    """QQ service stub that records the acquisition request instead of exporting."""

    def __init__(self, export_path: Path | None) -> None:
        self._export_path = export_path
        self.requests: list[object] = []

    def list_sessions(self) -> list[object]:
        return []

    def acquire_export(self, request, progress=None):
        self.requests.append(request)
        return _acquisition(self._export_path)


class _RecordingAnalysisService:
    """Analysis service stub that records the request it is handed."""

    def __init__(self, result: AnalysisResultDTO) -> None:
        self._result = result
        self.requests: list[object] = []

    def execute(self, request):
        self.requests.append(request)
        return self._result


class _RecordingPresentationBuilder:
    """Presentation stub so tests never build a real dashboard view."""

    def __init__(self) -> None:
        self.calls = 0

    def build(self, reports, *, top_words=()):
        self.calls += 1
        return object()


def _recording_facade(
    qq_service: _RecordingQQService,
    analysis_service: _RecordingAnalysisService,
) -> ChatAnalyzerFacade:
    return ChatAnalyzerFacade(
        qq_service=qq_service,
        analysis_service=analysis_service,
        presentation_builder=_RecordingPresentationBuilder(),
    )


def _two_day_config(tmp_path: Path) -> AnalysisConfig:
    return AnalysisConfig(
        start_time="2026-08-10",
        end_time="2026-08-11",
        output_directory=tmp_path / "facade-output",
    )


class _FakeQceExportBackend:
    """Minimal QCE stand-in for the newest-first, paged message scan.

    QCE pages a conversation backwards (newest first) and, given a
    ``filter.startTime``, stops as soon as one whole page predates the
    window. The fake mirrors that contract and counts how many pages the
    service had to fetch, so a two-day window must never walk the whole
    fictional history.
    """

    def __init__(
        self,
        *,
        export_path: Path,
        newest_millis: int,
        total_messages: int = TOTAL_FICTIONAL_MESSAGES,
    ) -> None:
        self._export_path = export_path
        self._newest_millis = newest_millis
        self._total_messages = total_messages
        self.pages_scanned = 0
        self.export_bodies: list[dict[str, object]] = []
        self._tasks: dict[str, dict[str, object]] = {}

    def __call__(self, method, url, payload, headers, timeout):
        if method == "GET" and "/api/groups" in url:
            return 200, self._envelope({"groups": []})
        if method == "GET" and "/api/friends" in url:
            return 200, self._envelope({"friends": []})
        if method == "POST" and url.endswith("/api/messages/export"):
            body = json.loads(payload.decode("utf-8"))
            self.export_bodies.append(body)
            filter_block = body.get("filter")
            message_count = self._scan(
                (filter_block or {}).get("startTime"),
                (filter_block or {}).get("endTime"),
            )
            task = {
                "taskId": f"fictional-task-{len(self.export_bodies)}",
                "status": "completed",
                "messageCount": message_count,
                "filePath": str(self._export_path),
            }
            self._tasks[str(task["taskId"])] = task
            return 200, self._envelope(task)
        if method == "GET" and "/api/tasks/" in url:
            task_id = url.rsplit("/", 1)[-1]
            return 200, self._envelope(self._tasks[task_id])
        raise AssertionError(f"unexpected QCE request: {method} {url}")

    @staticmethod
    def _envelope(data: object) -> str:
        return json.dumps({"success": True, "data": data, "requestId": "req-1"})

    def _scan(self, start_millis: object, end_millis: object) -> int:
        """Walk pages newest-first, exactly like QCE's reverse history scan."""
        self.pages_scanned = 0
        counted = 0
        total_pages = -(-self._total_messages // PAGE_SIZE)
        page_span = PAGE_SIZE * ONE_DAY_MILLIS
        for page_index in range(total_pages):
            page_newest = self._newest_millis - page_index * page_span
            self.pages_scanned += 1
            for offset in range(PAGE_SIZE):
                index = page_index * PAGE_SIZE + offset
                if index >= self._total_messages:
                    break
                moment = self._newest_millis - index * ONE_DAY_MILLIS
                if start_millis is not None and moment < start_millis:
                    continue
                if end_millis is not None and moment > end_millis:
                    continue
                counted += 1
            if start_millis is not None and page_newest < start_millis:
                # Every remaining page is older still: QCE stops paging here.
                break
        return counted


def _end_to_end_facade(
    tmp_path: Path,
    backend: _FakeQceExportBackend,
) -> ChatAnalyzerFacade:
    """Wire the real QQ service + provider around the fake QCE transport."""
    provider = QQChatExporterProvider(
        token=FAKE_TOKEN,
        transport=backend,
        sleep=lambda _seconds: None,
    )
    service = QQExportImportService(
        provider=provider,
        snapshot_manager=ChatDataSnapshotManager(tmp_path / "user-data"),
    )
    return ChatAnalyzerFacade(
        qq_service=service,
        analysis_service=_RecordingAnalysisService(_analysis_result()),
        presentation_builder=_RecordingPresentationBuilder(),
    )


def test_qq_scope_reaches_the_acquisition_request_as_milliseconds(
    tmp_path: Path,
) -> None:
    """RED before the fix: the QQ request carried ``start_time=None``."""
    qq_service = _RecordingQQService(_export_file(tmp_path))
    facade = _recording_facade(qq_service, _RecordingAnalysisService(_analysis_result()))
    expected_start, expected_end = _inclusive_window(
        date(2026, 8, 10),
        date(2026, 8, 11),
    )

    facade.analyze_session(
        ChatSource.QQ,
        "700000001",
        _two_day_config(tmp_path),
    )

    request = qq_service.requests[0]
    assert request.start_time == expected_start
    assert request.end_time == expected_end
    assert request.start_time > 10**12  # milliseconds, never epoch seconds


def test_qq_acquisition_window_covers_both_inclusive_local_days(
    tmp_path: Path,
) -> None:
    """Boundary contract: 00:00:00.000 through 23:59:59.999 local, inclusive."""
    qq_service = _RecordingQQService(_export_file(tmp_path))
    facade = _recording_facade(qq_service, _RecordingAnalysisService(_analysis_result()))

    facade.analyze_session(ChatSource.QQ, "700000001", _two_day_config(tmp_path))

    request = qq_service.requests[0]
    assert isinstance(request.start_time, int)
    assert isinstance(request.end_time, int)
    assert request.start_time % 1000 == 0  # midnight, no leftover millis
    assert request.end_time % 1000 == 999  # last millisecond of the end date
    assert datetime.fromtimestamp(request.start_time / 1000) == datetime(
        2026, 8, 10, 0, 0
    )
    assert datetime.fromtimestamp((request.end_time + 1) / 1000) == datetime(
        2026, 8, 12, 0, 0
    )
    # A mid-August window has no DST transition on any supported host.
    assert request.end_time - request.start_time == 2 * ONE_DAY_MILLIS - 1


def test_acquisition_window_matches_the_analysis_scope(tmp_path: Path) -> None:
    """Acquisition and analysis derive from the same two-day scope."""
    qq_service = _RecordingQQService(_export_file(tmp_path))
    analysis_service = _RecordingAnalysisService(_analysis_result())
    facade = _recording_facade(qq_service, analysis_service)
    expected_start, expected_end = _inclusive_window(
        date(2026, 8, 10),
        date(2026, 8, 11),
    )

    facade.analyze_session(ChatSource.QQ, "700000001", _two_day_config(tmp_path))

    assert analysis_service.requests[0].scope == AnalysisScope.custom(
        date(2026, 8, 10),
        date(2026, 8, 11),
    )
    request = qq_service.requests[0]
    assert (request.start_time, request.end_time) == (
        expected_start,
        expected_end,
    )


def test_all_scope_keeps_the_unfiltered_full_history_request(
    tmp_path: Path,
) -> None:
    """Regression guard: "全部时间" must not gain an invented filter."""
    qq_service = _RecordingQQService(_export_file(tmp_path))
    facade = _recording_facade(qq_service, _RecordingAnalysisService(_analysis_result()))

    facade.analyze_session(
        ChatSource.QQ,
        "700000001",
        AnalysisConfig(output_directory=tmp_path / "facade-output"),
    )

    request = qq_service.requests[0]
    assert request.start_time is None
    assert request.end_time is None


def test_two_day_scope_stops_the_qce_page_scan_early(tmp_path: Path) -> None:
    """The reported symptom: a two-day window must not fetch 200k messages."""
    export_path = _export_file(tmp_path)
    start = date(2026, 8, 10)
    end = date(2026, 8, 11)
    backend = _FakeQceExportBackend(
        export_path=export_path,
        newest_millis=_midnight_millis(end + timedelta(days=1)) - 1,
    )
    facade = _end_to_end_facade(tmp_path, backend)
    expected_start, expected_end = _inclusive_window(start, end)
    progress: list[str] = []

    facade.analyze_session(
        ChatSource.QQ,
        "700000001",
        AnalysisConfig(
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            output_directory=tmp_path / "facade-output",
        ),
        progress=progress.append,
    )

    # Two pages: the recent one plus the page that proves the cutoff is past.
    assert backend.pages_scanned == 2
    assert backend.export_bodies[0]["filter"] == {
        "startTime": expected_start,
        "endTime": expected_end,
    }
    assert "正在获取 QQ 聊天记录 · 已获取 2 条" in progress
    assert not any("200,000" in message for message in progress)


def test_all_scope_still_scans_the_full_history(tmp_path: Path) -> None:
    """Unchanged behavior: "全部时间" still gets the whole conversation."""
    export_path = _export_file(tmp_path)
    backend = _FakeQceExportBackend(
        export_path=export_path,
        newest_millis=_midnight_millis(date(2026, 8, 12)) - 1,
    )
    facade = _end_to_end_facade(tmp_path, backend)
    progress: list[str] = []

    facade.analyze_session(
        ChatSource.QQ,
        "700000001",
        AnalysisConfig(output_directory=tmp_path / "facade-output"),
        progress=progress.append,
    )

    assert backend.pages_scanned == TOTAL_FICTIONAL_MESSAGES // PAGE_SIZE
    assert "filter" not in backend.export_bodies[0]
    assert "正在获取 QQ 聊天记录 · 已获取 200,000 条" in progress
