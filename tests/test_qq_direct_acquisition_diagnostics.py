"""Anonymous formal acquisition diagnostics, using fictional sources only."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_qq_direct_main_wal_acquisition import fictional_source, _formal
from test_qq_direct_main_wal_poc import fictional_source as poc_source, _interleave

pytestmark = pytest.mark.slow_integration


def diagnose(source, action="", *, setup="", phase="main_baseline_read"):
    def driver(program):
        program = _formal(program)
        program = program.replace("const api=createEchoSnapshotApi", """
  const diagnosticLog=path.join(path.dirname(outputPath),'diagnostics.log');
  process.env.QCE_LOG_FILE=diagnosticLog;
  SETUP
  const api=createEchoSnapshotApi""".replace("SETUP", setup))
        return program.replace("result.recovered=recovered.ok;", """
  result.recovered=recovered.ok;
  result.diagnosticLog=fs.readFileSync(diagnosticLog,'utf8');
""")
    return _interleave(source, action, phase=phase, driver_transform=driver)


@pytest.mark.parametrize("action,setup,stage,guard", [
    ("", "core.apis.DatabaseApi.getNtDbDir=()=>null;", "source_location", "source_unavailable"),
    ("", "core.apis.DatabaseApi.getNtDbDir=()=>root;", "workspace_isolation", "workspace_invalid"),
    ("", "fs.unlinkSync(mainPath+'-shm');", "shm_witness", "checkpoint_witness_missing"),
    ("const b=fs.readFileSync(mainPath); b[0]^=1; fs.writeFileSync(mainPath,b);", "", "main_identity", "main_format_unsupported"),
    ("const b=fs.readFileSync(walPath); b[40]^=1; fs.writeFileSync(walPath,b);", "", "wal_prefix", "wal_frame_salt_invalid"),
    ("", "const b=fs.readFileSync(mainPath+'-shm'); b.writeUInt32LE(b.readUInt32LE(20)+1,20); updateIndex(b);", "commit_boundary", "wal_index_boundary_mismatch"),
    ("const b=fs.readFileSync(walPath); fs.renameSync(walPath,walPath+'.old'); fs.writeFileSync(walPath,b);", "", "wal_identity", "wal_replaced"),
    ("const b=fs.readFileSync(walPath); b[16]^=1; fs.writeFileSync(walPath,b);", "", "wal_header", "wal_header_checksum_invalid"),
    ("const b=fs.readFileSync(walPath); b[60]^=1; fs.writeFileSync(walPath,b);", "", "wal_checksum", "wal_frame_checksum_invalid"),
    ("const b=fs.readFileSync(mainPath); b[1100]^=1; fs.writeFileSync(mainPath,b);", "", "main_stability", "main_changed_during_read"),
    ("const b=fs.readFileSync(mainPath+'-shm'); b.writeUInt32LE(1,128); fs.writeFileSync(mainPath+'-shm',b);", "", "checkpoint_witness", "checkpoint_state_changed"),
])
def test_specific_guard_logged_without_changing_public_error(fictional_source, action, setup, stage, guard):
    result = diagnose(fictional_source, action, setup=setup)
    assert result["code"] == "snapshot_unstable"
    assert result["decryptCalls"] == 0
    assert f"failure_stage={stage} guard_code={guard}" in result["diagnosticLog"]
    assert "failure_stage" not in result and "guard_code" not in result


def test_wal_generation_reset_during_main_baseline_fails_closed(fictional_source):
    def driver(program):
        program = _formal(program).replace('const api=createEchoSnapshotApi', """
  const diagnosticLog=path.join(path.dirname(outputPath),'diagnostics.log');
  process.env.QCE_LOG_FILE=diagnosticLog;
  const initialBoundary=fs.readFileSync(mainPath+'-shm').readUInt32LE(16);
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync, originalRead=mutableFs.readSync, originalClose=mutableFs.closeSync;
  const activeFds=new Set(), mainFds=new Set();
  let resetDuringBaseline=false, oldFramesPreserved=false, headerChecksumValid=false, mergedOpened=false;
  mutableFs.openSync=(p,...args)=>{const fd=originalOpen(p,...args);
    activeFds.add(fd);
    if(String(p)===mainPath) mainFds.add(fd);
    if(path.basename(String(p))==='merged.db') mergedOpened=true;
    return fd;};
  mutableFs.readSync=(fd,buffer,at,length,position)=>{
    const count=originalRead(fd,buffer,at,length,position);
    // The main content baseline is read after B was fixed, before WAL scanning.
    if(!resetDuringBaseline && mainFds.has(fd) && position===0 && length>1024) {
      resetDuringBaseline=true;
      const wal=fs.readFileSync(walPath), oldFrames=Buffer.from(wal.subarray(32));
      // A reset publishes a new header generation while old physical frame
      // slots remain. Keep the header checksum valid so salt is the rejecting guard.
      wal.writeUInt32BE((wal.readUInt32BE(12)+1)>>>0,12);
      wal[16]^=1;
      const sum=checksum(wal.subarray(0,24),wal.readUInt32BE(0)===0x377f0682);
      wal.writeUInt32BE(sum[0],24); wal.writeUInt32BE(sum[1],28);
      fs.writeFileSync(walPath,wal);
      const rewritten=fs.readFileSync(walPath);
      oldFramesPreserved=rewritten.subarray(32).equals(oldFrames);
      const verified=checksum(rewritten.subarray(0,24),rewritten.readUInt32BE(0)===0x377f0682);
      headerChecksumValid=verified[0]===rewritten.readUInt32BE(24) && verified[1]===rewritten.readUInt32BE(28);
    }
    return count;};
  mutableFs.closeSync=(fd)=>{originalClose(fd); activeFds.delete(fd); mainFds.delete(fd);};
  builtin.syncBuiltinESMExports();
  const api=createEchoSnapshotApi""")
        return program.replace('result.recovered=recovered.ok;', """
  result.recovered=recovered.ok;
  result.diagnosticLog=fs.readFileSync(diagnosticLog,'utf8');
  result.initialBoundary=initialBoundary;
  result.resetDuringBaseline=resetDuringBaseline;
  result.oldFramesPreserved=oldFramesPreserved;
  result.headerChecksumValid=headerChecksumValid;
  result.mergedOpened=mergedOpened;
  result.publishedGenerationCount=fs.existsSync(path.join(root,'generations'))
    ? fs.readdirSync(path.join(root,'generations')).length : 0;
  result.workspaceDatabaseCount=fs.readdirSync(root,{recursive:true})
    .filter(name=>/\\.db(?:-wal|-shm|-journal)?$/.test(name)).length;
  result.activeFdCount=activeFds.size;
