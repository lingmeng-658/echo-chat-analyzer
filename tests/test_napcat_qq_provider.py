"""Fictional NapCat core over the real Echo HTTP bridge; no QQ/account state."""
import importlib
import http.client
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts/qq_napcat_plugin/bridge.mjs"


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    assert BRIDGE.is_file(), "Echo bridge missing"
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for real bridge transport contract")
    directory = tmp_path_factory.mktemp("echo-bridge")
    shutil.copy2(BRIDGE, directory / "bridge.mjs")
    (directory / "server.mjs").write_text("""
import {startBridge} from './bridge.mjs';
const core={dbPassphrase:'PRIVATE',selfInfo:{uin:'12345678',uid:'u_self',nick:'Self',online:true,secret:'PRIVATE'},apis:{
 DatabaseApi:{hasPassphrase:()=>true,decryptDatabase(){}},
 FriendApi:{getBuddyV2ExWithCate:async()=>[{buddyList:[{uin:'23456789',uid:'u_friend',coreInfo:{uin:'23456789',uid:'u_friend',nick:'Nick',remark:'Remark',secret:'PRIVATE'},secret:'PRIVATE'},{uid:'u_only'},{uin:'34567890'}]}]},
 GroupApi:{getGroups:async()=>[{groupCode:'45678901',groupName:'Group',memberCount:3},{groupCode:'56789012'}],getGroupMemberAll:async()=>({result:{infos:new Map([['u_member',{uid:'u_member',uin:'23456789',nick:'Nick',cardName:'Card',secret:'PRIVATE'}]])}})}
}};
let calls=0;
const snapshot={acquire:async()=>({ok:true,status:'ready',generation_id:'test-generation'}),cleanup:async()=>({ok:true,status:'cleaned'}),recover:async()=>({ok:true,status:'recovered'})};
if(process.argv[2]==='offline'){core.selfInfo={online:false};core.apis.DatabaseApi={};}
if(process.argv[2]==='empty'){core.apis.FriendApi.getBuddyV2ExWithCate=async()=>[];core.apis.GroupApi.getGroups=async()=>[];}
if(process.argv[2]==='failure'){core.apis.FriendApi.getBuddyV2ExWithCate=async()=>{throw Error('PRIVATE passphrase token path')};}
const bridge=await startBridge(core,snapshot,{port:0});
console.log(JSON.stringify({port:bridge.port}));
process.stdin.resume();process.stdin.on('end',async()=>{await bridge.stop();});
""", encoding="utf-8")
    processes = []

    def start(mode="ready"):
        process = subprocess.Popen([node, str(directory / "server.mjs"), mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        processes.append(process)
        return "http://127.0.0.1:" + str(json.loads(process.stdout.readline())["port"])

    yield start
    for process in processes:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        assert process.returncode == 0, process.stderr.read()


def provider(base):
    module = importlib.import_module("qq_chat_analyzer.providers.napcat_qq_provider")
    return module.NapCatQQProvider(base)


def request(base, method="Core.status", params=None, *, raw=None, headers=None):
    body = raw if raw is not None else json.dumps({"method":method,"params":params or []}).encode()
    req = urllib.request.Request(base+"/rpc",data=body,headers={"Content-Type":"application/json",**(headers or {})})
    try:
        with urllib.request.urlopen(req,timeout=5) as response:
            return response.status,json.load(response)
    except urllib.error.HTTPError as error:
        return error.code,json.load(error)


def test_status_readiness_and_no_passphrase(runtime):
    base=runtime()
    status=provider(base).status()
    assert status.bridge_ready and status.qq_online and status.database_api_ready and status.passphrase_ready
    assert status.self_info == {"uin":"12345678","uid":"u_self","nickname":"Self"}
    assert status.snapshot_api_ready and status.ready
    assert "PRIVATE" not in json.dumps(request(base)[1])
    offline=provider(runtime("offline")).status()
    assert offline.bridge_ready and not offline.qq_online and not offline.passphrase_ready and not offline.ready


def test_friends_identity_names_and_missing_field_fallback(runtime):
    friends=provider(runtime()).list_friends()
    assert [(f.uid,f.uin,f.nickname,f.remark,f.display_name) for f in friends] == [
        ("u_friend","23456789","Nick","Remark","Remark"),("u_only","","","","u_only"),("","34567890","","","34567890")]
    assert provider(runtime("empty")).list_friends() == []


def test_groups_mapping_and_empty(runtime):
    groups=provider(runtime()).list_groups()
    assert [(g.group_code,g.group_name,g.member_count) for g in groups] == [("45678901","Group",3),("56789012","",None)]
    assert provider(runtime("empty")).list_groups() == []


def test_members_map_identity_and_existing_snapshot_contract(runtime,tmp_path):
    qq=provider(runtime())
    client=qq.snapshot_client(tmp_path)
    assert qq.get_group_member_all("45678901") == client.get_group_member_all("45678901")
    member=client.get_group_member_all("45678901")["result"]["infos"]["u_member"]
    assert member == {"uid":"u_member","uin":"23456789","nick":"Nick","cardName":"Card"}
    client.recover()
    generation=client.acquire()
    assert generation == "test-generation"
    client.cleanup(generation)
    client.recover()


@pytest.mark.parametrize("method,params",[("DatabaseApi.decryptDatabase",[]),("__proto__.pollute",[]),("Core.status",[1]),("EchoSnapshotApi.cleanup",["../outside"]),("GroupApi.getGroupMemberAll",["u_uid"]),("EchoMetadata.listFriends",[1])])
def test_fixed_dispatch_and_parameter_rejection(runtime,method,params):
    code,value=request(runtime(),method,params)
    assert code == 400 and value["ok"] is False
    assert "PRIVATE" not in json.dumps(value)


def test_http_boundary_and_safe_errors(runtime):
    base=runtime()
    assert request(base,raw=b"{")[0] == 400
    assert request(base,raw=b"x"*4097)[0] == 413
    assert request(base,headers={"Origin":"https://outside.example"})[0] == 403
    assert request(base,headers={"Host":"outside.example"})[0] == 403
    assert request(base,raw=b'{"method":"Core.status","params":null}')[0] == 400
    assert request(base,headers={"Content-Type":"text/plain"})[0] == 415
    value=request(runtime("failure"),"EchoMetadata.listFriends")[1]
    assert value == {"ok":False,"error":"qq_runtime_operation_failed"}
    module=importlib.import_module("qq_chat_analyzer.providers.napcat_qq_provider")
    with pytest.raises(module.NapCatQQError) as error:
        provider(runtime("failure")).list_friends()
    assert "PRIVATE" not in str(error.value)


def test_streamed_body_limit_and_http_route(runtime):
    base=runtime()
    parsed=urllib.parse.urlsplit(base)
    connection=http.client.HTTPConnection(parsed.hostname,parsed.port,timeout=5)
    connection.request('POST','/rpc',body=iter([b'x'*2000,b'x'*3000]),headers={'Content-Type':'application/json'},encode_chunked=True)
    response=connection.getresponse()
    assert response.status == 413
    assert json.loads(response.read()) == {'ok':False,'error':'request_too_large'}
    connection.close()
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(base+'/rpc',timeout=5)
    assert error.value.code == 404
    error.value.close()


def test_single_fetch_and_invalid_response_errors():
    module=importlib.import_module("qq_chat_analyzer.providers.napcat_qq_provider")
    calls=[]
    def transport(url,body,timeout):
        calls.append(json.loads(body))
        return 200,json.dumps({"ok":True,"result":[]})
    client=module.NapCatQQProvider(transport=transport)
    assert client.list_friends() == [] and client.list_groups() == []
    assert [c['method'] for c in calls] == ['EchoMetadata.listFriends','EchoMetadata.listGroups']
    for body in ['PRIVATE',json.dumps({'ok':False,'error':'PRIVATE'}),json.dumps({'ok':True,'result':{}})]:
        client=module.NapCatQQProvider(transport=lambda *args:(200,body))
        with pytest.raises(module.NapCatQQError) as error: client.list_friends()
        assert 'PRIVATE' not in str(error.value)


def test_snapshot_transport_errors_keep_existing_error_family(tmp_path):
    module=importlib.import_module("qq_chat_analyzer.providers.napcat_qq_provider")
    from qq_chat_analyzer.providers.qq_direct_snapshot_runtime import QQSnapshotRuntimeUnavailable
    def failing(*args): raise module.NapCatQQError()
    client=module.NapCatQQProvider(transport=failing).snapshot_client(tmp_path)
    with pytest.raises(QQSnapshotRuntimeUnavailable): client.acquire()


@pytest.mark.parametrize("url",["http://127.0.0.1.evil.example:40655","https://127.0.0.1:40655","http://user:secret@127.0.0.1:40655","http://192.168.1.1:40655","http://127.0.0.1:40655/path","http://localhost:40655?x=1"])
def test_provider_rejects_non_loopback_or_ambiguous_urls(url):
    module=importlib.import_module("qq_chat_analyzer.providers.napcat_qq_provider")
    with pytest.raises(module.NapCatQQError):
        module.NapCatQQProvider(url)


def test_bridge_cannot_bind_external_address(tmp_path):
    assert BRIDGE.is_file()
    node=shutil.which("node")
    if not node: pytest.skip("Node unavailable")
    script=f"import {{startBridge}} from {json.dumps(BRIDGE.as_uri())}; try {{ await startBridge({{apis:{{}}}},{{}},{{host:'0.0.0.0',port:0}}); process.exit(1); }} catch {{ process.exit(0); }}"
    result=subprocess.run([node,"--input-type=module","-e",script],capture_output=True,timeout=10)
    assert result.returncode == 0
