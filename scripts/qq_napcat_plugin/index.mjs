import {registerEchoSnapshotApi} from './snapshot/snapshot.mjs';
import {startBridge} from './bridge.mjs';
import {isAbsolute} from 'node:path';

let snapshot;
let bridge;

// Candidate-only: fixed Echo bridge, no automatic acquisition or QCE imports.
export async function plugin_init(ctx) {
  if (!ctx?.core?.apis) throw new Error('echo_core_unavailable');
  const rootDirectory = process.env.ECHO_SNAPSHOT_ROOT;
  if (typeof rootDirectory !== 'string' || !isAbsolute(rootDirectory) || rootDirectory.includes('\0')) {
    throw new Error('echo_snapshot_root_missing');
  }
  snapshot = registerEchoSnapshotApi(ctx.core, {rootDirectory});
  bridge = await startBridge(ctx.core, snapshot, {
    port: Number(process.env.ECHO_BRIDGE_PORT ?? 40655),
    runtimeId: process.env.ECHO_RUNTIME_ID ?? null,
  });
  ctx.logger?.info?.('Echo snapshot plugin initialized');
}

export async function plugin_cleanup() {
  if (bridge) await bridge.stop();
  bridge = undefined;
  if (!snapshot) return;
  const result = await snapshot.recover();
  if (!result.ok) throw new Error('echo_snapshot_recovery_failed');
  snapshot = undefined;
}
