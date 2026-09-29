// Local-only Direct DB snapshot lifecycle — runtime-side generation API (Phase 1).
//
// This helper never auto-decrypts and never accesses or serializes the
// passphrase.  It exposes a restricted EchoSnapshotApi with three methods
// (acquire / cleanup / recover) that own the plaintext snapshot lifecycle
// through an explicit generation + atomic-publish scheme:
//
//   <root>/generations/<id>/snapshot.db
//   <root>/generations/<id>/manifest.json
//
// The default <root> mirrors Python's canonical path
// ``runtime_directory.parent / output/qq_direct_db_phase35`` (four parent
// segments up from this file reach ``runtime/``).
//
// Privacy contract: status objects and log lines carry only stable codes,
// fixed stages, timestamps, opaque generation ids, and source-file size/
// change booleans. The identity value (QQ UIN), nicknames, message text, the
// passphrase and absolute paths never appear in a status object, log line or
// exception message.
import { appendFileSync, existsSync, mkdirSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const SCHEMA_VERSION = 1;
const IDENTITY_NAMESPACE = 'qq_uin';
const DATABASE_NAME = 'snapshot.db';
const MANIFEST_NAME = 'manifest.json';
const SOURCE_DATABASE_NAME = 'nt_msg.db';

const DEFAULT_TIMEOUTS = Object.freeze({
  passphraseMs: 30000,
  identityMs: 30000,
  pollIntervalMs: 250,
});

// Stable, privacy-safe error codes.  These are the only values that may reach
// a status object alongside the opaque generation id.
const CODES = Object.freeze({
  PASSHRASE_UNAVAILABLE: 'passphrase_unavailable',
  DECRYPT_FAILED: 'decrypt_failed',
  SNAPSHOT_UNSTABLE: 'snapshot_unstable',
  IDENTITY_MISSING: 'identity_missing',
  IDENTITY_CHANGED: 'identity_changed',
  MANIFEST_FAILED: 'manifest_failed',
  PUBLISH_FAILED: 'publish_failed',
  CLEANUP_FAILED: 'cleanup_failed',
  GENERATION_NOT_FOUND: 'generation_not_found',
  RECOVER_FAILED: 'recover_failed',
});

const helperDirectory = dirname(fileURLToPath(import.meta.url));
const defaultRoot = resolve(
  helperDirectory,
  '..',
  '..',
  '..',
  '..',
  'output',
  'qq_direct_db_phase35',
);

function canonicalizeUin(value) {
  if (value === null || value === undefined || typeof value === 'boolean') {
    return null;
  }
  let text;
  if (typeof value === 'string') {
    text = value.trim();
  } else if (typeof value === 'number') {
    text = String(value);
  } else {
    return null;
  }
  if (!text || text === '0') {
    return null;
  }
  return text;
}

function fail(code) {
  return { ok: false, code, status: 'failed' };
}

function sleep(milliseconds) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds));
}

function now() {
  return globalThis.performance?.now?.() ?? Date.now();
}
function logDiagnostic(stage) {
  console.error(`qq_direct_db.diagnostic stage=${stage}`);
}

function traceStage(stage, generationId = null) {
  // The launcher already uses this file for timestamped runtime diagnostics.
  // Only fixed stage names are written; a logging failure must not affect data.
  const logFile = process.env.QCE_LOG_FILE;
  if (!logFile) return;
  try {
    const generation = generationId ? ` generation_id=${generationId}` : '';
    appendFileSync(logFile, `[${new Date().toISOString()}] [echo-snapshot] stage=${stage}${generation}\n`);
  } catch {
    // Best-effort diagnostics only.
  }
}

function fileState(path) {
  try {
    const stat = statSync(path);
    return {
      present: stat.isFile(),
      bytes: stat.isFile() ? stat.size : 0,
      mtimeMs: stat.mtimeMs,
    };
  } catch {
    return { present: false, bytes: 0, mtimeMs: 0 };
  }
}

