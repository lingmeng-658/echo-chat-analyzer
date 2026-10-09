"""Read-only QQ conflict detection; ownership comes from the launch registry."""
from __future__ import annotations

import json
import os
import subprocess


def find_conflicting_qq_pids(owned_pids: tuple[int, ...]) -> list[int]:
    """Return user QQ processes, excluding recorded launchers and descendants.

    A bounded CIM query supplies the whole tree so QQ renderer children are
    included even when their executable name differs in case. Detection errors
    propagate: an unreadable snapshot must never be treated as an empty one.
    """
    if os.name != "nt":
        return []
    script = (
        "$ErrorActionPreference='Stop'; "
        "$rows=@(Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name); "
        "ConvertTo-Json -InputObject $rows -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=5, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise OSError("QQ process query failed")
    rows = json.loads(result.stdout)
    if not isinstance(rows, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("ProcessId"), int)
        or not isinstance(row.get("ParentProcessId"), int)
        or not isinstance(row.get("Name"), str)
        for row in rows
    ):
        raise ValueError("Invalid QQ process snapshot")
    owned = set(owned_pids)
    while True:
        children = {row["ProcessId"] for row in rows if row["ParentProcessId"] in owned}
        if children.issubset(owned):
            break
        owned.update(children)
    return sorted({row["ProcessId"] for row in rows
                   if row["Name"].lower() == "qq.exe" and row["ProcessId"] not in owned})
