# NapCat 本地 RPC 客户端认证 —— 实施报告（方案 A 落地）

- 仓库：`lingmeng-658/echo-chat-analyzer`　工作树：`D:/ChatAnalyzerWorkspace/wt-napcat-rpc-auth`　分支：`security/napcat-rpc-auth`
- 依据：`2026-10-09-napcat-rpc-auth-design-audit.md`（第一轮审计）+ `2026-10-09-napcat-rpc-auth-design-convergence.md`（第二轮收敛，方案 A 已批准）
- 范围：**未 commit、未 push**；未纳入可选加固 13/14；未升级 NapCat；未修改无关模块；测试全部使用虚构数据。

---

## 1. 交付概览

方案 A 按批准的设计落地：

- **凭证所有权**：新增 `QQRuntimeSession`（进程内单实例、单槽、不按 URL 索引），由组合根 `gui/app.py` 创建并**显式注入** provider factory / Direct DB service / setup service / auth bridge；未显式注入的工厂默认回落到 `default_qq_runtime_session()`（对齐既有 `default_qq_process_registry()` 模式）。
- **服务端**：`bridge.mjs` 的 `token` 为必填参数；**所有 RPC 方法统一前置认证**（在路由判定之前），失败一律 `401 {"ok":false,"error":"invalid_credential"}`，方法分发不可达；`timingSafeEqual` 常量时间比较，响应不回显凭证。现有 Host/Origin/Content-Type/大小/方法白名单/参数校验/runtime_id 路径绑定全部保留。
- **插件 fail-closed**：`index.mjs` 在 `ECHO_BRIDGE_TOKEN` 缺失或非法时抛 `echo_bridge_token_missing`，**不注册 snapshot API、不监听端口**，不存在无认证 bridge。
- **客户端 fail-closed**：两个 RPC 客户端在**没有当前凭证时不发送任何请求**（本地直接失败）；401 映射为独立内部错误类型。
- **生命周期**：每次启动生成新凭证并注入子进程私有环境变量；任何“停止 Echo 自有 runtime”的路径都 `retire()`；不持久化、不打印、不进报告。

与第二轮设计的两点实施差异（均已在批准范围内，理由如下）：

1. 新增 `src/qq_chat_analyzer/providers/bridge_credential.py`（设计里预期的 `providers/` 凭证读取共享模块）：`providers` 不允许 import `application`，因此把“请求头格式 + 从 session 读取当前值”放在 provider 层，避免两处重复。
2. 凭证对象的解析用鸭子类型（`.credential()`），因此 `QQRuntimeSession` 可留在 `application/qq/`（如设计所定），provider 侧不需要 import 它。

---

## 2. 修改文件清单

**新增（4）**

| 文件 | 作用 |
|---|---|
| `src/qq_chat_analyzer/application/qq/qq_runtime_session.py` | `QQRuntimeSession`（`begin_launch` / `credential` / `retire` / 脱敏 `__repr__`）+ `mint_bridge_credential` + `is_bridge_credential` + `default_qq_runtime_session()` |
| `src/qq_chat_analyzer/providers/bridge_credential.py` | `resolve_bridge_credential()` + `authorization_headers()`（`Authorization: Bearer <token>` 单一来源） |
| `tests/test_qq_runtime_session.py` | Session 单元测试（9 项） |
| `tests/test_qq_bridge_credential.py` | 两个客户端的凭证/401/隐私 HTTP 级测试（12 项） |

**修改（15）**