function sourceDatabaseState(databaseApi) {
  try {
    const getDirectory = databaseApi?.getNtDbDir;
    if (typeof getDirectory !== 'function') return null;
    const directory = getDirectory();
    if (typeof directory !== 'string' || !directory) return null;
    const database = join(directory, SOURCE_DATABASE_NAME);
    return {
      database: fileState(database),
      wal: fileState(`${database}-wal`),
      shm: fileState(`${database}-shm`),
    };
  } catch {
    return null;
  }
}

function stateChanged(before, after) {
  return before.present !== after.present ||
    before.bytes !== after.bytes ||
    before.mtimeMs !== after.mtimeMs;
}

function readWindowChanged(state) {
  // Missing or malformed telemetry is not evidence of a stable source. The
  // bundled NapCat patch records all four states around its native read.
  if (!state || typeof state !== 'object') return true;
  const validState = (value) => value && typeof value === 'object' &&
    typeof value.present === 'boolean' &&
    Number.isSafeInteger(value.bytes) && value.bytes >= 0 &&
    Number.isFinite(value.mtimeMs);
  if (!validState(state.databaseBefore) || !validState(state.databaseAfter) ||
      !validState(state.walBefore) || !validState(state.walAfter)) return true;
  // The native read consumes only the main database file. A main-file change
  // can produce a torn/inconsistent image; a WAL change separately means the
  // copied main file may omit committed WAL content. Neither is publishable as
  // a stable generation, but a WAL change alone does not prove corruption.
  const database = safeReadFileState(state.databaseBefore);
  const databaseAfter = safeReadFileState(state.databaseAfter);
  const wal = safeReadFileState(state.walBefore);
  const walAfter = safeReadFileState(state.walAfter);
  return stateChanged(database, databaseAfter) || stateChanged(wal, walAfter);
}

function traceSourceDatabaseState(stage, state, before = null, generationId = null) {
  if (!state) return;
  const logFile = process.env.QCE_LOG_FILE;
  if (!logFile) return;
  const changed = before
    ? ` database_changed=${stateChanged(before.database, state.database)}` +
      ` wal_changed=${stateChanged(before.wal, state.wal)}` +
      ` shm_changed=${stateChanged(before.shm, state.shm)}`
    : '';
  const details =
    `generation_id=${generationId} ` +
    `database_present=${state.database.present} database_bytes=${state.database.bytes} ` +
    `wal_present=${state.wal.present} wal_bytes=${state.wal.bytes} ` +
    `shm_present=${state.shm.present} shm_bytes=${state.shm.bytes}`;
  try {
    appendFileSync(
      logFile,
      `[${new Date().toISOString()}] [echo-snapshot] stage=${stage} ${details}${changed}\n`,
    );
  } catch {
    // Best-effort diagnostics only.
  }
}

function safeReadFileState(value) {
  return {
    present: value?.present === true,
    bytes: Number.isSafeInteger(value?.bytes) && value.bytes >= 0 ? value.bytes : 0,
    mtimeMs: Number.isFinite(value?.mtimeMs) ? value.mtimeMs : 0,
  };
}