""")
    result = _interleave(fictional_source, '', driver_transform=driver)
    assert result['initialBoundary'] > 0
    assert f"capture_stage=shm_witness boundary={result['initialBoundary']}" in result['diagnosticLog']
    assert result['resetDuringBaseline'] and result['oldFramesPreserved'] and result['headerChecksumValid']
    assert not result['ok'] and result['code'] == 'snapshot_unstable'
    assert 'failure_stage=wal_prefix guard_code=wal_frame_salt_invalid' in result['diagnosticLog']
    assert result['decryptCalls'] == 0 and not result['mergedOpened']
    assert result['manifest'] is None and result['publishedGenerationCount'] == 0
    assert result['stagingCleaned'] and result['recovered']
    assert result['workspaceDatabaseCount'] == 0 and result['activeFdCount'] == 0
    assert not fictional_source[2].exists()


def test_unknown_error_and_private_fields_never_reach_log(fictional_source):
    result = diagnose(fictional_source, setup="""
  core.apis.DatabaseApi.getNtDbDir=()=>{const e=new Error('PRIVATE_TEXT path UIN key salt payload');
  e.code='PRIVATE_CODE'; e.boundary='PRIVATE_BOUNDARY'; e.sourceHash='PRIVATE_HASH'; throw e;};
""")
    log = result["diagnosticLog"]
    assert "failure_stage=source_location guard_code=unexpected_error" in log
    for private in ("PRIVATE", "10086", str(fictional_source[0]), "fictional-local-passphrase"):
        assert private not in log


@pytest.mark.parametrize('expression', ['null', 'undefined', "'PRIVATE_TEXT'", "{get code(){throw new Error('PRIVATE_TEXT')}}"])
def test_nonstandard_thrown_values_are_anonymous(fictional_source, expression):
    result = diagnose(fictional_source, setup=f"core.apis.DatabaseApi.getNtDbDir=()=>{{throw {expression};}};")
    assert result['code'] == 'snapshot_unstable'
    assert 'failure_stage=source_location guard_code=unexpected_error' in result['diagnosticLog']
    assert 'PRIVATE_TEXT' not in result['diagnosticLog']


def test_loaded_hashes_and_only_anonymous_witness_fields(fictional_source):
    result = diagnose(fictional_source)
    log = result["diagnosticLog"]
    root = Path(__file__).parents[1] / "scripts/qq_direct_db_snapshot"
    for name, field in (("snapshot.mjs", "snapshot_code_hash"), ("main_wal.mjs", "capture_code_hash"), ("workspace.mjs", "workspace_code_hash")):
        assert f"{field}={hashlib.sha256((root / name).read_bytes()).hexdigest()}" in log
    assert "boundary=" in log and "nBackfill=0" in log and "attempted=0" in log
    for private in (str(fictional_source[0]), "10086", "fictional-local-passphrase", "sourceHash=", "salt="):
        assert private not in log


@pytest.mark.parametrize('changed,offset', [
    ('wal_index_headers_stable', 0), ('nbackfill_stable', 96),
    ('attempted_stable', 128), ('shm_identity_stable', None),
])
def test_shm_reread_reports_each_anonymous_condition(fictional_source, changed, offset):
    setup = """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalRead=mutableFs.readSync;
  let witnessReads=0;
