"""Fictional lifecycle coverage; no real QQ paths or payloads."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/qq_direct_db_snapshot/main_wal_acceptance.py"
pytestmark = pytest.mark.slow_integration


def _workspace_type():
    spec = importlib.util.spec_from_file_location("poc_acceptance", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PocWorkspace


@pytest.mark.parametrize("interrupt", [False, True])
def test_success_and_exception_clean_all_owned_artifacts(tmp_path, interrupt):
    workspace = _workspace_type()
    source = tmp_path / "source"
    source.mkdir()
    main = source / "fictional.db"
    main.write_bytes(b"fictional source remains untouched")
    root = tmp_path / "owned"
    if interrupt:
        with pytest.raises(RuntimeError, match="fictional"):
            with workspace(root, [main]) as stage:
                for name in ("main.db", "main.db-wal", "merged.db", "snapshot.db", "snapshot.db-shm", "snapshot.db-journal"):
                    (stage / name).write_bytes(b"fictional temporary")
                raise RuntimeError("fictional interruption")
    else:
        with workspace(root, [main]) as stage:
            for name in ("main.db", "main.db-wal", "merged.db", "snapshot.db", "snapshot.db-wal"):
                (stage / name).write_bytes(b"fictional temporary")
    assert not (root / "staging").exists()
    assert main.read_bytes() == b"fictional source remains untouched"


def test_actual_process_kill_recovered_on_next_acquisition(tmp_path):
    root, source = tmp_path / "owned", tmp_path / "source" / "fictional.db"
    source.parent.mkdir()
    source.write_bytes(b"fictional user source")
    program = """