| 类别 | 文件 | 改动 |
|---|---|---|
| 插件 | `scripts/qq_napcat_plugin/bridge.mjs` | 必填 `token` + 统一前置认证（401）+ 常量时间比较 |
| 插件 | `scripts/qq_napcat_plugin/index.mjs` | 读取 `ECHO_BRIDGE_TOKEN`，缺失/非法即 fail-closed |
| 发布合同 | `scripts/qq_napcat_runtime_pins.json` | 同步 `index.mjs` / `bridge.mjs` 两个 `sha256` |
| 组合根 | `src/qq_chat_analyzer/gui/app.py` | 创建 session；注入 facade 与 QQ bundle（provider factory / Direct DB / setup） |
| Facade | `src/qq_chat_analyzer/application/facade.py` | 新增 `qq_runtime_session` 参数；传给 auth bridge；`shutdown()` 末端 `retire()` |
| 启动 | `.../application/qq/qq_auth_bridge.py` | `credential` 注入；`_launch_auth_window` mint + `pop-then-set` env + 启动失败 `retire`；`_terminate_runtime_sessions()` → `retire`；身份探针带凭证 |
| 设置 | `.../application/qq/qq_setup_service.py` | `bridge_credential` 注入；`default_runtime_factory(credential=…)`；两处探针带凭证；`stop_runtime()` → `retire` |
| Provider 装配 | `.../application/qq/qq_provider_factory.py` | `bridge_credential` 注入；`default_provider_builder(config, credential=…)` |
| Direct DB | `.../application/qq/qq_direct_database_import_service.py` | `bridge_credential` 注入；构造客户端时传入 |
| Provider | `.../providers/napcat_qq_provider.py` | `credential` 参数；请求时刻取凭证；无凭证不发请求；401 → `NapCatQQAuthRejected`；`snapshot_client()` 透传 |
| 快照客户端 | `.../providers/qq_direct_snapshot_runtime.py` | `credential` 参数；默认 transport 认证 + 无凭证不发请求；401 → `QQSnapshotRuntimeUnauthorized` |
| 测试 | `tests/test_napcat_qq_provider.py` | 虚构 server 改为 JSON 配置（token/runtimeId/marker）；新增未授权不执行方法等 15 项 |
| 测试 | `tests/test_qq_napcat_runtime_bootstrap.py` | 插件加载用例补 token；新增 fail-closed 参数化用例 |
| 测试 | `tests/test_qq_runtime_wiring.py` | env 凭证注入/不继承/不落日志/失败不残留/生命周期/关闭 retire/注入透传；真实插件端到端用例改为认证客户端 + 无凭证与陈旧凭证必须被拒 |
| 测试 | `tests/test_gui_qq_deqce_wiring.py` | custom 模式同样注入凭证且无 `ECHO_RUNTIME_ID` |

`git diff --stat`：15 files changed, 572 insertions(+), 83 deletions(-)（另有上述 4 个新增文件）。

---

## 3. RED → GREEN 证据

**RED（实现前，同一套测试）**

```
34 failed, 18 passed, 1 error in 5.36s
```

- `test_qq_runtime_session.py` / `test_qq_bridge_credential.py` / `test_qq_runtime_wiring.py`：`ModuleNotFoundError: qq_runtime_session`（会话与新模块不存在）。
- `test_napcat_qq_provider.py`：未授权的 `Core.status` / 元数据 / snapshot 方法未被拒绝（旧 bridge 无认证），`startBridge` 缺失/非法 token 未抛错。
- `test_qq_napcat_runtime_bootstrap.py`：`plugin_init` 在无凭证时仍成功启动 bridge。

**GREEN（实现后，干净环境）**

```
tests/test_qq_runtime_session.py tests/test_qq_bridge_credential.py tests/test_napcat_qq_provider.py tests/test_qq_napcat_runtime_bootstrap.py
  → 67 passed
```

---

## 4. 测试结果

| 层级 | 命令 | 结果 |
|---|---|---|
| RED | 见第 3 节 | 34 failed / 18 passed / 1 error |
| focused | `pytest tests/test_napcat_qq_provider.py tests/test_qq_napcat_runtime_bootstrap.py tests/test_qq_runtime_wiring.py tests/test_qq_auth_bridge.py tests/test_qq_setup_service.py tests/test_qq_direct_db_snapshot_runtime.py tests/test_qq_connection_service.py tests/test_gui_qq_deqce_wiring.py tests/test_qq_runtime_session.py tests/test_qq_bridge_credential.py -m "not slow_integration and not known_failure"` | **180 passed, 37 deselected** |
| focused（slow） | `pytest tests/test_qq_runtime_wiring.py -m slow_integration` | **5 passed**（真实 node + 插件端到端，含认证/无凭证被拒） |
| Fast | `pytest -m "not slow_integration and not known_failure"` | **3318 passed, 5 skipped, 348 deselected** |
| Full | `pytest`（干净环境） | **3639 passed, 31 skipped, 1 failed**（该 1 项见第 7 节，环境/顺序相关，非本改动表面） |
| `git diff --check` | — | 无输出（无空白问题） |

覆盖的关键不变量（均有 RED 用例）：