function traceSourceReadState(rawState, generationId) {
  if (!rawState || typeof rawState !== 'object') return;
  const state = {
    databaseBefore: safeReadFileState(rawState.databaseBefore),
    databaseAfter: safeReadFileState(rawState.databaseAfter),
    walBefore: safeReadFileState(rawState.walBefore),
    walAfter: safeReadFileState(rawState.walAfter),
    shmBefore: safeReadFileState(rawState.shmBefore),
    shmAfter: safeReadFileState(rawState.shmAfter),
  };
  const readBytes = Number.isSafeInteger(rawState.readBytes) && rawState.readBytes >= 0
    ? rawState.readBytes
    : 0;
  const logFile = process.env.QCE_LOG_FILE;
  if (!logFile) return;
  try {
    appendFileSync(
      logFile,
      `[${new Date().toISOString()}] [echo-snapshot] stage=decrypt_source_read ` +
      `generation_id=${generationId} ` +
      `database_changed=${stateChanged(state.databaseBefore, state.databaseAfter)} ` +
      `wal_changed=${stateChanged(state.walBefore, state.walAfter)} ` +
      `shm_changed=${stateChanged(state.shmBefore, state.shmAfter)} ` +
      `database_before_bytes=${state.databaseBefore.bytes} ` +
      `database_after_bytes=${state.databaseAfter.bytes} ` +
      `wal_before_bytes=${state.walBefore.bytes} wal_after_bytes=${state.walAfter.bytes} ` +
      `shm_before_bytes=${state.shmBefore.bytes} shm_after_bytes=${state.shmAfter.bytes} ` +
      `read_bytes=${readBytes}\n`,
    );
  } catch {
    // Best-effort diagnostics only.
  }
}

/**
 * Normalize a caller-supplied generation id into a single path segment, or
 * return ``null`` when it cannot be a generation id.  ``cleanup`` must only
 * ever delete ``generations/<id>``, so separators and traversal segments are
 * rejected here rather than ever reaching the filesystem.
 */
function normalizeGenerationId(generationId) {
  let value = generationId;
  if (value && typeof value === 'object') {
    value = value.generation_id ?? value.generationId;
  }
  if (typeof value !== 'string') {
    return null;
  }
  const id = value.trim();
  if (!id || id === '.' || id === '..') {
    return null;
  }
  if (id.includes('/') || id.includes('\\')) {
    return null;
  }
  return id;
}

