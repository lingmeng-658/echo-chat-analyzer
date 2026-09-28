"""Runtime-side Direct DB snapshot lifecycle tests (Phase 1).

These tests drive the real ``scripts/qq_direct_db_snapshot/snapshot.mjs``
template under the system Node runtime with a fictional in-process ``core``,
so they exercise the generation + atomic-publish scheme without any real QQ
account, passphrase or plaintext data.

The helper is an ESM module, so each test writes a small ``.mjs`` driver into a
temporary directory, points it at the real template via a file URL, feeds it a
JSON plan, and inspects the returned status objects plus the on-disk layout.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_TEMPLATE = PROJECT_ROOT / "scripts" / "qq_direct_db_snapshot" / "snapshot.mjs"
PINS_PATH = PROJECT_ROOT / "scripts" / "qq_runtime_pins.json"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason="the Direct DB snapshot helper tests require a system Node runtime",
)

# The one privacy-safe identity value every success test uses.  It is fictional
# and may freely appear in assertions here; it must never leak from the helper.
FICTIONAL_UIN = "10086"

# Stable error codes the helper is allowed to surface.
STABLE_CODES = {
    "passphrase_unavailable",
    "decrypt_failed",
    "identity_missing",
    "identity_changed",
    "manifest_failed",
    "publish_failed",
    "cleanup_failed",
    "generation_not_found",
    "recover_failed",
}

# Fragments that must never appear in a helper status object.
FORBIDDEN_STATUS_FRAGMENTS = (
    FICTIONAL_UIN,
    "\\",
    "/",
    "manifest.json",
    "snapshot.db",
    "passphrase",
)


_DRIVER = r"""import { createEchoSnapshotApi, registerEchoSnapshotApi } from '__SNAPSHOT_URL__';
import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2];
const config = JSON.parse(process.argv[3]);

let activeDecrypt = 0;
const metrics = { decryptCalls: 0, maxActiveDecrypt: 0 };
const diagnostics = [];
console.error = (...args) => {
  diagnostics.push(args.map(String).join(' '));
};

function buildCore() {
  const core = { selfInfo: { uin: config.uin }, apis: {} };
  if (config.databaseApiPresent !== false) {
    core.apis.DatabaseApi = {
      hasPassphrase() {
        return config.passphrase !== false;
      },
      async decryptDatabase(source, target) {
        metrics.decryptCalls += 1;
        activeDecrypt += 1;
        metrics.maxActiveDecrypt = Math.max(metrics.maxActiveDecrypt, activeDecrypt);
        try {
          if (config.decryptDelayMs) {
            await new Promise((resolveDelay) => setTimeout(resolveDelay, config.decryptDelayMs));
          }
          if (config.decrypt === 'false') {
            return false;
          }
          if (config.decrypt === 'throw') {
            throw new Error('fictional decrypt failure');
          }
          fs.mkdirSync(path.dirname(target), { recursive: true });
          fs.writeFileSync(target, 'fictional-sqlite-db');
          if (config.decryptMutateUin !== undefined) {
            core.selfInfo.uin = config.decryptMutateUin;
          }
          if (config.decryptCreatesManifestDir) {
            fs.mkdirSync(path.join(path.dirname(target), 'manifest.json'));
          }
          if (config.decryptCreatesGenerationsFile) {
            fs.writeFileSync(path.join(root, 'generations'), 'conflict');
          }
          return true;
        } finally {
          activeDecrypt -= 1;
        }
      },
    };
  }
  return core;
}

const out = {};