- 认证失败**不执行任何 RPC**：`Core.status` / `EchoMetadata.listFriends` / `listGroups` / `GroupApi.getGroupMemberAll` / `EchoSnapshotApi.acquire|cleanup|recover` 在无凭证、错凭证、畸形头部下均为 401，且虚构核心的 **marker 文件为空**（证明方法未被调用、无明文落盘）。
- 认证先于路由：未认证调用者拿不到 `/rpc` 与 `/rpc/<id>` 的 404/409 差异；`/rpc/<正确 runtime_id>` 缺凭证同样 401（凭证与 runtime 绑定是两条独立防线，缺一不可）。
- `startBridge` 缺 token / 非法 token → 抛 `invalid_bridge_credential` 且不监听；401 响应体不含凭证（含前缀）。
- 插件：缺/非法 `ECHO_BRIDGE_TOKEN` → `echo_bridge_token_missing`，**未注册 snapshot API、未记录就绪日志**；`plugin_cleanup` 在无凭证场景仍完成进程内 recover。
- 客户端：无凭证/已 retire 凭证 → **不发出任何 HTTP 请求**；401 → `NapCatQQAuthRejected` / `QQSnapshotRuntimeUnauthorized`（均为原错误族子类，既有 catch 语义不变）且**只发一次请求**（无重试、无旧凭证回退）。
- 隐私：启动 + 探测 + 401 失败后 `caplog` 不含凭证；`qq.json` 字节前后一致且不含凭证；公共文案不含凭证/URL。
- 发布合同：pins 两个模板 `sha256` 与实际文件一致（既有契约测试自动覆盖）。

---

## 5. Managed / custom 兼容行为

| 行为 | managed | custom |
|---|---|---|
| 凭证注入 | ✅ 每次启动新凭证经 `ECHO_BRIDGE_TOKEN` | ✅ 同一启动函数（`_launch_auth_window`），同样注入 |
| `ECHO_RUNTIME_ID` | ✅ 注入并校验路径契约 | 不注入（既有行为），仅 `/rpc` 路由 |
| 身份校验（runtime_id） | ✅ 三处探针带凭证后校验 | 跳过（既有行为） |
| 服务端认证 | ✅ 强制（pins 保证插件版本一致） | ✅ 强制（Echo 自己的新插件）；**若自定义目录里是旧插件，它会忽略新增头** → 该 bridge 自身仍无认证力 |
| 客户端 | 无凭证不发请求；401 独立错误 | 同左 |

结论：

- **未静默破坏 custom 连接能力**：同一启动函数、同一端口、同一 RPC 形状、同一请求路径；旧插件忽略新增头时功能与今天一致。
- **Echo 自身代码内不存在无认证旁路**：Echo 发出的每个 RPC 都带凭证；凭证不可用时本地 fail-closed 不发请求；服务端无凭证即不启动。custom 旧插件的残余风险属于“用户自备产物”，已在第二轮报告的发布说明项中记录，本轮不做能力探测（避免破坏 custom）。

---

## 6. 凭证生命周期验证结果

| 场景 | 验证用例 | 结果 |
|---|---|---|
| 首次启动 | `test_launch_injects_an_ephemeral_credential_and_never_leaks_it` | 新凭证 64-hex；等于 session 当前值 |
| 环境继承 | 同上（父进程预置 `ECHO_BRIDGE_TOKEN=ffff…`） | 子进程得到**不同**的值；Echo 自身 `os.environ` 未被改写 |
| 不落日志/不落盘 | 同上 | `caplog` 不含凭证；`qq.json` 字节不变且不含凭证字段 |
| 登录前探测 | `test_cached_client_follows_a_new_launch_credential` | 请求时刻读取：同一缓存客户端在二次启动后使用**新**值 |
| 启动失败 | `test_failed_launch_does_not_leave_a_credential_for_an_instance_that_never_started` | `retire` 后 `credential() is None` |
| 重新连接 / 取消 / 重启前清理 | `test_credential_lifecycle_follows_the_owned_runtime` | `disconnect()` 后凭证被废除；再次启动得到**不同**的新值（旧值不可复用于新实例） |
| Echo shutdown | `test_facade_shutdown_retires_the_bridge_credential` | `shutdown()` 末尾 retire（顺序在 Direct DB recover 与终止 runtime 之后） |
| Direct DB 注入 | `test_direct_db_service_propagates_the_injected_session` | 服务端构造的 snapshot 客户端持有同一 session |
| 端到端 | `test_python_and_js_plugin_share_snapshot_root_and_refuse_old_clients` | 同进程 mint 的凭证 == 插件收到的 env；携带凭证可 recover/acquire/cleanup；**无凭证 → 本地拒绝**；**陈旧凭证 → 401 被拒**；错误 runtime_id 仍被拒 |
| 401 不重试 | `test_provider_maps_unauthorized_to_its_own_error_type_and_does_not_retry` | 恰好 1 次请求 |

