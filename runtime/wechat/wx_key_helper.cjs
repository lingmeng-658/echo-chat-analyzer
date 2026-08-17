'use strict'

// Aligned with the verified verify_wx_key_print_once_20260807.cjs flow.
// Difference in contract: the 64-hex key is the ONLY thing written to stdout,
// because the Python caller reads stdout as the key. All diagnostics go to
// stderr, where WeChatKeyService maps them into a user-safe message.

const { execFileSync } = require('node:child_process')
const now = () => new Date().toISOString()
const log = (message) => process.stderr.write(`${now()} ${message}\n`)

log('helper_stage=node_start')
log('helper_stage=koffi_load')
const koffi = require('koffi')

const POLL_INTERVAL_MS = 200
const STATUS_INTERVAL_MS = 5000
const KEY_LENGTH = 64

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function arg(name, fallback) {
  const index = process.argv.indexOf(name)
  return index >= 0 ? process.argv[index + 1] : fallback
}

function pids() {
  const output = execFileSync(
    'powershell.exe',
    ['-NoProfile', '-Command', '(Get-Process -Name Weixin -ErrorAction SilentlyContinue).Id'],
    { encoding: 'utf8', windowsHide: true }
  )
  return output
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean)
    .map(Number)
    .filter(Number.isFinite)
}

function errorText(funcs) {
  try {
    return String(funcs.GetLastErrorMsg ? funcs.GetLastErrorMsg() : '(GetLastErrorMsg unavailable)')
  } catch (error) {
    return `GetLastErrorMsg unavailable: ${error}`
  }
}

function bind(lib) {
  const funcs = {
    initialize: lib.func('bool InitializeHook(uint32_t)'),
    poll: lib.func('bool PollKeyData(char*, int32_t)'),
    cleanup: lib.func('bool CleanupHook()'),
    GetLastErrorMsg: null,
    GetStatusMessage: null,
  }
  try {
    funcs.GetLastErrorMsg = lib.func('const char* GetLastErrorMsg()')
  } catch {
    log('GetLastErrorMsg: not exported (optional)')
  }
  try {
    funcs.GetStatusMessage = lib.func('bool GetStatusMessage(char*, int32_t, int32_t*)')
  } catch {
    log('GetStatusMessage: not exported (optional)')
  }
  return funcs
}

function printStatus(funcs, elapsedSeconds) {
  if (!funcs.GetStatusMessage) {
    log(`elapsed=${elapsedSeconds}s, waiting for key...`)
    return
  }
  try {
    const statusBuffer = Buffer.alloc(256)
    const levelBuffer = Buffer.alloc(4)
    const ok = funcs.GetStatusMessage(statusBuffer, 256, levelBuffer)
    const status = statusBuffer.toString('utf8').replace(/\0/g, '').trim()
    const level = levelBuffer.readInt32LE(0)
    log(`GetStatusMessage -> ${ok}, level=${level}, status=${JSON.stringify(status)}`)
  } catch (error) {
    log(`GetStatusMessage error: ${error}`)
  }
  log(`elapsed=${elapsedSeconds}s, waiting for key...`)
}

async function pollForKey(funcs, deadline) {
  const started = Date.now()
  let lastStatus = 0

  while (Date.now() < deadline) {
    const buffer = Buffer.alloc(65)
    let got = false
    try {
      got = Boolean(funcs.poll(buffer, 65))
    } catch (error) {
      log(`PollKeyData exception: ${error}`)
    }

    if (got) {
      const raw = buffer.toString('utf8').replace(/\0/g, '').trim()
      log(`PollKeyData -> true, key_len=${raw.length}`)
      if (raw.length >= KEY_LENGTH) {
        return raw.slice(0, KEY_LENGTH).toLowerCase()
      }
      log('PollKeyData returned non-key data; continuing')
    }

    if (Date.now() - lastStatus >= STATUS_INTERVAL_MS) {
      lastStatus = Date.now()
      printStatus(funcs, Math.round((Date.now() - started) / 1000))
    }

    await sleep(POLL_INTERVAL_MS)
  }

  log(`timeout after ${Math.round((Date.now() - started) / 1000)}s`)
  return null
}

async function main() {
  const dll = arg('--dll')
  const timeoutMs = Number(arg('--timeout-ms', '600000'))
  if (!dll) throw new Error('missing dll path')

  const pidArg = Number(arg('--pid', NaN))
  log('helper_stage=process_enumeration')
  const ids = Number.isFinite(pidArg) ? [pidArg] : pids()
  log(`process_found=${ids.length > 0}, process_count=${ids.length}`)

  log(`timeoutMs: ${timeoutMs}`)

  log('helper_stage=dll_load')
  const funcs = bind(koffi.load(dll))
  log('exports loaded: InitializeHook, PollKeyData, CleanupHook')

  if (!ids.length) throw new Error('no Weixin process')

  const deadline = Date.now() + timeoutMs
  for (const [index, pid] of ids.entries()) {
    const remainingPids = ids.length - index
    const pidDeadline = Date.now() + Math.max(0, Math.floor((deadline - Date.now()) / remainingPids))
    let hooked = false
    try {
      hooked = Boolean(funcs.initialize(pid))
    } catch (error) {
      log(`InitializeHook exception: ${error}`)
    }
    log(`hook_success=${hooked}`)

    if (!hooked) {
      log(`InitializeHook error: ${errorText(funcs)}`)
      continue
    }

    let key = null
    try {
      key = await pollForKey(funcs, pidDeadline)
    } finally {
      try {
        log(`CleanupHook() -> ${funcs.cleanup()}`)
      } catch (error) {
        log(`CleanupHook error: ${error}`)
      }
    }

    if (key) {
      process.stdout.write(key + '\n')
      return
    }
  }

  throw new Error('key unavailable')
}

main().catch((error) => {
  process.stderr.write(`${error.message || 'key acquisition failed'}\n`)
  process.exitCode = 1
})