"""
    if offset is None:
        setup += """
  mutableFs.readSync=(fd,buffer,at,length,position)=>{
    const count=originalRead(fd,buffer,at,length,position);
    if(length===136 && position===0 && ++witnessReads===2) {
      const p=mainPath+'-shm', bytes=fs.readFileSync(p);
      fs.renameSync(p,p+'.retired'); fs.writeFileSync(p,bytes);
    }
    return count;
  };
"""
    else:
        setup += f"""
  mutableFs.readSync=(fd,buffer,at,length,position)=>{{
    const count=originalRead(fd,buffer,at,length,position);
    if(length===136 && position===0 && ++witnessReads===2) buffer[{offset}]^=1;
    return count;
  }};
"""
    setup += "builtin.syncBuiltinESMExports();"
    result = diagnose(fictional_source, setup=setup)
    assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    failure = next(line for line in result['diagnosticLog'].splitlines()
                   if 'failure_stage=shm_witness guard_code=checkpoint_witness_torn' in line)
    for name in ('wal_index_headers_stable', 'nbackfill_stable', 'attempted_stable', 'shm_identity_stable'):
        assert f"{name}={'false' if name == changed else 'true'}" in failure
    assert 'headerCopiesMatch=true' in failure and 'boundary=' in failure
    assert 'nBackfill=0' in failure and 'attempted=0' in failure
    for private in (str(fictional_source[0]), '10086', 'fictional-local-passphrase', 'salt='):
        assert private not in result['diagnosticLog']


def test_shm_stable_reread_reports_all_four_true(fictional_source):
    result = diagnose(fictional_source)
    assert result['ok']
    for name in ('wal_index_headers_stable', 'nbackfill_stable', 'attempted_stable', 'shm_identity_stable'):
        assert f'{name}=true' in result['diagnosticLog']


@pytest.mark.parametrize('changed', ['dev', 'ino', None])
def test_shm_identity_components_and_runtime_versions_are_anonymous(fictional_source, changed):
    setup = """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync, originalFstat=mutableFs.fstatSync;
  const shmHandles=[];
  mutableFs.openSync=(p,...args)=>{const fd=originalOpen(p,...args);
    if(String(p)===mainPath+'-shm') shmHandles.push(fd);
    return fd;};
  mutableFs.fstatSync=(fd,...args)=>{const value=originalFstat(fd,...args);
    if(shmHandles.indexOf(fd)>0){
      const changed=CHANGED;
      if(changed) value[changed]+=1n;
    }
    return value;};
  builtin.syncBuiltinESMExports();
