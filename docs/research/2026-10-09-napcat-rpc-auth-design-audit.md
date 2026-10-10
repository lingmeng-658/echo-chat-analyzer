# NapCat 本地 RPC 最小客户端认证 —— 第一轮设计审计报告

- 仓库：`lingmeng-658/echo-chat-analyzer`
- 工作树：`D:/ChatAnalyzerWorkspace/wt-napcat-rpc-auth`
- 分支：`security/napcat-rpc-auth`（HEAD `b5413dd`，与 `origin/main` 一致，working tree 干净）
- 轮次：**仅审计 + 设计**，未修改任何代码、未创建 commit
- 日期：2026-10-09

---

## 0. 结论摘要

1. 缺口确认成立。`bridge.mjs` 的所有 RPC 方法目前**只靠 Host/Origin/Content-Type/大小/方法白名单/runtime_id 路径绑定**防护，任何本机进程（含**其他 Windows 用户账户**，loopback 不受用户隔离保护）都能无凭证调用 `EchoMetadata.listFriends` / `listGroups` / `GroupApi.getGroupMemberAll` 拉取社交元数据，并能先通过 `Core.status` 拿到 `runtime_id`，再调用 `EchoSnapshotApi.acquire` 触发 QQ 库解密落盘、`recover` 触发对既有 generation 的破坏性清理。
2. `runtime_id` 不能作为凭证：它是 `sha256(program_root|work_root|snapshot_root)`（`qq_runtime_paths.py:30-35`），**明文出现在 `Core.status` 响应里**（`bridge.mjs:24`），只表达“实例路径契约”，不表达“调用者被授权”。
3. 最小可行方案：**Echo 拥有完整启动链路**（`default_auth_window_launcher` → `_launch_auth_window`，managed 与 custom 都走同一条路径），因此可以在启动瞬间用 `secrets.token_hex(32)` 生成高熵凭证，通过已有的 `ECHO_*` 环境变量通道注入 NapCat，Python 侧在同一进程内保存于内存注册表；`bridge.mjs` 对所有 RPC 方法统一强制校验，凭证缺失/不符一律 `401 invalid_credential` 且**不进入任何方法分发**；插件在 `ECHO_BRIDGE_TOKEN` 缺失或非法时**拒绝启动 bridge**（fail closed，不提供无认证监听）。
4. 撤销 plaintext 清理的能力**不依赖 HTTP 凭证**：`acquire` 第 1 步、`EchoSnapshotApi.recover`、`plugin_cleanup` 三条路径最终都走同一个进程内 `workspace.recover()`（`snapshot.mjs:431-442 / 625-638`、`workspace.mjs:111-126`）。应用侧 `facade.shutdown()` 也保证“先 RPC recover，再终止 runtime”（`facade.py:1148-1178`），因此关闭链路不会因凭证问题而失去 cleanup 能力。
5. 需要人工确认的决策点有 3 个（见第 9 节）：非 managed（custom）模式的严格程度、是否加 401 的独立错误映射与提示、凭证注册表的位置。

---

## 1. 第一轮环境事实（只读核查）

| 项目 | 结果 |
|---|---|
| `git status --short --branch` | `## security/napcat-rpc-auth...origin/main`，无未提交修改 |
| `git worktree list` | 本工作树已存在并被正确复用，未新建、未干扰其他 6 个工作树 |
| HEAD vs `origin/main` | 均为 `b5413dd`（fetch 后一致） |
| 仓库根 `.venv` | **不存在**（worktree 不含虚拟环境） |
| 主工作树 venv | `D:/ChatAnalyzerWorkspace/local-chat-analyzer/.venv`，editable `.pth` 指向**主工作树** `src` |
| 覆盖方式（已验证） | `PYTHONPATH=<本工作树>/src` 优先于 `.pth`，`import qq_chat_analyzer` 解析到本工作树 |
| pytest / node | pytest 8.4.2；node v24.16.0（真实 bridge 契约测试可运行） |
| 相关测试收集 | `test_napcat_qq_provider.py` + `test_qq_runtime_wiring.py` + `test_qq_napcat_runtime_bootstrap.py` 共 49 项，收集正常 |
| `runtime/qq-napcat-candidate` | 不存在（被 `.gitignore:44` 忽略，需本地 bootstrap 生成） |

> 环境提示（实施轮需要先定）：AGENTS.md 要求使用仓库根 `.venv`。本工作树没有 `.venv`，而主工作树 venv 的 editable 安装指向主工作树源码，**直接用它会测到错误的代码**。实施轮前需确认采用以下哪种，并保持一致：
> - A：在本工作树执行 `python -m venv .venv` 并按 `requirements.txt` 安装（需人工批准安装依赖）；
> - B：沿用主工作树 venv + `PYTHONPATH=<本工作树>/src`（只读验证已通过）；
> - C：`pip install -e .` 到独立 venv。
>
> 本轮未安装任何依赖、未创建 `.venv`。

