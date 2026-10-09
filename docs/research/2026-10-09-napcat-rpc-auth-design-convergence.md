# NapCat RPC 认证 —— 第二轮设计收敛（Runtime Session 持有凭证 + 显式注入）

- 仓库：`lingmeng-658/echo-chat-analyzer`　工作树：`D:/ChatAnalyzerWorkspace/wt-napcat-rpc-auth`　分支：`security/napcat-rpc-auth`
- 关系：本文件**收敛并取代**第一轮报告（`2026-10-09-napcat-rpc-auth-design-audit.md`）的第 4 节与 9.1/9.3 决策点；第一轮的攻击面审计、既有防护清单、cleanup 路径结论继续有效。
- 本轮范围：**只补充设计，不修改生产代码、不 commit**。
- 事实标注约定：**【事实】**= 已通过读代码/跑命令确认；**【假设】**= 由代码结构推断、尚未运行时验证；**【待实测】**= 需要真实 runtime 或人工确认。

---

## 0. 收敛结论

1. **所有权**：凭证由 **`QQRuntimeSession`**（进程内单实例，单槽，不按 URL 索引）持有；由组合根 `gui/app.py` 创建并**显式注入**到 provider factory、Direct DB service、setup service、auth bridge 四个消费者；两个 launcher 工厂函数提供以 `default_qq_runtime_session()` 为默认值的兜底（对齐既有 `default_qq_process_registry()` 模式）。**不采用按 bridge URL 索引的全局注册表。**
2. **生命周期**：`begin_launch()` 在每次启动瞬间生成新凭证并设为当前；任何“停止 Echo 自有 runtime”的路径都调用 `retire()`；**单槽、无历史、无重试** → 旧凭证在结构上不可能用于新实例。
3. **兼容性**：managed 与 custom 共用同一个启动函数（`_launch_auth_window`），因此两者都注入并强制认证；**推理结论是 custom 连接能力不因本方案改变**（同一 URL、同一 RPC 形状、同一请求路径）。custom 目录里的**旧插件**会忽略新增头 → 该 bridge 自身仍无认证力：这是“用户自备产物”的既有限制，Echo 自身代码内不存在无认证旁路（Echo 永不发送无凭证请求、永不使用无凭证 bridge）。
4. **错误语义**：HTTP 401 → 两个**独立内部错误类型**（provider 侧 / snapshot 侧），只映射状态码，只在新类型上复用**既有**公共文案，不改动任何既有 catch 结构。
5. **改动面（必需文件）= 12 个**：1 新增 + 8 Python 修改 + 2 插件 + 1 pins。另有 2 个可选防御性改动。
6. **环境**：本工作树已建立独立 `.venv`（`D:\ChatAnalyzerWorkspace\wt-napcat-rpc-auth\.venv`，Python 3.13.9，pytest 8.4.2，`qq_chat_analyzer` 解析到本工作树 `src`），不再依赖主工作树 editable 安装。

---