""".replace('CHANGED', json.dumps(changed))
    result = diagnose(fictional_source, setup=setup)
    assert result['ok'] is (changed is None)
    if changed is not None:
        assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
        line = next(line for line in result['diagnosticLog'].splitlines()
                    if 'failure_stage=shm_witness guard_code=checkpoint_witness_torn' in line)
    else:
        line = next(line for line in result['diagnosticLog'].splitlines()
                    if 'shm_identity_stable=true' in line)
    assert f"dev_equal={'false' if changed == 'dev' else 'true'}" in line
    assert f"ino_equal={'false' if changed == 'ino' else 'true'}" in line
    versions = json.loads(subprocess.check_output(
        ['node', '-p', 'JSON.stringify({node:process.version,uv:process.versions.uv})'], text=True))
    assert f"node_version={versions['node']}" in line
    assert f"libuv_version={versions['uv']}" in line
    for forbidden in (' dev=', ' ino=', 'fd_dev=', 'path_dev=', 'fd_ino=', 'path_ino='):
        assert forbidden not in result['diagnosticLog']
    assert 'dev_equal' not in result and 'ino_equal' not in result


def test_same_shm_file_survives_path_stat_dev_inconsistency(fictional_source):
    result = diagnose(fictional_source, setup="""
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalStat=mutableFs.statSync;
  mutableFs.statSync=(p,...args)=>{const value=originalStat(p,...args);
    return String(p)===mainPath+'-shm' ? {...value,dev:value.dev+1n} : value;};
  builtin.syncBuiltinESMExports();
""")
    assert result['ok'] and result['decryptCalls'] == 1
    assert 'dev_equal=true ino_equal=true' in result['diagnosticLog']
    assert 'guard_code=checkpoint_witness_torn' not in result['diagnosticLog']


@pytest.mark.parametrize('phase', ['main_baseline_read', 'output_complete'])
def test_formal_shm_replacement_with_identical_bytes_still_rejected(fictional_source, phase):
    result = diagnose(fictional_source,
                      "const p=mainPath+'-shm', b=fs.readFileSync(p); fs.renameSync(p,p+'.retired'); fs.writeFileSync(p,b);",
                      phase=phase)
    assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    assert 'failure_stage=checkpoint_witness guard_code=checkpoint_state_changed' in result['diagnosticLog']
    assert result['stagingCleaned'] and result['recovered']


@pytest.mark.parametrize('fail_probe', [False, True])
def test_shm_identity_probe_closes_both_fds(fictional_source, fail_probe):
    def driver(program):
        program = _formal(program).replace('const api=createEchoSnapshotApi', """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync, originalFstat=mutableFs.fstatSync, originalClose=mutableFs.closeSync;
  const activeShm=new Set(), probeFds=new Set();
  let probeCount=0;
  mutableFs.openSync=(p,flags,...args)=>{const fd=originalOpen(p,flags,...args);
    if(String(p)===mainPath+'-shm') {
      if(flags!=='r') throw new Error('SHM must be read-only');
      if(activeShm.size) {probeFds.add(fd); probeCount++;}
      activeShm.add(fd);
    }
    return fd;};
  mutableFs.fstatSync=(fd,...args)=>{
    if(FAIL_PROBE && probeFds.has(fd)) {const error=new Error('fictional probe failure'); error.code='EIO'; throw error;}
    return originalFstat(fd,...args);};
  mutableFs.closeSync=(fd)=>{originalClose(fd); activeShm.delete(fd); probeFds.delete(fd);};
  builtin.syncBuiltinESMExports();
  const api=createEchoSnapshotApi""".replace('FAIL_PROBE', str(fail_probe).lower()))
        return program.replace('result.recovered=recovered.ok;', """
  result.recovered=recovered.ok;
  result.activeShmCount=activeShm.size;
  result.probeCount=probeCount;
""")
    result = _interleave(fictional_source, '', driver_transform=driver)
    assert result['ok'] is (not fail_probe)
    assert result['probeCount'] > 0 and result['activeShmCount'] == 0
    if fail_probe:
        assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    assert result['stagingCleaned'] and result['recovered']


def test_same_main_file_survives_path_stat_dev_inconsistency(fictional_source):
    result = diagnose(fictional_source, setup="""
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalStat=mutableFs.statSync;
  mutableFs.statSync=(p,...args)=>{const value=originalStat(p,...args);
    return String(p)===mainPath ? {...value,dev:value.dev+1n} : value;};
  builtin.syncBuiltinESMExports();
