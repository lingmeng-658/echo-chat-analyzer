"""Local-only Stage 3.5I2 acceptance harness. Never part of Provider/GUI.

Only anonymous checks/counts go to stdout. No credentials are requested.
Real artifacts live outside the repository in an owned, OS-locked workspace.
"""
from __future__ import annotations

import argparse
import json
import msvcrt
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import urllib.request


OWNER = {"kind": "echo-main-wal-poc", "version": 1}
ARTIFACTS = frozenset({
    "owner.json", "main.db", "main.db-wal", "merged.db", "snapshot.db",
    "snapshot.db-wal", "snapshot.db-shm", "snapshot.db-journal",
})


def _fail(code):
    raise RuntimeError(code)


def _no_links(path):
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            _fail("workspace_link_rejected")


class PocWorkspace:
    """A single Windows OS lease covering recovery, capture, consume, cleanup.

    The kernel releases byte-range locks on process termination. Recovery uses
    an explicit ownership marker and fixed artifact allowlist, never a PID or
    arbitrary source path. Unknown files and reparse points fail closed.
    """

    def __init__(self, root: Path, sources: list[Path]):
        self.root = Path(os.path.abspath(root))
        _no_links(self.root)
        for source in sources:
            source = source.resolve(strict=True)
            if self.root == source.parent or self.root.is_relative_to(source.parent) or source.is_relative_to(self.root):
                _fail("workspace_overlaps_source")
        self.stage = self.root / "staging"
        self.lock = None
        self.locked = False

    def _recover(self):
        _no_links(self.stage)
        if not self.stage.exists():
            return
        if not self.stage.is_dir():
            _fail("staging_invalid")
        entries = list(self.stage.iterdir())
        # A kill between mkdir and marker creation can leave an empty directory.
        if entries:
            marker = self.stage / "owner.json"
            if not marker.is_file() or marker.is_symlink():
                _fail("staging_unowned")
            if json.loads(marker.read_text(encoding="utf-8")) != OWNER:
                _fail("staging_unowned")
        # Validate every entry before deleting any entry.
        for entry in entries:
            _no_links(entry)
            if entry.name not in ARTIFACTS or not entry.is_file():
                _fail("staging_unowned")
        # Keep the ownership marker until every artifact was deleted, so a
        # cleanup error or process kill leaves a recognizable owned staging.
        for entry in entries:
            if entry.name != "owner.json":
                entry.unlink()
        marker = self.stage / "owner.json"
        marker.unlink(missing_ok=True)
        self.stage.rmdir()

    def _release(self):
        if self.lock is not None:
            try:
                if self.locked:
                    self.lock.seek(0)
                    msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self.lock.close()
                self.lock = None
                self.locked = False

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        _no_links(self.root / "lease.lock")
        self.lock = (self.root / "lease.lock").open("a+b")
        created_stage = False
        try:
            self.lock.seek(0)
            try:
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                _fail("workspace_busy")
            self.locked = True
            marker = self.root / "owner.json"
            _no_links(marker)
            if not marker.exists():
                if any(p.name != "lease.lock" for p in self.root.iterdir()):
                    _fail("workspace_unowned")
                with marker.open("x", encoding="utf-8") as stream:
                    json.dump(OWNER, stream)
            if json.loads(marker.read_text(encoding="utf-8")) != OWNER:
                _fail("workspace_unowned")
            if any(p.name not in {"owner.json", "lease.lock", "staging"} for p in self.root.iterdir()):
                _fail("workspace_unowned")
            self._recover()
            self.stage.mkdir()
            created_stage = True
            with (self.stage / "owner.json").open("x", encoding="utf-8") as stream:
                json.dump(OWNER, stream)
            return self.stage
        except BaseException:
            try:
                if created_stage:
                    # This invocation created the empty directory; no capture
                    # can have started yet. Remove even a partial marker write.
                    (self.stage / "owner.json").unlink(missing_ok=True)
                    self.stage.rmdir()
            finally:
                self._release()
            raise

    def __exit__(self, *_exception):
        try:
            self._recover()
        finally:
            self._release()