if (config.register === true) {
  const runtimeCore = { apis: {} };
  const returned = registerEchoSnapshotApi(runtimeCore);
  const api = runtimeCore.apis.EchoSnapshotApi;
  out.registered = {
    isObject: !!(api && typeof api === 'object'),
    hasAcquire: typeof (api && api.acquire) === 'function',
    hasCleanup: typeof (api && api.cleanup) === 'function',
    hasRecover: typeof (api && api.recover) === 'function',
    sameAsReturned: api === returned,
  };
  out.metrics = metrics;
  out.results = [];
  out.diagnostics = diagnostics;
} else {
  const core = buildCore();
  const api = createEchoSnapshotApi(core, {
    rootDirectory: root,
    timeouts: config.timeouts || {},
  });
  const results = [];
  for (const op of config.operations) {
    if (op.op === 'acquire') {
      results.push({ op: 'acquire', result: await api.acquire() });
    } else if (op.op === 'cleanup') {
      results.push({ op: 'cleanup', result: await api.cleanup(op.arg) });
    } else if (op.op === 'recover') {
      results.push({ op: 'recover', result: await api.recover() });
    } else if (op.op === 'concurrent-acquire') {
      const pair = await Promise.all([api.acquire(), api.acquire()]);
      results.push({ op: 'concurrent-acquire', result: pair });
    }
  }
  out.results = results;
  out.metrics = metrics;
  out.diagnostics = diagnostics;
}