---

## 2. 现状审计：RPC 攻击面与既有防护

### 2.1 监听与入口

`scripts/qq_napcat_plugin/bridge.mjs`

| 位置 | 现状 |
|---|---|
| `:11-16` | `startBridge(core, snapshot, {port=40655, host='127.0.0.1', runtimeId=null})`；host 只允许 `127.0.0.1`；`runtimeId` 必须是 `^[0-9a-f]{64}$` |
| `:99-101` | `requestTimeout/headersTimeout = 10s`，仅监听 loopback |

### 2.2 现有防护（逐项）

| 防护 | 位置 | 说明 |
|---|---|---|
| Origin/Host | `:67` | 任意 `Origin` 头 → `403 invalid_origin`；`Host` 必须是 `127.0.0.1:<port>` 或 `localhost:<port>`。**这是当前拦浏览器页面的关键防线** |
| 路由 | `:68-69` | 仅 `POST /rpc`，managed 时额外允许 `POST /rpc/<runtime_id>` |
| Content-Type | `:70` | 必须是 `application/json` |
| 请求大小 | `:71`、`:74-78` | `content-length` 与流式累计均限制 4096 字节 |
| 方法白名单 | `:52-60` | 7 个固定方法，无动态分发 |
| 参数校验 | `:93-94` | 固定 `params` 长度 + 每方法校验（uin / generation 段） |
| runtime 绑定 | `:88-90` | `EchoSnapshotApi.*` 在 managed 时必须走 `/rpc/<runtime_id>`，否则 `409 runtime_identity_mismatch` |
| 隐私错误 | `:95-96` | 方法内部异常折叠为 `qq_runtime_operation_failed`，不回传细节 |

### 2.3 缺口（可被本机未授权进程利用的调用链）

```
任意本机进程
  ├─ POST /rpc {"method":"Core.status"}                 → 拿到 uin / uid / nickname / runtime_id
  ├─ POST /rpc {"method":"EchoMetadata.listFriends"}    → 好友 UIN/UID/昵称/备注全量
  ├─ POST /rpc {"method":"EchoMetadata.listGroups"}     → 群号/群名/人数
  ├─ POST /rpc {"method":"GroupApi.getGroupMemberAll"}  → 任意群成员名单
  ├─ POST /rpc/<runtime_id> {"method":"EchoSnapshotApi.acquire"}
  │        → 触发 NapCat 解密 QQ 库并把明文 snapshot 发布到 <user_data>/transient/qq-direct-db/generations/*
  ├─ POST /rpc/<runtime_id> {"method":"EchoSnapshotApi.cleanup", params:[<id>]}
  │        → 删除他人正在使用的 generation（数据破坏 / DoS）
  └─ POST /rpc/<runtime_id> {"method":"EchoSnapshotApi.recover"}
           → 删除全部 generation / staging / legacy 明文（破坏性清理）
```

关键点：**`runtime_id` 可先通过 `Core.status` 无凭证读取**，因此 `/rpc/<runtime_id>` 的路径绑定不构成访问控制，只构成“路径契约一致性”。同时 `Host`/`Origin` 校验对非浏览器客户端无约束力（`urllib`、`curl`、`HttpClient` 可随意构造这两个头）。

---

## 3. 凭证传播路径全链（只读分析）

### 3.1 链路总览

```
QQAuthBridge._launch_window                     qq_auth_bridge.py:429-465
  └─ default_auth_window_launcher(config, paths)                    :625-642
       └─ _launch_auth_window(...)                                  :895-991
            ├─ environment = os.environ.copy()                      :902
            ├─ pop ECHO_MODE / NAPCAT_QUICK_*                       :903-908
            ├─ NAPCAT_QQ_PATH / PATCH_PACKAGE / LOAD_PATH /
            │  WORKDIR / INJECT_PATH / MAIN_PATH                    :909, 923-928
            ├─ ECHO_BRIDGE_PORT = "40655"                           :929
            ├─ ECHO_SNAPSHOT_ROOT = paths.snapshot_root             :932-933
            ├─ pop ECHO_RUNTIME_ID；managed 时 = paths.runtime_id    :934-936
            ├─ launch_owned_process(NapCatWinBootMain.exe, env=…)   :955-959   ← Windows Job 持有进程树
            └─ returncode != 0 → QQAuthWindowUnavailable            :972-990
                                  ↓  (环境变量跨越 QQ/NapCat 注入边界)
                    NapCat 加载 plugins/napcat-plugin-echo/index.mjs
                              index.mjs:11-19
                     process.env.ECHO_SNAPSHOT_ROOT / ECHO_BRIDGE_PORT / ECHO_RUNTIME_ID
                              ↓
                     startBridge(core, snapshot, {port, runtimeId})  bridge.mjs:11
                              ↓  HTTP 127.0.0.1:40655
          Python 客户端（同一 Echo 进程）
            ├─ NapCatQQProvider._request                        napcat_qq_provider.py:85-103
            │    └─ _rpc → Core.status / EchoMetadata.* /
            │       GroupApi.getGroupMemberAll                    :105-143
            │    └─ snapshot_client() → QQDirectSnapshotRuntimeClient（复用 _request）:145-151
            └─ QQDirectDatabaseImportService._require_runtime_client()   qq_direct_database_import_service.py:524-538
                 └─ QQDirectSnapshotRuntimeClient（自带 _urllib_transport） qq_direct_snapshot_runtime.py:307-326
```

