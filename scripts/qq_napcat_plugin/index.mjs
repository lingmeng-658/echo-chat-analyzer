import {registerEchoSnapshotApi} from './snapshot/snapshot.mjs';
import {startBridge} from './bridge.mjs';

let snapshot;
let bridge;

// Candidate-only: fixed Echo bridge, no automatic acquisition or QCE imports.
export async function plugin_init(ctx) {
  if (!ctx?.core?.apis) throw new Error('echo_core_unavailable');
  snapshot = registerEchoSnapshotApi(ctx.core);
  bridge = await startBridge(ctx.core, snapshot, {port: Number(process.env.ECHO_BRIDGE_PORT ?? 40655)});
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