console.log(JSON.stringify(out));
"""


def _snapshot_url() -> str:
    assert SNAPSHOT_TEMPLATE.is_file(), (
        "the Direct DB snapshot template is missing: "
        "scripts/qq_direct_db_snapshot/snapshot.mjs"
    )
    return SNAPSHOT_TEMPLATE.as_uri()


def _run_node(root: Path, config: dict, driver_dir: Path | None = None) -> dict:
    # ``root`` is the snapshot root handed to the helper; ``driver_dir`` is a
    # real directory where the .mjs driver can be written.  They only differ
    # when a test intentionally passes a non-directory root to trigger the
    # fail-closed cleanup path.
    driver_dir = driver_dir or root
    driver = driver_dir / "driver.mjs"
    driver.write_text(
        _DRIVER.replace("__SNAPSHOT_URL__", _snapshot_url()),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [NODE, str(driver), str(root), json.dumps(config)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _test_timeouts(**overrides) -> dict:
    timeouts = {"passphraseMs": 200, "identityMs": 200, "pollIntervalMs": 10}
    timeouts.update(overrides)
    return timeouts


def _generation_ids(root: Path) -> list[str]:
    generations = root / "generations"
    if not generations.is_dir():
        return []
    return sorted(entry.name for entry in generations.iterdir() if entry.is_dir())


def _read_manifest(root: Path, generation_id: str) -> dict:
    manifest = root / "generations" / generation_id / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8"))


def _acquire(config: dict) -> dict:
    config.setdefault("operations", [{"op": "acquire"}])
    config.setdefault("timeouts", _test_timeouts())
    return config


def _seed_legacy_plaintext(root: Path) -> None:
    legacy = root / "decrypted"
    legacy.mkdir(parents=True)
    (legacy / "nt_msg.before.plaintext.db").write_bytes(b"fictional-legacy-db")
    (legacy / "nt_msg.before.plaintext.db-wal").write_bytes(b"fictional-wal")
    (legacy / "nt_msg.before.plaintext.db-shm").write_bytes(b"fictional-shm")
    (legacy / "self_identity.json").write_text(
        json.dumps({"namespace": "qq_uin", "value": FICTIONAL_UIN}),
        encoding="utf-8",
    )


def _seed_staging(root: Path) -> None:
    staging = root / "staging" / "partial"
    staging.mkdir(parents=True)
    (staging / "snapshot.db").write_bytes(b"fictional-partial-db")


def _seed_generation(root: Path, generation_id: str) -> None:
    generation = root / "generations" / generation_id
    generation.mkdir(parents=True)
    (generation / "snapshot.db").write_bytes(b"fictional-snapshot-db")
    (generation / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generation_id": generation_id,
                "state": "ready",
                "database": "snapshot.db",
                "identity": {"namespace": "qq_uin", "value": FICTIONAL_UIN},
            }
        ),
        encoding="utf-8",
    )


# ------------------------------------------------------------------ acquire


def test_passphrase_unavailable_removes_previous_plaintext_first(
    tmp_path: Path,
) -> None:
    """When the passphrase never arrives, the fail-closed cleanup still ran."""
    _seed_legacy_plaintext(tmp_path)
    _seed_staging(tmp_path)
    _seed_generation(tmp_path, "previous-generation")

    output = _run_node(
        tmp_path,
        _acquire({"passphrase": False, "uin": FICTIONAL_UIN}),
    )

    result = output["results"][0]["result"]
    assert result == {"ok": False, "code": "passphrase_unavailable", "status": "failed"}
    # The previous plaintext, staging and generation were all deleted first.
    assert not (tmp_path / "decrypted").exists()
    assert not (tmp_path / "staging").exists()
    assert _generation_ids(tmp_path) == []
    assert output["metrics"]["decryptCalls"] == 0


@pytest.mark.parametrize(
    ("config", "expected_stage"),
    (
        ({"databaseApiPresent": False}, "database_api_not_ready"),
        ({"passphrase": False}, "passphrase_not_ready"),
        ({"uin": None, "passphrase": True}, "identity_not_ready"),
        ({"decrypt": "false", "passphrase": True}, "decrypt_failed"),
        (
            {
                "decryptCreatesGenerationsFile": True,
                "passphrase": True,
            },
            "publish_failed",
        ),
    ),
)
def test_acquire_logs_one_privacy_safe_diagnostic_stage(
    tmp_path: Path,
    config: dict,
    expected_stage: str,
) -> None:
    output = _run_node(
        tmp_path,
        _acquire({"uin": FICTIONAL_UIN, **config}),
    )

    assert output["diagnostics"] == [
        f"qq_direct_db.diagnostic stage={expected_stage}"
    ]
    serialized = json.dumps(output["diagnostics"])
    for fragment in (FICTIONAL_UIN, str(tmp_path), "snapshot.db", "nt_msg.db"):
        assert fragment not in serialized, fragment

@pytest.mark.parametrize("decrypt", ["false", "throw"])
def test_decrypt_failure_never_publishes_a_ready_generation(
    tmp_path: Path,
    decrypt: str,
) -> None:
    output = _run_node(
        tmp_path,
        _acquire({"decrypt": decrypt, "uin": FICTIONAL_UIN}),
    )

    result = output["results"][0]["result"]
    assert result == {"ok": False, "code": "decrypt_failed", "status": "failed"}
    assert _generation_ids(tmp_path) == []
    assert not (tmp_path / "staging").exists()


def test_missing_identity_fails_closed_without_decrypting(tmp_path: Path) -> None:
    output = _run_node(
        tmp_path,
        _acquire({"uin": None, "passphrase": True}),
    )

    result = output["results"][0]["result"]
    assert result == {"ok": False, "code": "identity_missing", "status": "failed"}
    assert _generation_ids(tmp_path) == []
    assert output["metrics"]["decryptCalls"] == 0


def test_identity_changed_during_decrypt_fails_closed(tmp_path: Path) -> None:
    output = _run_node(
        tmp_path,
        _acquire(
            {"uin": "111111", "decryptMutateUin": "222222", "passphrase": True}
        ),
    )

    result = output["results"][0]["result"]
    assert result == {"ok": False, "code": "identity_changed", "status": "failed"}
    assert _generation_ids(tmp_path) == []
    assert not (tmp_path / "staging").exists()
    assert output["metrics"]["decryptCalls"] == 1


@pytest.mark.parametrize(
    "failure_flag",
    ["decryptCreatesManifestDir", "decryptCreatesGenerationsFile"],
)
def test_manifest_or_publish_failure_leaves_no_ready_generation(
    tmp_path: Path,
    failure_flag: str,
) -> None:
    config = _acquire({"uin": FICTIONAL_UIN, "passphrase": True})
    config[failure_flag] = True

    output = _run_node(tmp_path, config)

    result = output["results"][0]["result"]
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["code"] in {"manifest_failed", "publish_failed"}
    assert _generation_ids(tmp_path) == []


def test_success_publishes_database_and_identity_in_one_generation(
    tmp_path: Path,
) -> None:
    output = _run_node(
        tmp_path,
        _acquire({"uin": FICTIONAL_UIN, "passphrase": True}),
    )

    result = output["results"][0]["result"]
    assert result["ok"] is True
    assert result["status"] == "ready"
    generation_id = result["generation_id"]

    assert _generation_ids(tmp_path) == [generation_id]
    assert (tmp_path / "generations" / generation_id / "snapshot.db").is_file()
    manifest = _read_manifest(tmp_path, generation_id)
    assert manifest == {
        "schema_version": 1,
        "generation_id": generation_id,
        "state": "ready",
        "database": "snapshot.db",
        "identity": {"namespace": "qq_uin", "value": FICTIONAL_UIN},
    }
    # No staging or legacy plaintext survives a successful acquire.
    assert not (tmp_path / "staging").exists()
    assert not (tmp_path / "decrypted").exists()


def test_each_acquire_uses_a_fresh_opaque_generation_id(tmp_path: Path) -> None:
    output = _run_node(
        tmp_path,
        {
            "uin": FICTIONAL_UIN,
            "passphrase": True,
            "timeouts": _test_timeouts(),
            "operations": [{"op": "acquire"}, {"op": "acquire"}],
        },
    )

    first = output["results"][0]["result"]
    second = output["results"][1]["result"]
    assert first["ok"] and second["ok"]
    assert first["generation_id"] != second["generation_id"]
    assert first["generation_id"]
    assert second["generation_id"]


def test_concurrent_acquire_never_decrypts_in_parallel(tmp_path: Path) -> None:
    output = _run_node(
        tmp_path,
        {
            "uin": FICTIONAL_UIN,
            "passphrase": True,
            "decryptDelayMs": 30,
            "timeouts": _test_timeouts(),
            "operations": [{"op": "concurrent-acquire"}],
        },
    )

    first, second = output["results"][0]["result"]
    assert first["ok"] and second["ok"]
    assert first["generation_id"] != second["generation_id"]
    assert output["metrics"]["maxActiveDecrypt"] == 1
    assert output["metrics"]["decryptCalls"] == 2
    # Only the latest generation survives; earlier ones were cleaned first.
    assert _generation_ids(tmp_path) == [second["generation_id"]]


def test_cleanup_failure_carries_a_stable_privacy_safe_code(tmp_path: Path) -> None:
    # A broken snapshot root (a file where a directory is required) makes the
    # fail-closed cleanup fail before any decryption can start.
    (tmp_path / "root-file").write_text("not a directory", encoding="utf-8")
    root = tmp_path / "root-file"

    output = _run_node(
        root,
        {
            "uin": FICTIONAL_UIN,
            "passphrase": True,
            "timeouts": _test_timeouts(),
            "operations": [{"op": "acquire"}],
        },
        driver_dir=tmp_path,
    )

    result = output["results"][0]["result"]
    assert result == {"ok": False, "code": "cleanup_failed", "status": "failed"}
    assert output["metrics"]["decryptCalls"] == 0


# ------------------------------------------------------------------ cleanup


def test_cleanup_removes_only_the_requested_generation(tmp_path: Path) -> None:
    _seed_generation(tmp_path, "keep-me")
    _seed_generation(tmp_path, "delete-me")

    output = _run_node(
        tmp_path,
        {
            "uin": FICTIONAL_UIN,
            "passphrase": True,
            "timeouts": _test_timeouts(),
            "operations": [{"op": "cleanup", "arg": "delete-me"}],
        },
    )

    result = output["results"][0]["result"]
    assert result == {"ok": True, "status": "cleaned"}
    assert _generation_ids(tmp_path) == ["keep-me"]


def test_cleanup_missing_generation_returns_a_stable_code(tmp_path: Path) -> None:
    output = _run_node(
        tmp_path,
        {
            "uin": FICTIONAL_UIN,
            "passphrase": True,
            "timeouts": _test_timeouts(),
            "operations": [{"op": "cleanup", "arg": "no-such-generation"}],
        },
    )

    result = output["results"][0]["result"]
    assert result == {"ok": False, "code": "generation_not_found", "status": "failed"}


def test_cleanup_rejects_path_traversal_and_leaves_everything_untouched(
    tmp_path: Path,
) -> None:
    _seed_generation(tmp_path, "keep-me")

    output = _run_node(
        tmp_path,
        {
            "uin": FICTIONAL_UIN,
            "passphrase": True,
            "timeouts": _test_timeouts(),
            "operations": [{"op": "cleanup", "arg": "../keep-me"}],
        },
    )

    result = output["results"][0]["result"]
    assert result == {"ok": False, "code": "generation_not_found", "status": "failed"}
    assert _generation_ids(tmp_path) == ["keep-me"]


# ------------------------------------------------------------------ recover


def test_recover_removes_orphan_staging_and_legacy_plaintext(
    tmp_path: Path,
) -> None:
    _seed_legacy_plaintext(tmp_path)
    _seed_staging(tmp_path)
    _seed_generation(tmp_path, "orphan-generation")

    output = _run_node(
        tmp_path,
        {
            "uin": FICTIONAL_UIN,
            "passphrase": True,
            "timeouts": _test_timeouts(),
            "operations": [{"op": "recover"}],
        },
    )

    result = output["results"][0]["result"]
    assert result == {"ok": True, "status": "recovered"}
    assert _generation_ids(tmp_path) == []
    assert not (tmp_path / "staging").exists()
    assert not (tmp_path / "decrypted").exists()


# ----------------------------------------------------------- status privacy


def test_status_objects_never_leak_identity_or_paths(tmp_path: Path) -> None:
    output = _run_node(
        tmp_path,
        {
            "uin": FICTIONAL_UIN,
            "passphrase": True,
            "decrypt": "throw",
            "timeouts": _test_timeouts(),
            "operations": [{"op": "acquire"}],
        },
    )

    serialized = json.dumps(output)
    for fragment in FORBIDDEN_STATUS_FRAGMENTS:
        assert fragment not in serialized, fragment


# -------------------------------------------------- registration seam (static)


def test_index_patch_no_longer_auto_decrypts_at_startup() -> None:
    pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    patch = pins["indexPatch"]

    replacement = patch["replacement"]
    assert "registerEchoSnapshotApi(runtimeCore)" in replacement
    assert "createSnapshotFromNapCatCore" not in replacement
    assert "await createSnapshotFromNapCatCore(core)" not in replacement
    assert (
        "const { registerEchoSnapshotApi } = "
        "await import('./direct_db_research/snapshot.mjs');"
    ) == patch["addedLine"]
    assert replacement.count(patch["addedLine"]) == 1


def test_snapshot_template_registers_echo_snapshot_api_on_runtimecore_apis() -> None:
    text = SNAPSHOT_TEMPLATE.read_text(encoding="utf-8")

    assert "export function registerEchoSnapshotApi" in text
    assert "runtimeCore.apis.EchoSnapshotApi = api" in text
    for method in ("acquire", "cleanup", "recover"):
        assert f"{method}," in text or f"return {{ acquire, cleanup, recover }}" in text
    # It must never auto-decrypt on registration.
    assert "createSnapshotFromNapCatCore" not in text


def test_registration_exposes_acquire_cleanup_recover(tmp_path: Path) -> None:
    output = _run_node(tmp_path, {"register": True})

    assert output["registered"] == {
        "isObject": True,
        "hasAcquire": True,
        "hasCleanup": True,
        "hasRecover": True,
        "sameAsReturned": True,
    }
    assert output["metrics"]["decryptCalls"] == 0