## 1. 本轮新确认的事实（代码确认）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 组合根 `gui/app.py` 只构造 QQ 的 provider factory / Direct DB service / connection / setup；`QQAuthBridge` 是由 **facade** 在 `_require_qq_auth_bridge()` 里构造的 | `gui/app.py:67-127`、`facade.py:1450-1467` |
| F2 | facade 构造函数只接受 `source_builders: dict[ChatSource, Callable[[], Any]]`，**没有**任何可承载 session 的参数；QQ bundle 由外部 builder 惰性构造 | `facade.py:357-401`、`facade.py:390` |
| F3 | 启动路径只有两条，且都汇聚到 `_launch_auth_window`：① auth bridge 的 launcher；② `default_runtime_factory` 注入 `BundledQQRuntime` 的 launcher | `qq_auth_bridge.py:429-453,625-642`、`qq_setup_service.py:409-428` |
| F4 | `BundledQQRuntime.start()` 还有一条**直启**回退（`env={**os.environ, NAPCAT_DISABLE_FFMPEG_DOWNLOAD:"1"}`），不注入 `ECHO_SNAPSHOT_ROOT`，因此该路径下插件必然 `echo_snapshot_root_missing` | `runtime/__init__.py:154-165`、`index.mjs:11-14` |
| F5 | 生产代码中**没有任何**地方设置 `runtime_mode="custom"` / 传入自定义 `runtime_directory`；GUI 里 `custom` 只出现在分析范围选择 | 全仓 `runtime_mode=`/`runtime_directory=` 搜索仅命中 config 读取与默认值；`gui/session_analysis_panel.py` |
| F6 | 存在 3 处**临时构造** `NapCatQQProvider(url, timeout=1)` 的探针，不经过 provider factory | `qq_setup_service.py:331`、`qq_setup_service.py:418`、`qq_auth_bridge.py:353` |
| F7 | “停止自有 runtime”的落点：`QQAuthBridge._terminate_runtime_sessions()`（disconnect / cancel / 重启前）、`Facade.shutdown_qq_runtime()`（`registry.terminate_all()`）、`QQSetupService.stop_runtime()`（`QQRuntimeManager.stop()`） | `qq_auth_bridge.py:484-508,166-181,287-288`、`facade.py:576-587`、`qq_setup_service.py:270-275` |
| F8 | 仓库已有“进程级单例访问器 + 可显式注入”的先例：`default_qq_process_registry()` | `qq_process_registry.py`、`facade.py:1469-1477`、`qq_auth_bridge.py:140-142` |
| F9 | 仓库已有“把密钥放进子进程环境变量并按需清除”的先例（微信 key），但它是**写入 Echo 自身 `os.environ`** 的 | `wechat_key_service.py:619-628` |
| F10 | `_launch_auth_window` 用 `os.environ.copy()` 构造子进程环境，只修改**局部 dict**；全仓没有任何 `os.environ[ECHO_*] = …` 写入 | `qq_auth_bridge.py:902-936`；全仓 `os.environ[` 仅命中 `wechat_key_service.py:622` |
| F11 | 启动相关日志只打印 `command/cwd/qq_path`、launcher 输出**字节数**、config 摘要（仅 runtime 目录），不打印 env | `qq_auth_bridge.py:938-941,1004-1009,1051-1058` |
| F12 | `snapshot.mjs` 的 `acquire` 第 1 步、`recover`、`plugin_cleanup` 三条路径都汇入进程内 `cleanSlate()` → `workspace.recover()`（删除 staging / generations / legacy 明文） | `snapshot.mjs:431-442,625-638`、`workspace.mjs:111-126` |
| F13 | Job Object 使用 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`，且 `atexit` 关闭自有 Job；`QQProcessRegistry` 仅内存记录 | `windows_job.py:22,362-373`、`qq_process_registry.py:26-94` |
| F14 | 修改 `scripts/qq_napcat_plugin/*.mjs` 会改变 `_components()` 的组件摘要（→ 新 `work_root`），且必须同步 pins 中的 `templates[].sha256`，否则 bootstrap 与 bootstrap 契约测试失败 | `qq_runtime_workspace.py:98-128`、`bootstrap_qq_napcat_runtime.py:139-145`、`test_qq_napcat_runtime_bootstrap.py:34-51` |

## 1.1 风险假设（未运行时验证）

| # | 假设 | 影响 | 验证方式 |
|---|---|---|---|
| A1 | Echo 自有 runtime 进程树在 Echo 退出/崩溃时必定被 Job 终止，不存在“跨 Echo 重启的遗留 runtime”主路径 | 决定“无凭证无法 adopt 旧实例”是否影响真实用户 | 真机：启动 → 强杀 Echo → 检查 40655 与 QQ 进程；【待实测】 |
| A2 | custom 模式在当前产品中**不可由 GUI 产生**，只来自历史 `qq.json` 或手工编辑 | custom 的兼容性影响面极小 | 已读代码（F5）；【假设】用户机器上仍可能存在历史配置 |
| A3 | NapCat 自身日志（`work_root/logs`）不会打印进程环境（因而不会记录凭证） | 决定是否需要额外脱敏 | 真机检查日志；【待实测】 |
| A4 | `Authorization` 头不会被 NapCat 侧任何中间层（无代理、loopback 直连）剥离或改写 | 决定头部选择是否需要备选方案 | 已确认 provider 禁用代理（`ProxyHandler({})`），snapshot 传输未禁用；【假设】 |

---

## 2. managed / custom 真实调用路径核查

### 2.1 启动路径矩阵

| 步骤 | managed | custom |
|---|---|---|
| 配置来源 | `load_or_default()` 命中 `runtime_mode == "managed"` 时**恒回落到 bundled 默认**（旧 runtime_directory 被忽略） | 磁盘配置显式 `runtime_mode == "custom"` 时**原样返回** |
| 路径解析 | `resolve_runtime_paths(prepare=True)` → `prepare_qq_workspace()`：哈希校验 + 复制到 `work_root` | `QQRuntimePaths(program, program, program.parent/"output/qq_direct_db_phase35")`：不 prepare、不校验 |
| 插件来源 | 工作副本，内容受 pins 摘要保护 | 用户目录内既有文件，**内容不受任何校验** |
| 启动函数 | `_launch_auth_window(..., managed=True)` | `_launch_auth_window(..., managed=False)`（同一函数） |
| 环境变量 | `ECHO_RUNTIME_ID = paths.runtime_id` | `ECHO_RUNTIME_ID` 被 pop，插件得到 `runtimeId = null` |
| 公共端口 | `ECHO_BRIDGE_PORT = "40655"`（硬编码，两种模式相同） | 同左 |
| snapshot root | `paths.snapshot_root`（用户数据目录） | `runtime_directory.parent/output/qq_direct_db_phase35` |
| RPC 路由 | `/rpc` + `/rpc/<runtime_id>` | 仅 `/rpc` |
| 身份校验 | `_verify_running_identity` / `healthy` / `_check_runtime_binding` 三处校验 `runtime_id` | **全部跳过**（只要求 `bridge_ready`） |
| Direct DB 客户端 | `runtime_id=paths.runtime_id` | `runtime_id=None` |

### 2.2 每次 RPC 的消费者来源

| RPC 调用 | 客户端对象 | 构造点 |
|---|---|---|
| 连接状态探测 | `NapCatQQProvider` | `QQProviderFactory._build()` → `default_provider_builder(config)`（工厂缓存，长期存活） |
| 身份校验探针 | `NapCatQQProvider`（临时） | `qq_setup_service.py:331,418`、`qq_auth_bridge.py:353` |
| 元数据（friends/groups/members） | `NapCatQQProvider` | 同上工厂 |
| Direct DB（acquire/cleanup/recover） | `QQDirectSnapshotRuntimeClient` | ① `NapCatQQProvider.snapshot_client()`；② `QQDirectDatabaseImportService._require_runtime_client()`（**每次 acquire 新建**，自带 transport） |

结论：需要凭证的**唯一数据通道**是 2 个客户端类；需要“当前凭证”的对象共 6 个构造点（工厂 1 + 临时探针 3 + snapshot client 2）。

---

## 3. 设计收敛：`QQRuntimeSession` 持有凭证 + 显式注入

### 3.1 为什么不是 URL 索引的全局注册表

- Echo 进程内**同时最多只有一个自有 NapCat 实例**：端口固定 40655，auth bridge 用 `_auth_lock` 串行化启动，`QQRuntimeManager`/`BundledQQRuntime` 各持一个进程句柄（【事实】F3/F7）。因此“按 URL 分桶”没有真实语义来源。
- 键取自 `config.napcat_bridge_url`，而启动端端口是**硬编码 40655**：两者本就不保证一致（既有不一致），用 URL 做键会把“配置笔误”变成“认证静默失败”。单槽 + 显式注入没有这个耦合。
- URL 索引注册表是**隐式耦合**：任何能构造 URL 的代码都能取到凭证，且无法在测试/GUI 中显式替换来源。

### 3.2 Session 契约（新增 `application/qq/qq_runtime_session.py`）

```text
class QQRuntimeSession:
    """Owns the single bridge credential of the runtime Echo launched."""

    def begin_launch(self) -> str:
        """Mint a new credential (secrets.token_hex(32)) and make it current."""

    def credential(self) -> str | None:
        """Current credential, or None when no Echo-owned instance is running."""

    def retire(self, credential: str | None = None) -> None:
        """Drop the current credential; ignore a credential that is no longer current."""

    def __repr__(self) -> str:
        """Redacted: never contains the credential."""

def default_qq_runtime_session() -> QQRuntimeSession:
    """Process-level default, injectable/resettable like default_qq_process_registry()."""
```

约束：
- **单槽**：不保存历史、不做多凭证匹配；`begin_launch()` 直接替换（并返回新值供环境注入）。
- 只存内存；`__str__/__repr__` 脱敏；不提供序列化接口。
- `RLock` 保护（启动在 GUI 线程，读取在探测线程/关闭线程）。
- 凭证形状 `^[0-9a-f]{64}$`（与 `runtime_id` 校验习惯一致，避免编码歧义）。
- **不写入 `os.environ`**：与既有微信 key 做法（F9）刻意不同 —— 写入 Echo 自身环境块会让任何同用户进程枚举进程时读到；本项目只把凭证放进**子进程 env dict**（F10）。

### 3.3 显式注入调用链（逐跳）

```text
gui/app.py :: build_facade()
  session = QQRuntimeSession()                                  # 唯一持有者（进程内）
  ChatAnalyzerFacade(
      source_builders={ChatSource.QQ: lambda: _qq_bundle_factory(session), ...},
      qq_runtime_session=session, ...)                          # 新增参数（facade）
      │
      ├─ facade.qq_runtime_session = session
      │    └─ _require_qq_auth_bridge()
      │         └─ QQAuthBridge(..., credential=session)        # 新增参数
      │              ├─ _launch_window → default_auth_window_launcher(config, paths=…, credential=session)
      │              ├─ _check_runtime_binding → NapCatQQProvider(url, credential=session, timeout=1)
      │              └─ _terminate_runtime_sessions → session.retire()
      │
      └─ _qq_bundle_factory(session)                            # gui/app.py
           ├─ QQProviderFactory(config_loader=…, bridge_credential=session)
           │    └─ default_provider_builder(config, credential=session)
           │         └─ NapCatQQProvider(url, credential=session)
           │              ├─ _request：请求时刻读 session.credential() → Authorization: Bearer …
           │              └─ snapshot_client() → QQDirectSnapshotRuntimeClient(..., credential=session)
           ├─ QQDirectDatabaseImportService(provider_factory=…, config_loader=…, bridge_credential=session)
           │    └─ _require_runtime_client() → QQDirectSnapshotRuntimeClient(..., credential=session)
           └─ QQSetupService(config_loader=…, provider_factory=…, connection_service=…, bridge_credential=session)
                ├─ _verify_running_identity → NapCatQQProvider(url, credential=session, timeout=1)
                ├─ default_runtime_factory(config, paths=…, path_preparer=…, credential=session)
                │    ├─ healthy(url) → NapCatQQProvider(url, credential=session, timeout=1)
                │    └─ BundledQQRuntime(launcher=default_auth_window_launcher(config, paths=…, credential=session))
                └─ stop_runtime() → session.retire()
                          │
                          └─ _launch_auth_window(runtime_directory, launcher, qq_path, *, paths, managed, credential)
                               ├─ token = credential.begin_launch()          # 每次启动新凭证
                               ├─ environment.pop("ECHO_BRIDGE_TOKEN", None)
                               ├─ environment["ECHO_BRIDGE_TOKEN"] = token
                               ├─ spawn = launch_owned_process(command, env=environment, …)
                               └─ 启动失败(OSError / returncode ∉ {None,0}) → credential.retire(token)
```

要点：
- **`default_qq_runtime_session()` 只作为两个 launcher 工厂函数与 `default_provider_builder` 的默认值兜底**（对齐 F8），生产接线始终显式传入；显式传入的对象永不触碰访问器。
- 三个临时探针（F6）必须与工厂走同一个 session，否则身份校验会 fail-closed 成“异实例”。
- `QQConnectionService` **不需要改动**（provider 来自工厂）。

### 3.4 改动面评估与最小替代方案

**主方案 A（推荐）必需文件 = 12**
1. 新增 `src/qq_chat_analyzer/application/qq/qq_runtime_session.py`
2. `src/qq_chat_analyzer/gui/app.py`
3. `src/qq_chat_analyzer/application/facade.py`
4. `src/qq_chat_analyzer/application/qq/qq_auth_bridge.py`
5. `src/qq_chat_analyzer/application/qq/qq_setup_service.py`
6. `src/qq_chat_analyzer/application/qq/qq_provider_factory.py`
7. `src/qq_chat_analyzer/application/qq/qq_direct_database_import_service.py`
8. `src/qq_chat_analyzer/providers/napcat_qq_provider.py`
9. `src/qq_chat_analyzer/providers/qq_direct_snapshot_runtime.py`
10. `scripts/qq_napcat_plugin/bridge.mjs`
11. `scripts/qq_napcat_plugin/index.mjs`
12. `scripts/qq_napcat_runtime_pins.json`

**可选（防御性，各 2-3 行，13/14 含 pins）**
13. `src/qq_chat_analyzer/runtime/__init__.py`：直启路径 `environment.pop("ECHO_BRIDGE_TOKEN", None)`（防父进程残留被继承）
14. `scripts/qq_direct_db_snapshot/workspace.mjs`（+pins sha256）：PowerShell lease 子进程不再继承凭证（`env` 中 delete 后传 `{...env, ECHO_SNAPSHOT_LEASE}`）

**最小替代方案 B（若要求最小 diff）**
- 只改 3 个生产文件（8/9/4）+ 新增 1 个模块（内含 `default_qq_runtime_session()` 单槽访问器）+ 插件 3 文件 = 7 个文件。
- 具体差异：`QQProviderFactory` / `QQSetupService` / `QQDirectDatabaseImportService` / `default_runtime_factory` / `default_provider_builder` **不新增构造参数**，统一在内部按 `default_qq_runtime_session()` 取当前凭证（对齐 `default_qq_process_registry()` 的既有风格）。
- 代价：provider 与快照客户端之间是隐式共享状态，测试需要 `reset` fixture；与“显式注入”原则相比，可见性下降。
- **不计入**的方案：按 URL 索引的全局注册表（第 3.1 节）。

---

## 4. 凭证生命周期（按场景）

| 场景 | Session 动作 | 触发点（代码位置） |
|---|---|---|
| **首次启动**（点击连接） | `begin_launch()` 生成新凭证 → 注入 env → 成功提交 | `_start_auth_flow` → `_launch_window` → `_launch_auth_window:902-959` |
| **登录前探测** | 只读当前凭证 | `QQAuthBridge.get_snapshot` → `QQConnectionManager` → `provider.status()` |
| **重新连接**（断开后重连） | `disconnect()` → `_terminate_runtime_sessions()` → `retire()`；下次启动 `begin_launch()` 换新 | `qq_auth_bridge.py:405-417,484-508` |
| **取消授权** | `cancel_auth_flow()` → `_terminate_runtime_sessions()` → `retire()` | `qq_auth_bridge.py:170-181` |
| **重启前清理旧会话** | `terminate_all()` + `_clean_stale_runtime()` → `retire()`；随后 mint | `qq_auth_bridge.py:283-300` |
| **NapCat 异常退出** | 不猜测、不保留：`_launcher_process_alive()` 判定已死 → 下次启动走“retire → mint” | `qq_auth_bridge.py:241-242,467-482` |
| **Echo shutdown** | 顺序：Direct DB `recover`（用当前凭证）→ `shutdown_qq_runtime()`（terminate）→ `retire()` | `facade.py:1148-1178,576-587` |
| **setup.stop_runtime** | `QQRuntimeManager.stop()` → `retire()` | `qq_setup_service.py:270-275` |
| **启动失败** | `retire(刚生成的值)` —— 不留“没有对应实例”的凭证 | `qq_auth_bridge.py:960-990` |

不变量：
- **旧凭证不能用于新实例**：唯一 mint 点是 `begin_launch()`，且是替换（单槽），不存在“旧值仍可匹配新实例”的路径。
- **不使用旧凭证重试**：客户端只读当前值；401 直接报错，不做二次尝试、不回退无凭证请求、不做多凭证匹配。
- **cleanup/recover 不因凭证丢失而中断**：进程内 `cleanSlate()`/`plugin_cleanup` 路径（F12）不依赖凭证；应用侧 RPC 失败仍受既有有界窗口约束（`facade.py:1206-1259`），返回“可重试/终态”语义而不挂起。

---

## 5. 401 → 独立内部错误类型

| 位置 | 类型 | 映射条件 | 公共文案 |
|---|---|---|---|
| `napcat_qq_provider.py` | 新增 `NapCatQQAuthRejected(NapCatQQError)`，`code="napcat_qq_auth_rejected"` | `_request` 收到 HTTP **401** | **复用既有** `NapCatQQError.public_message`（“QQ local runtime is unavailable. Please finish QQ login and retry.”） |
| `qq_direct_snapshot_runtime.py` | 新增 `QQSnapshotRuntimeUnauthorized(QQSnapshotRuntimeError)`，`code="qq_snapshot_runtime_unauthorized"` | `_unwrap_rpc` 的 `status == 401` | **复用既有** `QQSnapshotRuntimeUnavailable.public_message` |

边界（避免扩大重构范围）：
- 只新增类型 + 只映射 401；**不修改**任何既有 `except` 结构：`QQConnectionService` 的 catch-all、`QQDirectDatabaseImportService` 的 `except QQSnapshotRuntimeError` 全部保持原样（新类型是其子类）。
- 捕获点仅限既有的 3 处身份探针（F6）：命中时沿用既有 `RuntimeIdentityMismatch` / `qq_runtime_identity_mismatch` / `healthy=False`，**不新增 UI 文案**。
- 公共提示只包含稳定 code 与既有中文/英文文案；**不含凭证、URL、端口、路径、UIN**（RED 中显式断言）。

---

## 6. 环境继承 / 日志脱敏 / fail-closed 核查

| 项 | 结论 |
|---|---|
| Echo 自身环境 | 【事实】从不写入凭证（F10）；与微信 key 先例（F9）刻意区分 |
| 子进程环境 | 仅 `_launch_auth_window` 的局部 env dict 携带；`pop-then-set` 防父进程/上次运行残留被继承（与 `ECHO_RUNTIME_ID` 同构） |
| 孙进程继承 | 【事实】`workspace.mjs` 的 PowerShell lease 子进程会继承 → 可选加固（文件 14）；【假设 A3】NapCat 自身不打印 env |
| 日志 | 【事实】启动链路日志不含 env（F11）；新增代码禁止打印凭证；`QQRuntimeSession.__repr__` 脱敏；RED 断言 caplog 全文不含凭证 |
| 配置文件 | 【事实】`QQEnvironmentConfigWriter.save` payload 不含凭证字段；RED 断言 `qq.json` 前后字节一致且不含凭证 |
| 报告/导出 | 不经过 bridge 凭证；`Core.status` 响应不新增凭证字段 |
| 客户端 fail-closed | 凭证为 `None` → 客户端**不发送请求**（直接抛错）；凭证过期/不符 → 401 → 独立错误类型 → 既有提示；**无任何降级为无认证请求的代码路径** |
| 剩余暴露面 | 同用户进程/管理员可读进程环境（已接受，第一轮 §6 已说明）；凭证与端口绑定、每次启动轮换、随实例终止失效 |

---

## 7. managed / custom 兼容性结论

**Echo 自身代码内的不变量（本方案保证）**
1. Echo 发出的每一个 bridge RPC 都带 `Authorization: Bearer <当前凭证>`。
2. 凭证不可用时**不发送请求**（本地 fail-closed），不存在无认证回退。
3. 服务端（Echo 自己的插件）在凭证缺失/非法时**不启动 bridge**，不存在无认证监听模式。

**custom 模式（不得静默破坏）**
- 【事实】custom 与 managed 共用同一启动函数、同一端口、同一 RPC 形状（§2.1）。
- 因此本方案**不改变** custom 的连接能力：旧插件忽略新增头 → 行为与今天完全一致；新插件则同样受保护。
- 【事实】生产代码无 GUI 入口产生 custom（F5）；custom 仅来自历史 `qq.json` 或手工编辑（【假设 A2】）。
- **残余风险（需在发布说明中写明）**：自定义运行时目录里若是旧版插件，该 bridge 自身没有认证能力，Echo 无法证明。若要“Echo 绝不与未认证 bridge 通信”，唯一可行手段是能力探测（`Core.status` 增量字段），但那会**破坏 custom + 旧插件**的连接，与本次约束冲突 → **本轮不做**，列为后续独立决策。

---

## 8. 最小修改文件集（必需 12 + 可选 2）

| # | 文件 | 改动要点 |
|---|---|---|
| 1 | `src/qq_chat_analyzer/application/qq/qq_runtime_session.py`（新） | `QQRuntimeSession`（begin_launch/credential/retire/脱敏 repr）+ `default_qq_runtime_session()` |
| 2 | `src/qq_chat_analyzer/gui/app.py` | 创建 session；`build_facade(qq_runtime_session=…)`；`_qq_bundle_factory(session)`；provider factory / Direct DB / setup 注入 |
| 3 | `src/qq_chat_analyzer/application/facade.py` | 新增 `qq_runtime_session` 参数；`_require_qq_auth_bridge` 传入；`shutdown()` 末尾 `retire()` |
| 4 | `.../application/qq/qq_auth_bridge.py` | `QQAuthBridge(credential=…)`；`default_auth_window_launcher(..., credential=…)`；`_launch_auth_window` mint/pop-set/失败 retire；`_terminate_runtime_sessions` → retire；探针传凭证 |
| 5 | `.../application/qq/qq_setup_service.py` | `QQSetupService(bridge_credential=…)`；`default_runtime_factory(..., credential=…)`；两处探针传凭证；`stop_runtime` → retire |
| 6 | `.../application/qq/qq_provider_factory.py` | `QQProviderFactory(bridge_credential=…)`；`default_provider_builder(config, credential=…)` |
| 7 | `.../application/qq/qq_direct_database_import_service.py` | `bridge_credential=…`；`_require_runtime_client()` 传凭证 |
| 8 | `.../providers/napcat_qq_provider.py` | `credential=…`；`_request` 请求时刻取凭证 + 401 → `NapCatQQAuthRejected`；无凭证不发请求；`snapshot_client()` 透传 |
| 9 | `.../providers/qq_direct_snapshot_runtime.py` | `credential=…`；默认 transport 加头；`_unwrap_rpc` 401 → `QQSnapshotRuntimeUnauthorized` |
| 10 | `scripts/qq_napcat_plugin/bridge.mjs` | `token` 必填 + `^[0-9a-f]{64}$`；所有方法统一前置校验 → `401 invalid_credential`；`timingSafeEqual`；不回显凭证 |
| 11 | `scripts/qq_napcat_plugin/index.mjs` | 读 `ECHO_BRIDGE_TOKEN`；缺失/非法 → `throw echo_bridge_token_missing`（不注册、不监听）；传入 `startBridge` |
| 12 | `scripts/qq_napcat_runtime_pins.json` | 更新 `index.mjs` / `bridge.mjs` 两个 `sha256` |
| 13 | （可选）`src/qq_chat_analyzer/runtime/__init__.py` | 直启回退路径 pop 残留 `ECHO_BRIDGE_TOKEN` |
| 14 | （可选）`scripts/qq_direct_db_snapshot/workspace.mjs` + pins | lease 子进程不继承凭证 |

---

## 9. RED 测试清单

约定：仅虚构数据；服务端用真实 `bridge.mjs` + 虚构 core/snapshot；凭证用虚构值。

**S. 服务端统一认证（`tests/test_napcat_qq_provider.py`，Fast，需 node）**
- S1 无凭证调用 `Core.status` → 401 `invalid_credential`，且 core API 调用计数为 0。
- S2 错误凭证调用 `EchoMetadata.listFriends` / `listGroups` / `GroupApi.getGroupMemberAll` → 401，core 调用计数为 0。
- S3 无凭证调用 `EchoSnapshotApi.acquire` / `cleanup` / `recover` → 401，snapshot 调用计数为 0（无明文落盘）。
- S4 `/rpc/<正确 runtime_id>` 无凭证 → 401（凭证与 runtime 绑定是两条独立防线）。
- S5 `startBridge` 缺 token / token 形状非法 → 抛错且未监听端口。
- S6 401 响应体不含凭证（含前缀/长度信息）。
- S7 既有边界用例（Origin/Host/Content-Type/大小/路由/参数/既有方法白名单）在携带正确凭证时行为不变。

**P. 插件 fail-closed（`tests/test_qq_napcat_runtime_bootstrap.py`）**
- P1 `ECHO_BRIDGE_TOKEN` 缺失 / 非法 → `plugin_init` 抛 `echo_bridge_token_missing`，bridge 未启动。
- P2 既有 `echo_snapshot_root_missing` 语义与顺序不变。
- P3 `plugin_cleanup` 在无凭证场景仍完成进程内 recover。

**R. Session 与生命周期（新增 `tests/test_qq_runtime_session.py` + 既有 auth/close 测试）**
- R1 `begin_launch()` 返回 64-hex；两次调用值不同；单槽（不累积历史）。
- R2 `retire()` 后 `credential()` 为 None；`retire(非当前值)` 不清空当前。
- R3 启动失败（OSError / returncode≠0）→ 不残留凭证。
- R4 `disconnect()` / `cancel_auth_flow()` → 凭证被 retire，随后的探测不发送请求。
- R5 `Facade.shutdown()` 事件顺序：Direct DB recover（带凭证）→ terminate → retire。
- R6 无凭证时 Direct DB shutdown recover 失败有界且被记录（不挂起）——扩展既有 shutdown 测试。

**I. 注入（`tests/test_qq_runtime_wiring.py`、`tests/test_qq_setup_service.py`、`tests/test_qq_auth_bridge.py`）**
- I1 启动 env 含合法 `ECHO_BRIDGE_TOKEN`，等于 session 当前值，且不等于父进程 env 中的同名值。
- I2 缓存的 provider 在第二次启动后使用**新**凭证（请求时刻读取，非构造时刻）。
- I3 Direct DB 构造的 snapshot client 携带凭证（`/rpc` 与 `/rpc/<runtime_id>` 两种形态）。
- I4 三处临时探针（F6）携带凭证，managed 身份校验成功。
- I5 无凭证 → provider 未发出任何 HTTP 请求（transport spy 计数 0）。
- I6 401 → `NapCatQQAuthRejected`，且**只发送 1 次**请求（无重试、无旧凭证回退）。

**E. 端到端（`tests/test_qq_runtime_wiring.py::test_python_and_js_plugin_share_snapshot_root_and_refuse_old_clients`，slow_integration）**
- E1 携带 `seen[0]["ECHO_BRIDGE_TOKEN"]` 的客户端可完成 recover/acquire/cleanup。
- E2 无凭证客户端（含旧客户端形态）一律被拒 → 强化该测试原有“旧客户端被拒”的意图。
- E3 错误凭证 + 错误 runtime_id 同时存在时仍被拒。

**V. 隐私与发布合同**
- V1 启动 + 探测 + 401 失败后，`caplog` 全文不含凭证。
- V2 `qq.json` 前后字节一致且不含凭证；用户数据目录内不出现凭证字面量。
- V3 pins 中 `index.mjs` / `bridge.mjs` 的 sha256 与实际文件一致（`test_qq_napcat_runtime_bootstrap.py` 既有断言自动覆盖）。
- V4 所有新增公共文案不含凭证/URL/端口/路径/UIN（对新增错误类型断言 `code` 与 `public_message`）。

---

## 10. 环境（第 7 项已执行）

| 项 | 结果 |
|---|---|
| 路径 | `D:\ChatAnalyzerWorkspace\wt-napcat-rpc-auth\.venv`（`.gitignore:22` 已忽略，不会进入提交） |
| 解释器 | Python 3.13.9（基础解释器 `D:\python\python.exe`），pip 25.2 |
| 安装 | `pip install -e ".[dev]"`（含 pytest 8.4.2） |
| 包解析 | `import qq_chat_analyzer` → `D:\ChatAnalyzerWorkspace\wt-napcat-rpc-auth\src\qq_chat_analyzer\__init__.py`（**本工作树**，非主工作树） |
| focused 基线 | `pytest tests/test_napcat_qq_provider.py tests/test_qq_napcat_runtime_bootstrap.py tests/test_qq_runtime_wiring.py tests/test_qq_auth_bridge.py tests/test_qq_setup_service.py tests/test_qq_direct_db_snapshot_runtime.py -m "not slow_integration and not known_failure"` → **116 passed, 37 deselected** |
| slow_integration 基线 | `pytest tests/test_qq_runtime_wiring.py -m slow_integration` → **5 passed**（真实 node/插件路径可用） |

后续命令统一使用：

```powershell
cd d:/ChatAnalyzerWorkspace/wt-napcat-rpc-auth
.\.venv\Scripts\python.exe -m pytest <focused files> -q
.\.venv\Scripts\python.exe -m pytest -m "not slow_integration and not known_failure" -q
.\.venv\Scripts\python.exe -m pytest -q
```

---

## 11. 待批准项（收敛后的开放问题）

1. **方案选择**：主方案 A（12 文件，显式注入 + 工厂默认访问器兜底）vs 最小替代 B（7 文件，统一走 `default_qq_runtime_session()`）。
2. **custom 严格程度**：接受“旧插件忽略凭证”的残余并写入发布说明（推荐）vs 增加 `Core.status` 能力字段并因此**破坏 custom+旧插件**（与本次约束冲突，默认不做）。
3. **可选加固 13/14** 是否纳入本轮（各 2-3 行；14 会改动 pins 覆盖文件）。
4. **真机验收范围**（A1/A3）：是否在本任务内做一次“强杀 Echo → 端口/进程残留检查 + NapCat 日志脱敏抽查”。

以上确认后进入 TDD（RED → GREEN → focused → full → `git diff --check`）。