### 3.2 启动

| 环节 | 事实 | 对认证的影响 |
|---|---|---|
| 启动入口唯一性 | `QQAuthBridge._launch_window`（managed 与 custom 都经 `default_auth_window_launcher`，`managed` 只影响 `ECHO_RUNTIME_ID`） | **存在唯一可注入凭证的位置**，无需协议重构 |
| 另一条启动路径 | `BundledQQRuntime.start()` 的 `env={**os.environ, NAPCAT_DISABLE_FFMPEG_DOWNLOAD}` 直启（`runtime/__init__.py:154-165`） | 该路径不带 `ECHO_SNAPSHOT_ROOT`，插件当前已无法工作；但它是**遗留通道**，实施时必须让它同样 pop 掉继承来的 `ECHO_BRIDGE_TOKEN`（若未来被启用） |
| 组合根 | `gui/app.py:67-108` 构造 provider factory / connection / direct-db / setup；`facade.py:1450-1467` 构造 `QQAuthBridge` | DI 方案与注册表方案的改动面差异集中在这里 |
| 进程所有权 | `launch_owned_process` 使用 Job Object，`_KILL_ON_CLOSE = 0x2000`（`windows_job.py:22`），`atexit` 关闭 Job（`:362-373`）；`QQProcessRegistry` 仅内存记录（`qq_process_registry.py:26-94`） | Echo 退出会带走整棵 runtime 进程树 → **“跨应用重启遗留 runtime”不是主路径** |

### 3.3 状态探测（readiness / 连接状态）

| 调用点 | 代码 | managed 时的附加校验 |
|---|---|---|
| 连接状态探测 | `qq_connection_service.py:80-102` ← `QQProviderFactory.create()`（`qq_provider_factory.py:27-50`） | 无 |
| setup 连接校验 | `qq_setup_service.py:326-336` `_verify_running_identity` | `status.runtime_id == get_runtime_paths().runtime_id`，否则 `RuntimeIdentityMismatch` |
| 运行时就绪探针 | `qq_setup_service.py:417-419` `healthy(url)` | `bridge_ready and runtime_id == paths.runtime_id` |
| 认证会话绑定校验 | `qq_auth_bridge.py:345-358` `_check_runtime_binding` | 同上，失败 → `qq_runtime_identity_mismatch` |

含义：**这三处“实例是不是我的”判断点，天然也是“该实例是否要求认证/我是否持有凭证”的判断点。**

### 3.4 元数据

`NapCatQQProvider.list_friends / list_groups / get_group_member_all`（`:125-143`）→ `bridge.mjs:26-51`。全部是隐私数据，且**没有 runtime 绑定要求**（走 `/rpc` 即可，managed 也一样）。

### 3.5 Direct DB（最高价值目标）

| 环节 | 事实 |
|---|---|
| 客户端构造 A | `NapCatQQProvider.snapshot_client()`（`napcat_qq_provider.py:145-151`），复用 provider 的 `_request` |
| 客户端构造 B | `QQDirectDatabaseImportService._require_runtime_client()`（`:524-538`），**自带 transport**，`runtime_id` 仅在 managed 时传入；每次 acquire 都会新建客户端 |
| URL 形态 | `qq_direct_snapshot_runtime.py:249-276`：`/rpc`，managed 追加 `/<runtime_id>` |
| 启动恢复 | `_recover_on_startup`（`:471-479`），失败语义 `not_ready`（可重试）/ `recovery_failed`（终态） |
| 关闭恢复 | `_recover_on_shutdown`（`:516-522`），`facade` 给予有界窗口（`facade.py:1180-1200`、`:1206-1259`） |
| 应用关闭顺序 | `facade.shutdown()`：Direct DB recover → 释放暂存报告 → 终止 QQ runtime（`facade.py:1148-1178`） |