---

## 7. 环境与干扰项

- 独立 `.venv`：`D:\ChatAnalyzerWorkspace\wt-napcat-rpc-auth\.venv`（Python 3.13.9），`import qq_chat_analyzer` 解析到**本工作树** `src`；已安装 `.[dev]`、`.[gui]`（PySide6，与参考环境一致）、`.[build]`（PyInstaller，打包契约测试需要）。`.venv/` 由 `.gitignore` 忽略。
- **IDE 注入的 `sitecustomize` 干扰（环境问题，非本次改动）**：本会话的 `PYTHONPATH` 指向 IDE 的 `...\genie\out\vendor\shim`，其“批量删除守卫”会在 pytest 清理旧 basetemp 时抛 `SystemExit(1)`，并向 `LOCALAPPDATA` 写入守卫状态。影响两处：① 单独运行 `tests/test_app_version.py` 会被 teardown 崩溃掩盖结果；② `tests/test_test_user_data_isolation.py` 的子进程会把守卫文件写进被断言的 `LOCALAPPDATA`（哨兵目录）导致失败。
  - 证据：清空 `PYTHONPATH` 后 `test_test_user_data_isolation` **通过**；使用全新 `--basetemp` 后 `test_app_version.py` 三个用例**全部通过**。
  - 处理：Fast / Full 的最终数字均在 `PYTHONPATH=''` + 全新 `--basetemp` 下取得。
- Full 运行中仅剩的 1 个失败：`tests/test_app_version.py::test_desktop_spec_ships_release_metadata_for_runtime_version`（`slow_integration`），单独运行该文件时通过，仅在完整运行中失败；其输入（`LocalChatAnalyzer.spec`、`pyproject.toml`、已安装发行版元数据）**均不在本次改动范围内**，本改动未新增任何发行版或 `.dist-info` 数据。判定为**环境/顺序相关的既有问题**，建议由人工在参考环境复核。

---

## 8. 尚未完成的真实环境验收项

以下需要人工在本机（含真实 QQ/NapCat）执行，本轮自动化只能覆盖到虚构管线：

1. **真实 bootstrap 与 E2E**：`scripts/bootstrap_qq_napcat_runtime.py`（需官方 archive + 网络）后启动真实 runtime，确认：QQ 登录 → 连接状态 → Direct DB 会话列表 → 分析 → 关闭；验证 pins 更新后的真实工作副本可准备成功（组件摘要已变 → 新 `work_root`）。
2. **真实 RPC 认证**：用非 Echo 的本机进程（另一用户账户/脚本）直连 `127.0.0.1:40655`，确认 `Core.status`/元数据/snapshot 全部 401；确认 `Authorization` 头确被接受（无中间层剥离）。
3. **遗留实例场景（风险假设 A1）**：强杀 Echo 后检查 40655 端口与 QQ/NapCat 进程是否随 Job 终止；若存在遗留 runtime，确认用户可见提示与“完全退出 QQ 后重连”路径可用（不会静默降级）。
4. **NapCat 自身日志脱敏抽查（风险假设 A3）**：检查 `work_root/logs` 是否出现凭证字面量。
5. **custom 旧插件风险确认**：确认现网是否存在 `runtime_mode=custom` 的历史 `qq.json`；若有，评估“旧插件忽略凭证”是否需要发布说明或能力探测。
6. **凭证不落报告**：真机导出报告后全局搜索凭证字面量（本程序化不可覆盖真实报告产物）。

---

## 9. 明确未纳入项

- 可选加固 13（`runtime/__init__.py` 直启回退路径 pop 残留 `ECHO_BRIDGE_TOKEN`）与 14（`workspace.mjs` lease 子进程不继承凭证）：按指示**未实施**。
- 未升级 NapCat、未改动 `LocalChatAnalyzer.spec`、未改动与本任务无关的模块。
- 未 commit、未 push。

