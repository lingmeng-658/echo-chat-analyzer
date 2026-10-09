"""Only fictional process snapshots; no host QQ processes are touched."""
import importlib
import json
import os
import subprocess
from types import SimpleNamespace

import pytest


def test_detection_excludes_owned_launcher_tree_but_keeps_all_user_qq(monkeypatch):
    module = importlib.import_module("qq_chat_analyzer.application.qq.qq_process_detection")
    rows = [
        {"ProcessId": 10, "ParentProcessId": 1, "Name": "NapCatWinBootMain.exe"},
        {"ProcessId": 11, "ParentProcessId": 10, "Name": "QQ.exe"},
        {"ProcessId": 12, "ParentProcessId": 11, "Name": "QQ.exe"},
        {"ProcessId": 20, "ParentProcessId": 1, "Name": "QQ.exe"},
        {"ProcessId": 21, "ParentProcessId": 20, "Name": "qq.EXE"},
        {"ProcessId": 30, "ParentProcessId": 1, "Name": "Other.exe"},
    ]
    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(rows)))
    assert module.find_conflicting_qq_pids((10,)) == [20, 21]


@pytest.mark.parametrize("output,returncode", [("", 1), ("broken", 0), ("{}", 0), ("null", 0)])
def test_detection_fails_closed_on_unreliable_snapshot(monkeypatch, output, returncode):
    module = importlib.import_module("qq_chat_analyzer.application.qq.qq_process_detection")
    monkeypatch.setattr(module.os, "name", "nt")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=returncode, stdout=output))
    with pytest.raises((OSError, ValueError)):
        module.find_conflicting_qq_pids(())


@pytest.mark.slow_integration
@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell query contract")
def test_powershell_query_uses_fictional_cim_rows_and_preserves_empty_arrays(monkeypatch):
    module = importlib.import_module("qq_chat_analyzer.application.qq.qq_process_detection")
    real_run = subprocess.run
    for body, expected in [
        ("", []),
        ("[pscustomobject]@{ProcessId=501;ParentProcessId=1;Name='QQ.exe'}", [501]),
        ("[pscustomobject]@{ProcessId=501;ParentProcessId=1;Name='QQ.exe'}; "
         "[pscustomobject]@{ProcessId=502;ParentProcessId=501;Name='QQ.exe'}", [501, 502]),
    ]:
        def run_with_fictional_cim(command, **kwargs):
            command = list(command)
            command[-1] = "function Get-CimInstance { " + body + " }; " + command[-1]
            return real_run(command, **kwargs)
        monkeypatch.setattr(module.subprocess, "run", run_with_fictional_cim)
        assert module.find_conflicting_qq_pids(()) == expected