def _rpc(method, params, timeout=45):
    request = urllib.request.Request(
        "http://127.0.0.1:40654/rpc",
        data=json.dumps({"method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        envelope = json.load(response)
    if envelope.get("ok") is not True:
        _fail("bridge_rejected")
    return envelope.get("result")


def run_acceptance(repeat):
    script = Path(__file__).with_name("main_wal_poc.mjs")
    # getNtDbDir stays inside this process; it is never logged or persisted.
    directory = _rpc("DatabaseApi.getNtDbDir", [])
    if not isinstance(directory, str):
        _fail("source_unavailable")
    main = Path(directory) / "nt_msg.db"
    wal = Path(f"{main}-wal")
    root = Path(tempfile.gettempdir()) / "echo-main-wal-poc-i2"
    results = []
    initial_state = (main.stat().st_size, main.stat().st_mtime_ns, wal.stat().st_size, wal.stat().st_mtime_ns)
    for number in range(repeat):
        result = {"attempt": number + 1, "ok": False}
        try:
            with PocWorkspace(root, [main, wal]) as stage:
                merged, snapshot = stage / "merged.db", stage / "snapshot.db"
                process = subprocess.run(
                    ["node", str(script), "merge", str(main), str(wal), str(merged)],
                    capture_output=True, timeout=45,
                )
                # Never forward subprocess stderr or exceptions with arguments.
                payload = json.loads(process.stdout)
                if process.returncode or payload.get("ok") is not True:
                    result["code"] = payload.get("code", "capture_failed")
                else:
                    decrypted = _rpc("DatabaseApi.decryptDatabase", [str(merged), str(snapshot)])
                    if not decrypted or not snapshot.is_file():
                        _fail("decrypt_failed")
                    connection = sqlite3.connect(f"{snapshot.as_uri()}?mode=ro&immutable=1", uri=True)
                    try:
                        quick = connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
                        integrity = connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                        tables = connection.execute("SELECT count(*) FROM sqlite_schema WHERE type='table'").fetchone()[0]
                        # Provider's fixed table; count only, never read messages.
                        rows = connection.execute("SELECT count(*) FROM group_msg_table").fetchone()[0]
                    finally:
                        connection.close()
                    result.update(ok=quick and integrity and tables > 0, quickCheck=quick, integrityCheck=integrity,
                                  tables=tables, rows=rows, selectedCommitFrame=payload["selectedCommitFrame"],
                                  pages=payload["pages"], sourceState=payload["sourceState"])
            result["stagingCleaned"] = not (root / "staging").exists()
        except Exception:
            # Fixed failure code: never serialize exception text, RPC envelopes,
            # sqlite error payloads, file paths or source bytes.
            result.update(ok=False, code="acceptance_failed", stagingCleaned=not (root / "staging").exists())
        results.append(result)
        print(json.dumps(result), flush=True)
    final_state = (main.stat().st_size, main.stat().st_mtime_ns, wal.stat().st_size, wal.stat().st_mtime_ns)
    ready = _rpc("DatabaseApi.hasPassphrase", []) is True
    summary = {"attempts": repeat, "successes": sum(r["ok"] for r in results),
               "qqStillReady": ready, "sourceActivityObserved": initial_state != final_state,
               "allStagingCleaned": all(r.get("stagingCleaned") for r in results)}
    print(json.dumps(summary), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5, choices=range(1, 11))
    arguments = parser.parse_args()
    try:
        summary = run_acceptance(arguments.repeat)
        raise SystemExit(0 if summary["successes"] == arguments.repeat and summary["qqStillReady"] and summary["allStagingCleaned"] else 1)
    except Exception:
        print(json.dumps({"ok": False, "code": "acceptance_unavailable"}))
        raise SystemExit(1)