### 3.6 退出与异常恢复

| 路径 | 是否依赖 HTTP 凭证 | 依据 |
|---|---|---|
| 应用正常关闭：先 RPC `recover`，再终止 runtime | 是（同进程内凭证仍有效） | `facade.py:1148-1178`；`qq_direct_database_import_service.py:516-522` |
| runtime 被 Job 终止（可能来不及跑 `plugin_cleanup`） | 否（应用已在终止前完成 recover） | 同上 + `windows_job.py:22` |
| `plugin_cleanup`（插件卸载） | **否**，进程内 `snapshot.recover()` | `index.mjs:23-30` → `snapshot.mjs:625-638` |
| 每次 `acquire` 的 fail-closed 前置清理 | **否**，进程内 `cleanSlate()` | `snapshot.mjs:431-442`、`workspace.mjs:111-126` |
| 启动恢复（运行时已就绪但应用刚起） | 是（需要本进程持有的凭证） | `qq_direct_database_import_service.py:471-479` |

> 结论：plaintext cleanup 存在**进程内独立路径**，因此“凭证丢失导致明文永远无法清理”在结构上不成立；但**应用侧 RPC recover 会失败**，需要给用户可执行提示（见 9.2 决策点）。

---

## 4. 最小方案设计

### 4.1 设计原则

1. **不新增协议层**：不引入认证握手、不新增 RPC 方法、不改现有方法与 JSON 形状（仅允许“增量字段”，见 9.1）。
2. **单一认证点**：`bridge.mjs` 在请求处理最前段统一校验，命中即 `401 invalid_credential`，**在方法分发之前返回**。
3. **fail closed**：凭证缺失/非法 → 插件**根本不启动 bridge**，不提供无认证监听。
4. **凭证不落盘**：不写 Git、不写 `qq.json`（`QQEnvironmentConfig` 保持不变）、不进报告、不进日志；只在内存与子进程环境变量中存在。
5. **保留全部既有防护**：`runtime_id`、方法白名单、JSON 形状、Host/Origin、大小限制、参数校验一律不动。

### 4.2 凭证的生成与传递

| 项 | 设计 |
|---|---|
| 生成位置 | `_launch_auth_window`（`qq_auth_bridge.py:895-991`）在构造子进程环境时生成：`secrets.token_hex(32)` |
| 生成时机 | **每次启动一个新凭证**，不复用、不持久化 |
| 传输通道 | 环境变量 `ECHO_BRIDGE_TOKEN`（与既有 `ECHO_BRIDGE_PORT` / `ECHO_SNAPSHOT_ROOT` / `ECHO_RUNTIME_ID` 同一受控通道） |
| 强制规则 | `environment.pop("ECHO_BRIDGE_TOKEN", None)` 后**再写入新值**（与 `:934-936` 的 `ECHO_RUNTIME_ID` 处理完全同构），防止父进程/上一次运行的残留值被继承导致“服务端与客户端凭证不一致” |
| Python 侧保存 | 新增极小的内存注册表模块（建议 `src/qq_chat_analyzer/providers/qq_bridge_credential.py`）：`{normalized_base_url: token}`，带 `RLock`；`repr` 脱敏；不提供任何 `__str__` 泄漏路径 |
| 注册表键 | 规范化后的 `config.napcat_bridge_url`（与客户端实际使用的 URL 一致）；仅保存 Echo 自己启动过的 URL |
| 消费端 | 见 4.4；**在请求时刻取值**（而非构造时刻），因为 `QQProviderFactory` 会长期缓存 provider |
| 位置理由 | `providers/` 已被 `qq_auth_bridge` 合法导入（`:351`），且注册表风格与 `windows_job.py` 的 `_LIVE` + `atexit` 全局注册表一致；若审阅偏好“无全局状态”，替代方案见 9.3 |

凭证形状：`^[0-9a-f]{64}$`（64 hex 字符 = 256 bit），与既有 `runtime_id` 的校验习惯一致，避免 base64 在环境变量/头部的编码歧义。

### 4.3 服务端强制（`bridge.mjs`）

```
startBridge(core, snapshot, {port, host, runtimeId, token})
  - token 必填：非字符串或不符合 ^[0-9a-f]{64}$ → throw new Error('invalid_bridge_credential')（与既有 invalid_runtime_identity 同构）
  - 请求处理顺序（只在前段插入一步，后续全部保持原样）：
      1. Origin / Host 校验                       （现状 :67）
      2. 方法 / 路由 / Content-Type / 大小        （现状 :68-71）
      3. 【新增】凭证校验 → 不符即 401 {ok:false,error:'invalid_credential'}，不读 body、不进分发
      4. body 解析 → 参数校验 → runtime 绑定 → 方法分发（现状 :83-96）
```

