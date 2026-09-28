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
// Privacy contract: status objects and any log lines may only carry stable
// error codes and the opaque generation id.  The identity value (QQ UIN),
// nicknames, message text, the passphrase and absolute paths never appear in
// a status object, a log line or an exception message.
import { existsSync, mkdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
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
    while (now() < deadline) {
      const api = core?.apis?.DatabaseApi;
      if (api && typeof api.hasPassphrase === 'function') {
        databaseApiSeen = true;
        try {
          if (api.hasPassphrase() === true) {
            return api;
          }
        } catch {
          // Transient read failure; retry within the bounded window.
        }
      }
      await sleep(pollIntervalMs);
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
    return withLock(async () => {
      // 1. Fail-closed cleanup: no decryption may start unless every previous
      //    generation, staging dir and legacy plaintext artifact is gone.
      const slate = cleanSlate();
      if (!slate.ok) {
        return fail(CODES.CLEANUP_FAILED);
      }

      // 2. Bounded wait for the in-process DatabaseApi and its passphrase.
      const databaseApi = await waitForDatabaseApi();
      if (!databaseApi) {
        logDiagnostic(
          databaseApiSeen ? 'passphrase_not_ready' : 'database_api_not_ready',
        );
        return fail(CODES.PASSHRASE_UNAVAILABLE);
      }

      // 3. Bounded wait for a canonical self identity *before* decryption.
      const identityBefore = await waitForIdentity();
      if (identityBefore === null) {
        logDiagnostic('identity_not_ready');
        return fail(CODES.IDENTITY_MISSING);
      }

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
      try {
        decrypted = Boolean(
          await databaseApi.decryptDatabase(SOURCE_DATABASE_NAME, stagingDatabase),
        );
      } catch {
        decrypted = false;
      }
      if (!decrypted || !existsSync(stagingDatabase)) {
        discardStaging();
        logDiagnostic('decrypt_failed');
        return fail(CODES.DECRYPT_FAILED);
      }

      // 5. The canonical self identity must still exist and be unchanged.
      const identityAfter = canonicalizeUin(core?.selfInfo?.uin);
      if (identityAfter === null) {
        discardStaging();
        return fail(CODES.IDENTITY_MISSING);
      }
      if (identityAfter !== identityBefore) {
        discardStaging();
        return fail(CODES.IDENTITY_CHANGED);
      }

      // 6. Manifest and database belong to the same generation.  The identity
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

      // 7. Atomic publish: rename the complete staging directory into place.
      try {
        mkdirSync(generationsDirectory, { recursive: true });
        renameSync(stagingDirectory, generationDirectory);
      } catch {
        discardStaging();
        logDiagnostic('publish_failed');
        return fail(CODES.PUBLISH_FAILED);
      }

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
    return withLock(async () => {
      const slate = cleanSlate();
      if (!slate.ok) {
        return fail(CODES.RECOVER_FAILED);
      }
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