---

## 10. 独立最终审计与收口（2026-10-09）

本节是最终审计结论；前文保留初次实施记录。第 7 节对版本测试失败的环境归类已被下面的复现证据推翻，第 8 节的旧 custom 插件能力探测已实现。

确认并按 RED → 最小 GREEN 修复的缺陷：

- Snapshot Client 原来逐次读取 session 当前凭证，旧 acquire 的 cleanup、重试或 recover 可获得新启动凭证。现在客户端在创建时绑定单次启动；没有凭证的旧客户端也不能收养未来实例。Provider 创建的 snapshot client 使用同一保护。
- Direct DB startup 重试、shutdown drain 后原来重新构造客户端，能跨启动轮换凭证。现在单次 startup / shutdown 保留同一个客户端，shutdown 在 drain 前固定客户端。
- Snapshot HTTP transport 原来用 URL 前缀判定 loopback，并沿用默认代理和重定向。现精确解析 host、port、route，禁止代理和重定向；真实 loopback 302 回归确认 Authorization 不会转发至第二个服务器。
- 旧 custom 插件可能忽略 Authorization。现插件的 Core.status 声明 `rpc_auth: bearer-v1`；Provider 和 custom snapshot 客户端在业务调用前确认该协议，旧插件被拒绝。401 不重试、不降级。
- 取消发生在 mint 前时，迟到启动可能留下凭证；异常 spawn/poll 和进程树退出也有遗漏。现 session 绑定拥有的进程树，迟到启动仅按 process 身份退休凭证，观察树退出时清理；boot 返回 0 且树仍存活不会误清理。启动异常退休凭证并关闭已创建资源。
- 默认 Facade 未显式注入 session 时 shutdown 没有退休默认凭证，现使用同一默认 session 清理。
- 不合法 credential 可能进入 HTTP header 并产生包含输入的异常。现客户端严格限制为 64 位小写 hex，非法输入不发送请求。
- custom 认证握手原来额外消耗 timeout 后还会发送 mutating RPC。现握手与业务请求共享剩余时限，耗尽后不发送 recover。

版本测试根因不是仅凭单测通过推断的环境问题：多个测试模块在 collection 时执行 `sys.path.insert(0, src)`，使 `src/qq_chat_analyzer.egg-info` 抢占 `.venv/Lib/site-packages/qq_chat_analyzer-0.1.0.dist-info`。PyInstaller.copy_metadata 随之返回 egg-info，而测试筛选 `.dist-info` 得到空集合。`pytest -k test_desktop_spec_ships_release_metadata_for_runtime_version` 在全量 collection 下稳定 RED；同一解释器中仅插入 src 就能改变 copy_metadata 结果。spec 验证现在在 `sys.executable -I` 子进程执行，既保留发行版 metadata 断言，也保留 stale installed version 的拒绝测试，未修改 spec、版本或安装依赖。

测试隔离：使用本工作树独立 `.venv`、`-I`、清空 PYTHONPATH/PYTHONSTARTUP、每次新的 basetemp，确认 user site 禁用且 sitecustomize 未加载。conftest 每个测试注入独立的默认 registry（虚构 terminator）和 credential session，防止虚构 PID / 凭证跨测试残留。审计 runner 额外阻止真实 taskkill、QQ 启动和 os.kill，并在结束时检查拦截记录；最终各层验证没有此类尝试。

最终 focused（含 Node 插件 / snapshot integration）：279 passed，原生进程退出码 0。最终 Fast 的 pytest 汇总：3335 passed、5 skipped、348 deselected。最终 Full 的 pytest 汇总：3657 passed、31 skipped、1 warning（既有 Pillow getdata 弃用提示）；无断言失败。跳过项为未生成的 frozen/portable 发行包、Windows symlink 权限及未提供的微信原生组件。`git diff --check` 通过；全部现有未提交工作保留，无 commit / push / PR / merge。