- 头部：`Authorization: Bearer <token>`（标准语义；`Host`/`Origin` 门禁已阻断浏览器侧，见 2.2）。
- 比较：先判长度，再 `crypto.timingSafeEqual`；**任何响应（含错误）都不得回显凭证或凭证片段**。
- 顺序说明：凭证校验放在 Origin 之后（保留既有的“外部 Origin 直接 403”行为，避免给浏览器任何探测面），但在路由之前（不向未认证调用者暴露 `/rpc` 与 `/rpc/<id>` 的 404/409 差异）。
- 保持：`runtimeId` 校验、`/rpc/<runtime_id>` 绑定、`EchoSnapshotApi` 的 409 语义、错误字符串全部不变。

### 4.4 客户端侧（Python）

| 文件 | 改动 |
|---|---|
| `providers/napcat_qq_provider.py:85-103` | `_request` 构造 `urllib.request.Request` 时，从注册表按 `self._base_url` 取 token；存在则加 `Authorization: Bearer <token>`。`_rpc` 语义、错误折叠不变 |
| `providers/qq_direct_snapshot_runtime.py:307-326` | `_urllib_transport` 同样按 URL 取 token 并加头（该函数只在“未注入 transport”时使用，即 3.5 的构造 B） |
| `providers/napcat_qq_provider.py:145-151` | `snapshot_client()` 复用 provider 的 transport，自动继承头部，无需额外代码 |
| `qq_direct_database_import_service.py:524-538` | 无需签名改动（transport 自行取凭证）；若要显式化，可加 `token=` 参数（见 9.3） |

**不发送未认证请求的额外保障（建议纳入本轮）**：当注册表**没有**该 URL 的凭证时，provider 直接抛 `NapCatQQError()`（等价于“该 bridge 不是我启动的”），**不发出请求**。这样可把不变量收紧为“Echo 发出的每一个 bridge 请求都带凭证”，并让“异实例/遗留实例”在本地即被识别为不可用，而不是先发一个无凭证请求再等 401。

### 4.5 插件侧（`index.mjs`）

```
plugin_init(ctx):
  1. 现状：ECHO_SNAPSHOT_ROOT 校验（:11-14）        ← 保持在前（既有测试语义不变）
  2. 新增：读 ECHO_BRIDGE_TOKEN；非字符串/不匹配 ^[0-9a-f]{64}$
           → throw new Error('echo_bridge_token_missing')   ← fail closed，不注册、不监听
  3. 现状：registerEchoSnapshotApi + startBridge（:15-19），startBridge 传入 token
plugin_cleanup(): 不变（进程内 recover，不依赖凭证）
```

### 4.6 生命周期语义矩阵（重点：cleanup / recover 不因凭证丢失而失效）

| 场景 | 凭证状态 | 期望结果 |
|---|---|---|
| 运行期 acquire / cleanup / 元数据 | 内存有效 | 全部带 Bearer，正常 |
| 同一会话正常关闭 | 内存有效 | `shutdown()` 先 RPC recover 成功 → 再终止 runtime（顺序不变） |
| 启动恢复（同会话，runtime 已就绪） | 内存有效 | `start()` 的 recover 成功 → 进入 ACTIVE |
| 新启动覆盖凭证 | 写入新值，旧 runtime 在此之前已被 `terminate_all()` + Job 关闭 | 不存在“旧 runtime 用旧凭证”的窗口 |
| runtime 被 Job 强制终止 | 不适用 | 应用已在终止前完成 recover；`plugin_cleanup` 可能不执行，但也不必要 |
| 应用重启后仍存在遗留 runtime（防御性场景，Job+KILL_ON_CLOSE 使该路径基本不可达） | 无凭证 | RPC recover / 身份校验失败 → 走既有 `runtime_identity_mismatch` / `not_ready` / `recovery_failed` 有界失败，日志可诊断；明文最终由该 runtime 的 `plugin_cleanup` 或下一次 `acquire` 的 `cleanSlate()` 清除 |
| 凭证被意外丢失（理论） | 无 | **不得挂起**：失败必须仍受 `facade` 的有界窗口约束（`:1206-1259`），并保持“可报告、可重试”语义 |

### 4.7 非 managed（custom）模式

- custom 模式同样经 `default_auth_window_launcher(..., managed=False)` 启动 → **同样注入并强制凭证**，不保留无认证旁路。
- custom 目录是用户自备产物，Echo 无法证明其中的插件版本；若该目录里的旧插件忽略新增头，则该 bridge 仍是无认证的（**残余风险**，见 8.3 与 9.1）。
- 明确禁止的做法：`token === null` 时放行全部方法（为了兼容旧插件/让测试变绿）。本轮方案中**不存在任何未认证服务端模式**。