""")
    assert result['ok'] and result['decryptCalls'] == 1
    assert result['stagingCleaned'] and result['recovered']


@pytest.mark.parametrize('phase', ['initial_open', 'main_baseline_read', 'output_complete'])
def test_formal_main_replacement_with_identical_bytes_still_rejected(fictional_source, phase):
    action = "const b=fs.readFileSync(mainPath); fs.renameSync(mainPath,mainPath+'.retired'); fs.writeFileSync(mainPath,b);"
    setup = ""
    if phase == 'initial_open':
        setup = """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync;
  let replaced=false;
  mutableFs.openSync=(p,...args)=>{const fd=originalOpen(p,...args);
    if(String(p)===mainPath && !replaced) {replaced=true; ACTION}
    return fd;};
  builtin.syncBuiltinESMExports();
""".replace('ACTION', action)
        action = ""
    result = diagnose(fictional_source, action, setup=setup, phase=phase)
    guard = 'main_replaced' if phase == 'initial_open' else 'main_changed_during_read'
    assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    assert f'guard_code={guard}' in result['diagnosticLog']
    assert result['stagingCleaned'] and result['recovered']


@pytest.mark.parametrize('changed', ['dev', 'ino'])
@pytest.mark.parametrize('probe_number', [1, 2])
def test_main_probe_keeps_both_identity_components(fictional_source, changed, probe_number):
    setup = """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync, originalFstat=mutableFs.fstatSync, originalClose=mutableFs.closeSync;
  const activeMain=new Set(), probeFds=new Set();
  let probes=0;
  mutableFs.openSync=(p,...args)=>{const fd=originalOpen(p,...args);
    if(String(p)===mainPath) {
      if(activeMain.size && ++probes===PROBE_NUMBER) probeFds.add(fd);
      activeMain.add(fd);
    }
    return fd;};
  mutableFs.fstatSync=(fd,...args)=>{const value=originalFstat(fd,...args);
    if(probeFds.has(fd)) value[CHANGED]+=1n;
    return value;};
  mutableFs.closeSync=(fd)=>{originalClose(fd); activeMain.delete(fd); probeFds.delete(fd);};
  builtin.syncBuiltinESMExports();
""".replace('CHANGED', json.dumps(changed)).replace('PROBE_NUMBER', str(probe_number))
    result = diagnose(fictional_source, setup=setup)
    guard = 'main_replaced' if probe_number == 1 else 'main_changed_during_read'
    assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    assert f'guard_code={guard}' in result['diagnosticLog']
    assert result['stagingCleaned'] and result['recovered']


@pytest.mark.parametrize('fail_probe_number', [None, 1, 2])
def test_main_identity_probe_closes_both_fds(fictional_source, fail_probe_number):
    def driver(program):
        program = _formal(program).replace('const api=createEchoSnapshotApi', """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync, originalFstat=mutableFs.fstatSync, originalClose=mutableFs.closeSync;
  const activeMain=new Set(), probeFds=new Map();
  let probeCount=0;
  mutableFs.openSync=(p,flags,...args)=>{const fd=originalOpen(p,flags,...args);
    if(String(p)===mainPath) {
      if(flags!=='r') throw new Error('main must be read-only');
      if(activeMain.size) probeFds.set(fd,++probeCount);
      activeMain.add(fd);
    }
    return fd;};
  mutableFs.fstatSync=(fd,...args)=>{
    if(probeFds.has(fd)) {
      if(args[0]?.bigint!==true) throw new Error('identity must use bigint');
      if(probeFds.get(fd)===FAIL_PROBE_NUMBER) {const error=new Error('fictional probe failure'); error.code='EIO'; throw error;}
    }
    return originalFstat(fd,...args);};
  mutableFs.closeSync=(fd)=>{originalClose(fd); activeMain.delete(fd); probeFds.delete(fd);};
  builtin.syncBuiltinESMExports();
  const api=createEchoSnapshotApi""".replace('FAIL_PROBE_NUMBER', json.dumps(fail_probe_number)))
        return program.replace('result.recovered=recovered.ok;', """
  result.recovered=recovered.ok;
  result.activeMainCount=activeMain.size;
  result.probeCount=probeCount;