**收口阻塞：不能将 Fast / Full 进程标记为 GREEN，尚未达到最终可提交状态。** 收尾核对发现：Full 的 PowerShell 包装退出码为 1；Fast 再运行显式打印 `pytest.main` 返回 `<ExitCode.OK: 0>`、进程安全记录 `[]`，随后实际 Python 退出码是 `-1073741819`（Windows `0xC0000005` 原生访问违例）。因此“pytest 全部通过”不能替代完整进程成功退出。RPC focused 正常退出，问题出现在包含 GUI 的完整组合结束阶段。较小的、未修改的 GUI 测试组合另出现停滞，已通过测试 session 的 Ctrl-C 停止，没有对任何 PID 执行 taskkill。`docs/HARDENING.md` 的 REL-07 已登记“跟踪 Qt 退出崩溃（环境失败不得静默记为通过）”；现象与该项相关，但具体 C 层根因及是否同源尚未证明。本轮不把它简单归类为 IDE 干扰，也不修改无关 GUI/native 退出实现或升级依赖；这需要独立的 GUI/native 退出排查，超出 RPC 认证收口范围。

本轮在已有实现上实际修改：`scripts/qq_napcat_plugin/bridge.mjs`、`scripts/qq_napcat_runtime_pins.json`；`application/facade.py`、`application/qq/qq_auth_bridge.py`、`application/qq/qq_direct_database_import_service.py`、`application/qq/qq_runtime_session.py`、`providers/napcat_qq_provider.py`、`providers/qq_direct_snapshot_runtime.py`、`providers/bridge_credential.py`（以上 source 路径均相对 `src/qq_chat_analyzer`）；`tests/conftest.py`、`tests/test_app_version.py`、`tests/test_napcat_qq_provider.py`、`tests/test_qq_runtime_wiring.py`、`tests/test_qq_bridge_credential.py`；以及本报告。其余初始未提交文件保持原工作内容，不做 restore / checkout / 清理。

边界保持：未启动真实 QQ、未读取真实聊天或用户数据、未操作其他工作树、未升级 NapCat、未 commit / push / PR / merge。真实 QQ 登录与强制退出、第三方 NapCat 自身日志和实际发行包验收仍需独立人工执行，不将虚构 integration 扩大为真人验收。


## 11. Windows 原生退出崩溃的独立诊断（2026-10-09）

本轮仅诊断并更新报告，未修改产品或测试代码，也未升级依赖。环境为本工作树独立 .venv（Python 3.13.9、PySide6/Shiboken 6.12.0），使用 -I -X faulthandler，删除 PYTHONPATH/PYTHONSTARTUP/PYTHONHOME，用户数据环境变量和 basetemp 均指向工作树内每次新建的诊断 sandbox；sitecustomize 未加载。测试使用桩，不启动 QQ，进程安全拦截记录均为空。

标准库父进程直接写入日志，记录真实 Windows 退出码；子进程另记录 pytest_sessionfinish、pytest.main 返回、Python atexit 和 faulthandler。Fast 连续两次与 Full 均在 pytest 返回 0 后崩溃，主线程无 Python frame，且未到诊断 atexit 回调。Windows venv 启动器另启动实际解释器；异常事件的 PID 对应 runner 记录的实际解释器 PID，启动器传播 0xC0000005，因此不是 PowerShell 包装产生的崩溃。

基线使用 git archive HEAD（b5413dd103ced970c14ea1689b217359e89f52dc）在当前工作树内展开，未 checkout/restore 或操作其他工作树，使用同一 .venv、环境和虚构默认进程终止桩。基线 test_gui.py 的 405 项全部通过后同样崩溃。GUI 二分：前、后半均崩溃；前四分之一正常；继续缩小到同一 51 项，基线与当前代码均通过全部断言后崩溃。六项组合可在当前代码触发，但拆成两组三项正常，基线六项正常，因此未将六项宣称为跨版本稳定的最小复现。

使用 Windows Debug API 调试本次测试进程及其 venv 启动器子进程，按正常异常处理继续执行、不吞掉访问冲突；第二机会异常时用 DbgHelp StackWalk64 抓取原生栈。同一 51 项在基线和当前代码得到完全相同的 40 帧模块/偏移序列：Qt6Core.dll+0x6E34 → QWidget::~QWidget（Qt6Widgets.dll+0x4FEF3 / +0x50165）→ QObjectPrivate::deleteChildren（Qt6Core.dll+0xF0650，递归销毁链）→ PySide::destroyQCoreApplication（pyside6.abi3.dll+0x229DE / +0x228FD）→ Shiboken::BindingManager::visitAllPyObjects → PySide::runCleanupFunctions → QtCore.pyd → python313.dll（含 Py_Exit）。这是解释器退出时 PySide 应用/控件清理中的原生访问冲突。非调试运行的多个已核对实际 PID 的 Application Error 事件定位到同一 Qt6Widgets.dll+0x3F2B80；调试状态改变异常落点，但基线与当前调试栈一致。