---

## 5. 保留不动的既有防护（明确清单）

- `runtime_id`：生成方式、`^[0-9a-f]{64}$` 校验、`/rpc/<runtime_id>` 绑定、`409 runtime_identity_mismatch`、`Core.status` 中的 `runtime_id` 字段。
- RPC 方法与 JSON 形状：7 个方法名、`{method, params}` 请求、`{ok, result|error}` 响应。
- Host/Origin、Content-Type、`MAX_REQUEST_BYTES=4096`、流式大小限制、超时、隐私错误折叠。
- `QQEnvironmentConfig` 与 `qq.json` 字段（**不新增任何凭证字段**）。
- `QQRuntimePaths.runtime_id` 与 workspace 准备/校验（组件 id 由内容摘要决定）。
- 快照 generation 布局、lease、manifest、`validate_generation_id` 路径段校验。

---

## 6. 凭证不落盘的核查点

| 通道 | 措施 |
|---|---|
| Git | 凭证运行时生成，仓库内不出现任何真实凭证；测试只用虚构 token |
| 配置 | 不写 `qq.json`；`QQEnvironmentConfigWriter.save` 的 payload（`qq_environment_config.py:97-109`）保持不变 |
| 报告 / 导出 | 分析、报告链路不接触 bridge 凭证；`Core.status` 响应**不含**凭证字段 |
| 日志 | 现有启动日志只打印 `command/cwd/qq_path`（`qq_auth_bridge.py:938-941`）与 `_config_summary`（`:1051-1058`，只含 runtime 目录），不打印 env；新增代码禁止打印凭证，并需新增断言测试 |
| 错误与异常 | 公共错误只用稳定 code（如 `invalid_credential`），不携带凭证或凭证片段 |
| 进程环境（**接受的局限**） | 同用户进程可通过 `PROCESS_VM_READ` / 调试器读取环境块；管理员可读任意进程环境；NapCat 自身的子进程（如 `workspace.mjs:42` 启动的 PowerShell）会继承该变量。缓解：凭证**每次启动轮换**、仅内存保存、与端口绑定（泄漏后无法用于其他实例）、runtime 终止即失效 |
| 残余价值说明 | 该凭证真正阻断的是**同机其他 Windows 用户账户/低权限程序**（loopback 不受用户隔离保护，而环境变量读取受用户隔离保护）。同用户攻击者仍可读取 env，但同用户攻击者本来就能直接读取该用户的 QQ 数据文件，边际风险有限 |

---

## 7. 测试与兼容性影响

### 7.1 必须新增的 RED（安全不变量）

服务端（真实 bridge，Node）：
- R1 `Core.status` 无凭证 → `401 invalid_credential`，且**未调用**任何 core API。
- R2 `EchoMetadata.listFriends` / `listGroups` / `GroupApi.getGroupMemberAll` 无凭证或错误凭证 → 401，且 **spy 断言 core 方法调用次数为 0**（直接对应“认证失败时不能执行任何 RPC”）。
- R3 `EchoSnapshotApi.acquire / cleanup / recover` 无凭证 → 401，且 **snapshot spy 调用次数为 0**（不得产生任何明文落盘）。
- R4 `/rpc/<正确 runtime_id>` 在缺少凭证时同样 401（凭证与 runtime 绑定两条独立防线叠加，不能互相替代）。
- R5 `startBridge` 未传 token / token 形状非法 → 抛错且**不监听**。
- R6 401 响应体不得回显凭证（含“前缀/长度”类信息）。

插件层（Node，`index.mjs`）：
- R7 `ECHO_BRIDGE_TOKEN` 缺失或非法 → `plugin_init` 抛 `echo_bridge_token_missing`，且 bridge 未启动（监听端口不可用）。
- R8 `plugin_cleanup` 在无凭证场景下仍能完成进程内 recover（证明 cleanup 不依赖凭证）。

Python 侧：
- R9 启动链注入：`_launch_auth_window` 产出的 env 含合法 `ECHO_BRIDGE_TOKEN`，且**不等于**父进程中的既有值（覆盖 pop-then-set 规则）。
- R10 无凭证时不发请求：注册表为空时 provider 调用直接失败且**未发出 HTTP 请求**（transport spy 断言 0 次）。
- R11 有凭证时请求头正确：`Authorization: Bearer <token>` 出现在 provider 与 snapshot client 两条构造路径上。
- R12 不泄漏：启动 + 探测 + 401 失败后，`caplog` 全文不含凭证；`qq.json` 字节内容在启动前后一致、不含凭证。
- R13 关闭链：Direct DB `shutdown()` 的 recover 走已认证客户端；在无凭证时失败仍需**有界**且被记录（不得挂起）。