""")
    result = _interleave(fictional_source, '', driver_transform=driver)
    assert result['ok'] is (fail_probe_number is None)
    assert result['probeCount'] == (fail_probe_number or 2)
    assert result['activeMainCount'] == 0
    if fail_probe_number is not None:
        assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    assert result['stagingCleaned'] and result['recovered']


def test_same_wal_file_survives_path_stat_dev_inconsistency(fictional_source):
    result = diagnose(fictional_source, setup="""
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalStat=mutableFs.statSync;
  mutableFs.statSync=(p,...args)=>{const value=originalStat(p,...args);
    return String(p)===walPath ? {...value,dev:value.dev+1n} : value;};
  builtin.syncBuiltinESMExports();
""")
    assert result['ok'] and result['decryptCalls'] == 1
    assert result['stagingCleaned'] and result['recovered']


@pytest.mark.parametrize('phase', ['initial_open', 'main_baseline_read', 'boundary_selected', 'output_complete'])
def test_formal_wal_replacement_with_identical_bytes_still_rejected(fictional_source, phase):
    action = "const b=fs.readFileSync(walPath); fs.renameSync(walPath,walPath+'.retired'); fs.writeFileSync(walPath,b);"
    setup = ""
    if phase == 'initial_open':
        setup = """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync;
  let replaced=false;
  mutableFs.openSync=(p,...args)=>{const fd=originalOpen(p,...args);
    if(String(p)===walPath && !replaced) {replaced=true; ACTION}
    return fd;};
  builtin.syncBuiltinESMExports();
""".replace('ACTION', action)
        action = ""
    result = diagnose(fictional_source, action, setup=setup, phase=phase)
    guard = 'wal_replaced' if phase in ('initial_open', 'main_baseline_read') else 'wal_boundary_changed'
    assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    assert f'guard_code={guard}' in result['diagnosticLog']
    assert result['stagingCleaned'] and result['recovered']


@pytest.mark.parametrize('changed', ['dev', 'ino'])
@pytest.mark.parametrize('probe_open_number', [1, 4])
def test_wal_probe_keeps_both_identity_components(fictional_source, changed, probe_open_number):
    setup = """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync, originalFstat=mutableFs.fstatSync, originalClose=mutableFs.closeSync;
  const changedFds=new Set();
  let walOpens=0;
  mutableFs.openSync=(p,...args)=>{const fd=originalOpen(p,...args);
    if(String(p)===walPath && ++walOpens===PROBE_OPEN_NUMBER) changedFds.add(fd);
    return fd;};
  mutableFs.fstatSync=(fd,...args)=>{const value=originalFstat(fd,...args);
    if(changedFds.has(fd) && args[0]?.bigint===true) value[CHANGED]+=1n;
    return value;};
  mutableFs.closeSync=(fd)=>{originalClose(fd); changedFds.delete(fd);};
  builtin.syncBuiltinESMExports();
""".replace('CHANGED', json.dumps(changed)).replace('PROBE_OPEN_NUMBER', str(probe_open_number))
    result = diagnose(fictional_source, setup=setup)
    guard = 'wal_replaced' if probe_open_number == 1 else 'wal_boundary_changed'
    assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    assert f'guard_code={guard}' in result['diagnosticLog']
    assert result['stagingCleaned'] and result['recovered']


@pytest.mark.parametrize('fail_probe_open_number', [None, 1, 4])
def test_wal_identity_probe_closes_fds(fictional_source, fail_probe_open_number):
    def driver(program):
        program = _formal(program).replace('const api=createEchoSnapshotApi', """
  const builtin=await import('node:module');
  const mutableFs=builtin.createRequire(import.meta.url)('node:fs');
  const originalOpen=mutableFs.openSync, originalFstat=mutableFs.fstatSync, originalClose=mutableFs.closeSync;
  const activeWal=new Map();
  let walOpens=0, probeCount=0;
  mutableFs.openSync=(p,flags,...args)=>{const fd=originalOpen(p,flags,...args);
    if(String(p)===walPath) {
      if(flags!=='r') throw new Error('WAL must be read-only');
      activeWal.set(fd,++walOpens);
    }
    return fd;};
  mutableFs.fstatSync=(fd,...args)=>{
    const number=activeWal.get(fd);
    if(number===1 || number===4) {
      if(args[0]?.bigint!==true) throw new Error('identity must use bigint');
      probeCount++;
      if(number===FAIL_PROBE_OPEN_NUMBER) {const error=new Error('fictional probe failure'); error.code='EIO'; throw error;}
    }
    return originalFstat(fd,...args);};
  mutableFs.closeSync=(fd)=>{originalClose(fd); activeWal.delete(fd);};
  builtin.syncBuiltinESMExports();
  const api=createEchoSnapshotApi""".replace('FAIL_PROBE_OPEN_NUMBER', json.dumps(fail_probe_open_number)))
        return program.replace('result.recovered=recovered.ok;', """
  result.recovered=recovered.ok;
  result.activeWalCount=activeWal.size;
  result.probeCount=probeCount;