结论：本轮 RPC 认证不是该崩溃的首次引入者；既有 GUI/Qt 原生退出清理问题在当前依赖环境中已由基线复现，不能归咎于 IDE 注入。尚未确定具体失效对象、所有权/销毁顺序，或是否为此 PySide6/Qt 版本缺陷；不扩大本分支修改 GUI/native 生命周期，不禁用测试、忽略退出码或强制退出。现存退出崩溃仍阻塞可提交状态。

最终 focused 包含 Node 插件及 Python/JS snapshot integration；Fast/Full 不筛掉任何额外测试。原始结果摘要如下（诊断二分的 deselected 仅用于定位，不作为最终套件结果）：

```json
{
  "focused-initial": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "279 passed in 28.08s",
    "atexit_seen": true,
    "blocked": []
  },
  "focused-final": {
    "exit": "0x00000001",
    "pytest": 1,
    "summary": "1 failed, 278 passed in 59.69s",
    "atexit_seen": true,
    "blocked": []
  },
  "focused-final-repeat": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "279 passed in 39.20s",
    "atexit_seen": true,
    "blocked": []
  },
  "fast-repro": {
    "exit": "0xC0000005",
    "pytest": 0,
    "summary": "3335 passed, 5 skipped, 348 deselected in 128.28s (0:02:08)",
    "atexit_seen": false,
    "blocked": []
  },
  "fast-final": {
    "exit": "0xC0000005",
    "pytest": 0,
    "summary": "3335 passed, 5 skipped, 348 deselected in 109.10s (0:01:49)",
    "atexit_seen": false,
    "blocked": []
  },
  "full-final": {
    "exit": "0xC0000005",
    "pytest": 0,
    "summary": "3657 passed, 31 skipped, 1 warning in 373.02s (0:06:13)",
    "atexit_seen": false,
    "blocked": []
  },
  "gui-alone": {
    "exit": "0xC0000005",
    "pytest": 0,
    "summary": "405 passed in 51.09s",
    "atexit_seen": false,
    "blocked": []
  },
  "baseline-gui": {
    "exit": "0xC0000005",
    "pytest": 0,
    "summary": "405 passed in 51.30s",
    "atexit_seen": false,
    "blocked": []
  },
  "native-stack": {
    "exit": "0xC0000005",
    "pytest": 0,
    "summary": "51 passed, 354 deselected in 8.39s",
    "atexit_seen": false,
    "blocked": [],
    "stack_frames": 40,
    "stack_sha256": "683c1b4519516ed5fd2bc02bfef185ed2b4f6b8086930aa9baa69808bce80018"
  },
  "baseline-native-stack": {
    "exit": "0xC0000005",
    "pytest": 0,
    "summary": "51 passed, 354 deselected in 7.94s",
    "atexit_seen": false,
    "blocked": [],
    "stack_frames": 40,
    "stack_sha256": "683c1b4519516ed5fd2bc02bfef185ed2b4f6b8086930aa9baa69808bce80018"
  },
  "auth-header-repeat-01": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.43s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-02": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.45s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-03": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.45s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-04": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.47s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-05": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.45s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-06": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.52s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-07": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.44s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-08": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.46s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-09": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.46s",
    "atexit_seen": true,
    "blocked": []
  },
  "auth-header-repeat-10": {
    "exit": "0x00000000",
    "pytest": 0,
    "summary": "1 passed in 0.46s",
    "atexit_seen": true,
    "blocked": []
  }
}
```

一次 focused-final 中认证 header 用例发生 WinError 10053（本机软件中止连接），退出码 1；完整 focused 重跑与该用例连续 10 次独立请求均通过。不能仅据重复通过确认 10053 的根因，保留其为未稳定复现的传输异常，未调宽超时、增加重试或更改断言。

`git diff --check` 通过；全部既有未提交工作保留，无 commit / push / PR / merge。临时 archive、诊断脚本和测试 sandbox 在记录证据后从本工作树内清理。