### 7.2 需要更新的既有测试（属于测试夹具适配，不是生产旁路）

| 测试 | 现状 | 需要的调整 |
|---|---|---|
| `tests/test_napcat_qq_provider.py:25-40` | 虚构 server 以 `startBridge(core, snapshot, {port:0})` 启动（无 token） | 传入虚构 token；`request()` helper（`:64-71`）默认带正确凭证，另加无凭证/错误凭证用例 |
| `tests/test_napcat_qq_provider.py:111-146` | 覆盖既有边界拒绝 | 保留；新增 R1–R6 |
| `tests/test_napcat_qq_provider.py:179-185` | `startBridge({host:'0.0.0.0'})` 必须抛错 | 仍抛错；补 token 参数以表达意图 |
| `tests/test_qq_runtime_wiring.py:99-116` | 断言子进程 env 中各 `ECHO_*` 值 | 增加 `ECHO_BRIDGE_TOKEN` 合法性断言 + 不等于父进程值 |
| `tests/test_qq_runtime_wiring.py:330-393`（`slow_integration`） | 真实插件 + Python 客户端，断言“旧客户端被拒” | 正向用例改为携带 `seen[0]['ECHO_BRIDGE_TOKEN']`；**新增**“无凭证客户端一律被拒”，正好强化该测试原有意图 |
| `tests/test_qq_napcat_runtime_bootstrap.py:180-193` | 设 `ECHO_SNAPSHOT_ROOT`/`ECHO_BRIDGE_PORT` 让 `plugin_init` 成功 | 补设虚构 token（顺序上 snapshot root 校验仍在前，`:211-227` 的“相对/缺失 root”用例不受影响） |
| `tests/test_qq_napcat_runtime_bootstrap.py:34-51` | pins 模板 sha256 必须与实际文件一致 | bridge.mjs / index.mjs 改动后**必须同步更新 pins**（见 8.2） |
| `tests/test_gui_qq_deqce_wiring.py:138-159` | custom 模式启动 env 断言（`get` 语义，不穷举） | 预期无需改动；实施时确认 |

### 7.3 为什么这不是“为通过测试保留无认证旁路”

- 生产代码不存在任何 `token == null → 放行` 分支；服务端只有“有凭证且匹配”与“401”两种结局。
- 失败路径的唯一形态是 401（或插件拒绝启动），不存在降级为无认证的重试。
- 测试的修改只发生在“虚构 server 如何提供凭证”和“虚构客户端如何携带凭证”，不改变生产校验逻辑。

---

## 8. 实施必须注意的工程约束（容易漏）

### 8.1 组件内容摘要会变 → 工作副本路径会变
`_components()`（`qq_runtime_workspace.py:98-128`）把插件文件 sha256 纳入 `component` 摘要，`component` 决定 `work_root`。修改 `bridge.mjs`/`index.mjs` 后：
- 组件 id 变化 → 新的 `work_root`（旧工作副本不会被复用，也不会被自动删除，属于既有行为）；
- `runtime/qq-napcat-candidate` 必须**重新 bootstrap** 才能让真实（非虚构）E2E 一致。

### 8.2 pins 必须同步
`scripts/qq_napcat_runtime_pins.json:72-103` 的 `templates[].sha256` 是**强制校验**（`bootstrap_qq_napcat_runtime.py:139-145`），且 `test_qq_napcat_runtime_bootstrap.py:34-51` 会直接比对仓库内文件摘要。改动 `scripts/qq_napcat_plugin/*.mjs` 必须同时更新对应 sha256，否则 bootstrap 与测试都会失败。

### 8.3 其他
- `snapshot.mjs` 的 `workspace.mjs:42` 用 `{...process.env}` 启动 PowerShell → 会继承凭证。可选加固：在该 spawn 中删除 `ECHO_BRIDGE_TOKEN`（属 pins 覆盖文件，需一并更新 sha256）。
- managed 目录内容由 pins 校验，因此 managed 路径下“插件版本与客户端不匹配”不可能出现；custom 目录无此保证。
- `bridge.mjs` 头部上限由 Node 默认 16KB 决定，新增一个头不影响现有 4096 字节 body 限制。

---

## 9. 需要人工确认的决策点

### 9.1 非 managed（custom）模式的严格程度
- 方案 A（默认建议）：custom 模式也注入并强制凭证；对“旧插件忽略新头”的残余风险只做文档化。
- 方案 B（更严格）：在 `Core.status` 增加一个增量字段（如 `bridge_auth: true`），并在三处实例校验（`qq_setup_service._verify_running_identity`、`qq_auth_bridge._check_runtime_binding`、`default_runtime_factory.healthy`）要求该字段，从而**拒绝采用任何未认证 bridge**；代价是客户端可见 JSON 增加一个字段（合规于“不大规模协议重构”）。
- 方案 C：仅文档化，不做字段。**不推荐**（无法验证“Echo 只与强制认证的 bridge 通信”）。