""")
    result = _interleave(fictional_source, '', driver_transform=driver)
    assert result['ok'] is (fail_probe_open_number is None)
    assert result['probeCount'] == (1 if fail_probe_open_number == 1 else 2)
    assert result['activeWalCount'] == 0
    if fail_probe_open_number is not None:
        assert result['code'] == 'snapshot_unstable' and result['decryptCalls'] == 0
    assert result['stagingCleaned'] and result['recovered']


def test_cleanup_failure_has_own_stage(fictional_source):
    result = diagnose(fictional_source, setup="""
  fs.mkdirSync(path.join(root,'staging'),{recursive:true});
  fs.writeFileSync(path.join(root,'staging','owner.json'),JSON.stringify({kind:'echo-qq-snapshot',version:1}));
  fs.writeFileSync(path.join(root,'staging','unknown-private-file'),'PRIVATE_CONTENT');
""")
    assert result['code'] == 'cleanup_failed'
    assert 'failure_stage=cleanup guard_code=workspace_invalid' in result['diagnosticLog']
    assert 'PRIVATE_CONTENT' not in result['diagnosticLog']


def test_lease_failure_has_own_stage(fictional_source):
    result = diagnose(fictional_source, setup="""
  fs.mkdirSync(root,{recursive:true});
  fs.mkdirSync(path.join(root,'lease.lock'));
""")
    assert result['code'] == 'cleanup_failed'
    assert 'failure_stage=lease guard_code=workspace_busy' in result['diagnosticLog']


def test_unwritable_diagnostics_cannot_change_acquisition(fictional_source):
    def driver(program):
        return _formal(program).replace('const api=createEchoSnapshotApi',
                                        'process.env.QCE_LOG_FILE=path.dirname(mainPath); const api=createEchoSnapshotApi')
    result = _interleave(fictional_source, '', driver_transform=driver)
    assert result['ok'] and result['stagingCleaned'] and result['recovered']


def test_hashes_describe_evaluated_modules_after_disk_change(tmp_path):
    modules = ['snapshot.mjs', 'main_wal.mjs', 'workspace.mjs']
    source = Path(__file__).parents[1] / 'scripts/qq_direct_db_snapshot'
    expected = {}
    for name in modules:
        shutil.copyfile(source / name, tmp_path / name)
        expected[name] = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    program = """
import * as fs from 'node:fs';
import {createEchoSnapshotApi} from './snapshot.mjs';
for(const name of ['snapshot.mjs','main_wal.mjs','workspace.mjs']) fs.appendFileSync(name,'\n// later disk revision\n');
process.env.QCE_LOG_FILE='diagnostics.log';
const api=createEchoSnapshotApi({selfInfo:{uin:'10086'},apis:{DatabaseApi:{hasPassphrase:()=>true,getNtDbDir:()=>null}}},{rootDirectory:'workspace'});
await api.acquire();
console.log(JSON.stringify(fs.readFileSync('diagnostics.log','utf8')));
""".replace("'\n// later disk revision\n'", "'\\n// later disk revision\\n'")
    completed = subprocess.run(['node', '--input-type=module', '-e', program], cwd=tmp_path,
                               capture_output=True, text=True, timeout=15, check=True)
    log = json.loads(completed.stdout)
    for name in modules:
        assert expected[name] in log
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() not in log