export function createEchoSnapshotApi(core, options = {}) {
  const {
    rootDirectory = defaultRoot,
    timeouts = {},
  } = options;

  const passphraseMs = timeouts.passphraseMs ?? DEFAULT_TIMEOUTS.passphraseMs;
  const identityMs = timeouts.identityMs ?? DEFAULT_TIMEOUTS.identityMs;
  const pollIntervalMs = timeouts.pollIntervalMs ?? DEFAULT_TIMEOUTS.pollIntervalMs;

  const generationsDirectory = join(rootDirectory, 'generations');
  const stagingDirectory = join(rootDirectory, 'staging');
  const legacyDecryptedDirectory = join(rootDirectory, 'decrypted');

  // Single-flight mutex: every mutating operation is serialized on one promise
  // chain, so decrypt can never run concurrently (max concurrency = 1).
  let lockTail = Promise.resolve();
  function withLock(task) {
    const run = lockTail.then(task, task);
    lockTail = run.then(
      () => {},
      () => {},
    );
    return run;
  }

  function cleanSlate() {
    try {
      // Establish the snapshot root first so a broken root is a hard,
      // fail-closed error rather than a silent no-op.
      mkdirSync(rootDirectory, { recursive: true });
      rmSync(generationsDirectory, { recursive: true, force: true });
      rmSync(stagingDirectory, { recursive: true, force: true });
      rmSync(legacyDecryptedDirectory, { recursive: true, force: true });
      return { ok: true };
    } catch {
      return { ok: false };
    }
  }

  let databaseApiSeen = false;

  async function waitForDatabaseApi() {
    const deadline = now() + passphraseMs;
    let firstPollRecorded = false;
    let pollCount = 0;
    let nextProgressTrace = now() + 5000;
    traceStage('passphrase_wait_started');
    while (now() < deadline) {
      pollCount += 1;
      if (pollCount === 2) traceStage('passphrase_second_poll_started');
      const api = core?.apis?.DatabaseApi;
      if (pollCount === 2) traceStage('passphrase_second_api_read');
      if (api && typeof api.hasPassphrase === 'function') {
        if (pollCount === 2) traceStage('passphrase_second_method_read');
        databaseApiSeen = true;
        try {
          const ready = api.hasPassphrase() === true;
          if (pollCount === 2) traceStage('passphrase_second_method_returned');
          if (ready) {
            if (!firstPollRecorded) traceStage('passphrase_wait_polled');
            // QCE's API adapter is a Proxy whose unknown-method fallback also
            // exposes a callable `then`. Returning that Proxy directly from an
            // async function makes Promise resolution treat it as a thenable;
            // the fallback ignores resolve/reject, so this wait never settles.
            return { databaseApi: api };
          }
        } catch {
          if (pollCount === 2) traceStage('passphrase_second_method_threw');
          // Transient read failure; retry within the bounded window.
        }
      }
      if (!firstPollRecorded) {
        traceStage('passphrase_wait_polled');
        firstPollRecorded = true;
        traceStage('passphrase_first_poll_completed');
      }
      if (pollCount === 1) traceStage('passphrase_first_sleep_scheduled');
      await sleep(pollIntervalMs);
      if (pollCount === 1) traceStage('passphrase_first_sleep_resumed');
      if (now() >= nextProgressTrace) {
        traceStage('passphrase_wait_tick');
        nextProgressTrace = now() + 5000;
      }
    }
    return null;
  }

  async function waitForIdentity() {
    const deadline = now() + identityMs;
    while (now() < deadline) {
      const value = canonicalizeUin(core?.selfInfo?.uin);
      if (value !== null) {
        return value;
      }
      await sleep(pollIntervalMs);
    }
    return null;
  }

  function discardStaging() {
    try {
      rmSync(stagingDirectory, { recursive: true, force: true });
    } catch {
      // Best-effort: a half-written staging generation is never published.
    }
  }

  async function acquire() {
    traceStage('acquire_queued');
    return withLock(async () => {
      traceStage('acquire_entered');
      // 1. Fail-closed cleanup: no decryption may start unless every previous
      //    generation, staging dir and legacy plaintext artifact is gone.
      const slate = cleanSlate();
      if (!slate.ok) {
        traceStage('slate_failed');
        return fail(CODES.CLEANUP_FAILED);
      }
      traceStage('slate_ready');

      // 2. Bounded wait for the in-process DatabaseApi and its passphrase.
      const databaseApiResult = await waitForDatabaseApi();
      if (!databaseApiResult) {
        traceStage(databaseApiSeen ? 'passphrase_not_ready' : 'database_api_not_ready');
        logDiagnostic(
          databaseApiSeen ? 'passphrase_not_ready' : 'database_api_not_ready',
        );
        return fail(CODES.PASSHRASE_UNAVAILABLE);
      }
      const { databaseApi } = databaseApiResult;
      traceStage('passphrase_ready');

      // 3. Bounded wait for a canonical self identity *before* decryption.
      const identityBefore = await waitForIdentity();
      if (identityBefore === null) {
        traceStage('identity_not_ready');
        logDiagnostic('identity_not_ready');
        return fail(CODES.IDENTITY_MISSING);
      }
      traceStage('identity_ready');

      const generationId = randomUUID();
      const generationDirectory = join(generationsDirectory, generationId);
      const stagingDatabase = join(stagingDirectory, DATABASE_NAME);
      const stagingManifest = join(stagingDirectory, MANIFEST_NAME);

      // 4. Decrypt into a staging generation on the same filesystem.
      try {
        mkdirSync(stagingDirectory, { recursive: true });
      } catch {
        logDiagnostic('publish_failed');
        return fail(CODES.PUBLISH_FAILED);
      }

      let decrypted = false;
      const sourceStateBefore = sourceDatabaseState(databaseApi);
      traceSourceDatabaseState('decrypt_source_before', sourceStateBefore, null, generationId);
      globalThis.__ECHO_DIRECT_DB_READ_STATE__ = null;
      traceStage('decrypt_started');
      try {
        decrypted = Boolean(
          await databaseApi.decryptDatabase(SOURCE_DATABASE_NAME, stagingDatabase),
        );
      } catch {
        decrypted = false;
      }
      traceStage('decrypt_finished');
      const sourceReadState = globalThis.__ECHO_DIRECT_DB_READ_STATE__;
      globalThis.__ECHO_DIRECT_DB_READ_STATE__ = null;
      traceSourceReadState(sourceReadState, generationId);
      traceSourceDatabaseState(
        'decrypt_source_after',
        sourceDatabaseState(databaseApi),
        sourceStateBefore,
        generationId,
      );
      if (!decrypted || !existsSync(stagingDatabase)) {
        discardStaging();
        logDiagnostic('decrypt_failed');
        return fail(CODES.DECRYPT_FAILED);
      }

      // 5. The source must have been stable across the native read window.
      //    A snapshot read while the source database or WAL was changing is a
      //    mid-write image; publishing it would hand Python a corrupt file.
      if (readWindowChanged(sourceReadState)) {
        discardStaging();
        traceStage('snapshot_unstable', generationId);
        return fail(CODES.SNAPSHOT_UNSTABLE);
      }

      // 6. The canonical self identity must still exist and be unchanged.
      const identityAfter = canonicalizeUin(core?.selfInfo?.uin);
      if (identityAfter === null) {
        discardStaging();
        return fail(CODES.IDENTITY_MISSING);
      }
      if (identityAfter !== identityBefore) {
        discardStaging();
        return fail(CODES.IDENTITY_CHANGED);
      }

      // 7. Manifest and database belong to the same generation.  The identity
      //    value is written to disk only and never logged or returned.
      const manifest = {
        schema_version: SCHEMA_VERSION,
        generation_id: generationId,
        state: 'ready',
        database: DATABASE_NAME,
        identity: {
          namespace: IDENTITY_NAMESPACE,
          value: identityAfter,
        },
      };
      try {
        writeFileSync(stagingManifest, JSON.stringify(manifest, null, 2), 'utf8');
      } catch {
        discardStaging();
        return fail(CODES.MANIFEST_FAILED);
      }

      // 8. Atomic publish: rename the complete staging directory into place.
      try {
        mkdirSync(generationsDirectory, { recursive: true });
        renameSync(stagingDirectory, generationDirectory);
      } catch {
        discardStaging();
        logDiagnostic('publish_failed');
        return fail(CODES.PUBLISH_FAILED);
      }

      traceStage('generation_ready', generationId);

      return { ok: true, generation_id: generationId, status: 'ready' };
    });
  }

  async function cleanup(generationId) {
    return withLock(async () => {
      const id = normalizeGenerationId(generationId);
      if (id === null) {
        return fail(CODES.GENERATION_NOT_FOUND);
      }
      const directory = join(generationsDirectory, id);
      try {
        if (!existsSync(directory)) {
          return fail(CODES.GENERATION_NOT_FOUND);
        }
        rmSync(directory, { recursive: true, force: true });
        return { ok: true, status: 'cleaned' };
      } catch {
        return fail(CODES.CLEANUP_FAILED);
      }
    });
  }

  async function recover() {
    traceStage('recover_queued');
    return withLock(async () => {
      traceStage('recover_entered');
      const slate = cleanSlate();
      if (!slate.ok) {
        traceStage('recover_failed');
        return fail(CODES.RECOVER_FAILED);
      }
      traceStage('recover_finished');
      return { ok: true, status: 'recovered' };
    });
  }

  return { acquire, cleanup, recover };
}

export function registerEchoSnapshotApi(runtimeCore, options = {}) {
  const api = createEchoSnapshotApi(runtimeCore, options);
  if (runtimeCore && typeof runtimeCore === 'object') {
    if (!runtimeCore.apis || typeof runtimeCore.apis !== 'object') {
      runtimeCore.apis = {};
    }
    runtimeCore.apis.EchoSnapshotApi = api;
  }
  return api;
}