### 9.2 认证失败的用户可见语义
- 方案 A：不区分 401 与其他失败（沿用 `NapCatQQError` 折叠）→ 用户看到“无法确认 QQ 数据源状态”。
- 方案 B（建议）：`_request` 将 HTTP 401 映射为 `NapCatQQError` 子类（如 `NapCatQQAuthRejected`，保持既有 `except NapCatQQError` 全部有效），使 `_verify_running_identity` 能给出可执行提示（复用现有“请完全退出 QQ 后重试”话术族），而不是未知错误。

### 9.3 Python 凭证注册表的位置与形态
- 方案 A（默认建议，最小）：`providers/qq_bridge_credential.py` 内存注册表 + 请求时刻取值。
- 方案 B（无全局状态）：由组合根持有一个凭证对象，显式注入 launcher、provider factory、Direct DB 服务（需改 `gui/app.py`、`facade.py`、`qq_setup_service.py`、`qq_provider_factory.py`、`qq_direct_database_import_service.py`，改动面明显更大）。
- 相关子问题：是否需要“保留上一个凭证并在 401 时做一次有界重试”（用于极端乱序启动）。当前分析认为主流程不存在该窗口（启动前先 `terminate_all()`），**默认不做**。

### 9.4 环境（见第 1 节）
本工作树使用哪种 Python 环境策略（A/B/C），需要确认；未确认前不应运行依赖安装。

---

## 10. 实施顺序建议（第二轮，待批准后执行）

1. 环境决策（9.4）→ 确认 focused 测试可运行。
2. RED：先写 R1–R13（虚构 token / 虚构 server，不触碰真实聊天数据）。
3. GREEN：
   - `scripts/qq_napcat_plugin/bridge.mjs`（token 参数 + 统一校验 + 401）
   - `scripts/qq_napcat_plugin/index.mjs`（env 读取 + fail closed）
   - `scripts/qq_napcat_runtime_pins.json`（两个模板 sha256）
   - `src/qq_chat_analyzer/providers/qq_bridge_credential.py`（新，内存注册表）
   - `src/qq_chat_analyzer/providers/napcat_qq_provider.py`（请求头 + 无凭证不发请求）
   - `src/qq_chat_analyzer/providers/qq_direct_snapshot_runtime.py`（默认 transport 请求头）
   - `src/qq_chat_analyzer/application/qq/qq_auth_bridge.py`（生成/pop-then-set/注册，不落日志）
4. focused：
   - `tests/test_napcat_qq_provider.py`
   - `tests/test_qq_runtime_wiring.py`（含 `-m slow_integration` 的真实插件端到端）
   - `tests/test_qq_napcat_runtime_bootstrap.py`
   - `tests/test_qq_auth_bridge.py`、`tests/test_qq_setup_service.py`、`tests/test_shutdown_ownership.py`、`tests/test_shutdown_diagnostics.py`
5. Fast Suite → Full Suite。
6. `git diff --check` / `git diff --name-only` / `git status --short`，确认只改了本任务允许的文件。
7. 真实验收（需人工）：需要本地 bootstrap 真实 runtime（网络 + 官方 archive 校验），并人工确认 QQ 登录、Direct DB 分析、关闭后无残留明文 generation。

命令（本工作树，`PYTHONPATH` 方式，需先确认 9.4）：

```powershell
$env:PYTHONPATH='d:/ChatAnalyzerWorkspace/wt-napcat-rpc-auth/src'
D:/ChatAnalyzerWorkspace/local-chat-analyzer/.venv/Scripts/python.exe -m pytest tests/test_napcat_qq_provider.py -q
D:/ChatAnalyzerWorkspace/local-chat-analyzer/.venv/Scripts/python.exe -m pytest -m "not slow_integration and not known_failure" -q
D:/ChatAnalyzerWorkspace/local-chat-analyzer/.venv/Scripts/python.exe -m pytest -q
```

---

## 11. 本轮未做的事

- 未修改任何源码、脚本、pins、测试或文档（本报告位于工作区之外的 artifact 目录）。
- 未创建 commit、未 add、未 restore、未 checkout。
- 未安装依赖、未创建虚拟环境。
- 未下载 NapCat 官方包、未 bootstrap runtime、未启动 QQ 或任何真实 runtime。
- 未接触任何真实聊天记录（全部结论来自源码阅读与虚构用例收集）。