import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('poc',sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with m.PocWorkspace(Path(sys.argv[2]), [Path(sys.argv[3])]) as stage:
 for name in ('main.db','main.db-wal','merged.db','snapshot.db'):
  (stage/name).write_bytes(b'fictional interrupted artifact')
 print('ready',flush=True)
 time.sleep(30)
"""
    child = subprocess.Popen([sys.executable, "-c", program, str(SCRIPT), str(root), str(source)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        child.kill()
        child.communicate(timeout=10)
        assert (root / "staging" / "snapshot.db").exists()
        with _workspace_type()(root, [source]) as stage:
            assert sorted(p.name for p in stage.iterdir()) == ["owner.json"]
        assert not (root / "staging").exists()
        assert source.read_bytes() == b"fictional user source"
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


@pytest.mark.parametrize("case", ["unknown_root", "source_root", "unknown_staging"])
def test_unowned_files_never_deleted(tmp_path, case):
    workspace = _workspace_type()
    root = tmp_path / "owned"
    root.mkdir()
    source = tmp_path / "source" / "fictional.db"
    source.parent.mkdir()
    source.write_bytes(b"fictional source")
    sentinel = root / "unowned.db"
    if case == "source_root":
        source = root / "fictional.db"
        source.write_bytes(b"fictional source")
        with pytest.raises(Exception):
            with workspace(root, [source]):
                pass
        assert source.read_bytes() == b"fictional source"
    elif case == "unknown_root":
        sentinel.write_bytes(b"fictional unowned")
        with pytest.raises(Exception):
            with workspace(root, [source]):
                pass
        assert sentinel.read_bytes() == b"fictional unowned"
    elif case == "unknown_staging":
        with workspace(root, [source]):
            pass
        stage = root / "staging"
        stage.mkdir()
        sentinel = stage / "unowned.db"
        sentinel.write_bytes(b"fictional unowned")
        with pytest.raises(Exception):
            with workspace(root, [source]):
                pass
        assert sentinel.read_bytes() == b"fictional unowned"


def test_cleanup_failure_retains_owner_and_blocks_until_recovery(tmp_path, monkeypatch):
    workspace = _workspace_type()
    root = tmp_path / "owned"
    source = tmp_path / "source" / "fictional.db"
    source.parent.mkdir()
    source.write_bytes(b"fictional source")
    original_unlink = Path.unlink

    def fail_plaintext_delete(path, *args, **kwargs):
        if path.name == "snapshot.db":
            raise PermissionError("fictional cleanup denied")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_plaintext_delete)
        with pytest.raises(PermissionError):
            with workspace(root, [source]) as stage:
                (stage / "snapshot.db").write_bytes(b"fictional plaintext")
        assert (root / "staging" / "owner.json").exists()
        with pytest.raises(PermissionError):
            with workspace(root, [source]):
                pytest.fail("must not acquire before stale plaintext deletion")
    with workspace(root, [source]) as stage:
        assert list(p.name for p in stage.iterdir()) == ["owner.json"]


def test_live_workspace_lease_prevents_other_acquisition(tmp_path):
    workspace = _workspace_type()
    root = tmp_path / "owned"
    source = tmp_path / "source" / "fictional.db"
    source.parent.mkdir()
    source.write_bytes(b"fictional source")
    with workspace(root, [source]) as stage:
        (stage / "snapshot.db").write_bytes(b"fictional live plaintext")
        with pytest.raises(RuntimeError, match="workspace_busy"):
            with workspace(root, [source]):
                pass
        assert (stage / "snapshot.db").read_bytes() == b"fictional live plaintext"


@pytest.mark.parametrize("location", ["root", "staging_entry"])
def test_junction_cannot_redirect_cleanup_to_source(tmp_path, location):
    import _winapi

    workspace = _workspace_type()
    root = tmp_path / "owned"
    source = tmp_path / "source" / "fictional.db"
    source.parent.mkdir()
    source.write_bytes(b"fictional untouched source")
    if location == "root":
        _winapi.CreateJunction(str(source.parent), str(root))
        with pytest.raises(RuntimeError, match="workspace_link_rejected"):
            with workspace(root, [source]):
                pass
    else:
        with pytest.raises(RuntimeError, match="workspace_link_rejected"):
            with workspace(root, [source]) as stage:
                _winapi.CreateJunction(str(source.parent), str(stage / "main.db"))
        with pytest.raises(RuntimeError, match="workspace_link_rejected"):
            with workspace(root, [source]):
                pass
    assert source.read_bytes() == b"fictional untouched source"


def test_empty_staging_from_kill_before_marker_recovered(tmp_path):
    workspace = _workspace_type()
    root = tmp_path / "owned"
    source = tmp_path / "source" / "fictional.db"
    source.parent.mkdir()
    source.write_bytes(b"fictional source")
    with workspace(root, [source]):
        pass
    (root / "staging").mkdir()
    with workspace(root, [source]) as stage:
        assert list(p.name for p in stage.iterdir()) == ["owner.json"]


def test_other_process_cannot_recover_live_staging(tmp_path):
    workspace = _workspace_type()
    root = tmp_path / "owned"
    source = tmp_path / "source" / "fictional.db"
    source.parent.mkdir()
    source.write_bytes(b"fictional source")
    program = """
import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('poc',sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
try:
 with m.PocWorkspace(Path(sys.argv[2]), [Path(sys.argv[3])]): pass
except RuntimeError as error:
 if str(error)=='workspace_busy': print('busy'); sys.exit(0)
sys.exit(1)
"""
    with workspace(root, [source]) as stage:
        (stage / "snapshot.db").write_bytes(b"fictional active generation")
        result = subprocess.run([sys.executable, "-c", program, str(SCRIPT), str(root), str(source)],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0
        assert result.stdout.strip() == "busy"
        assert (stage / "snapshot.db").read_bytes() == b"fictional active generation"


def test_stage_marker_write_exception_cleans_and_releases_lease(tmp_path, monkeypatch):
    import json

    workspace = _workspace_type()
    root = tmp_path / "owned"
    source = tmp_path / "source" / "fictional.db"
    source.parent.mkdir()
    source.write_bytes(b"fictional source")
    with workspace(root, [source]):
        pass

    def interrupt_marker(_owner, stream):
        stream.write("{")
        raise OSError("fictional interrupted marker write")

    with monkeypatch.context() as patch:
        patch.setattr(json, "dump", interrupt_marker)
        with pytest.raises(OSError):
            with workspace(root, [source]):
                pass
        assert not (root / "staging").exists()
    with workspace(root, [source]):
        pass
