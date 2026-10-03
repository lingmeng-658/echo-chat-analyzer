# Stage 3.5J：正式 main+WAL acquisition

本轮完成可自动执行的接入、虚构测试和回归。真实 NapCat bridge 不可达，未完成真人会话列表和报告验收。没有 commit/push、reset/restore/clean；没有修改 A4/A5/A6、GUI UX、分析算法或清理 diagnostics。

## 正式调用链

GUI → ChatAnalyzerFacade → QQDirectDatabaseImportService → QQDirectSnapshotRuntimeClient
→ EchoSnapshotApi.acquire → shared hardened capture → staging/merged.db
→ NapCat DatabaseApi.decryptDatabase → staging/snapshot.db
→ identity 复核、原 schema manifest、原子 generation 发布
→ 原有 manifest / SQLite quick_check gate → QQDatabaseProvider
→ qq-db-json payload → qq_db_adapter / ImportService → AnalysisApplicationService → 报告。

runtime generation 在会话查询或 payload 物化后 cleanup；payload 生命周期仍由原编排负责。

`main_wal.mjs` 是 Stage 3.5H-I2 实现的唯一共享 capture 模块。原 PoC 文件保留 CLI 和 re-export，正式 acquisition 不执行 PoC harness，不获取 passphrase，不增加第二套 merge/decrypt 算法。真人解密仍由现有 NapCat 进程负责。正式成功路径只向 decryptDatabase 传入受控 merged 文件；旧 `decryptDatabase('nt_msg.db', ...)` 已退出成功路径。

## 一致性和 fail closed

- 固定 SHM committed boundary B，检查两份 SHM header、checksum、checkpoint witness。
- 检查 WAL header/version/page size、salt、frame checksum、commit boundary 和完整选定前缀；复读验证选定字节。
- 检查 main identity/stat/content fingerprint 和格式。允许 B 后 append；checkpoint/main 改变、WAL reset/truncate/salt 改变、选定前缀 torn/invalid 均拒绝。
- 复用模块仅作一个额外修正：提前建立 WAL identity 基线，覆盖 main baseline 读取期间的文件替换。该问题由新增正式入口测试得到 RED；共享模块修正后正式入口、PoC merge 和 PoC snapshot 均 GREEN。
- native read telemetry 继续校验受控 merged 输入；缺失或不稳定仍拒绝发布。Application 的独立 SQLite quick_check 保留。
- capture 失败不调用解密；解密失败不发布；没有 main-only fallback 或旧 generation fallback。现有客户端对 snapshot_unstable 的有限重试保持不变。

## Ownership / lease / recovery

同一 root 使用 Windows OS FileShare.None 独占 lease，隐藏 PowerShell 子进程持有 handle，通过 stdin EOF 释放。lease 从 recover/capture 持有到 generation cleanup；另一个活跃 owner 无法清理消费中的产物。runtime 进程强杀后 stdin 关闭、handle 释放，下一次 owner 在 lease 内恢复，无 PID 猜测。

root/staging 有固定版本 ownership marker；generation 保留该 marker，并兼容已有合法 manifest 的旧 generation。恢复先验证全部待删除成员，再删除任何成员。允许的 artifact 名称固定；未知文件/目录、symlink/junction 拒绝处理。加密 merged 文件必须在发布前删除。数据先删、ownership proof 最后删；manifest 删除后剩余 marker 的 generation 仍可恢复。marker 写入失败只清除本次独占创建的 marker。

OS 删除失败、未知 staging 和清理失败均返回失败，保留可识别残留；后续 acquisition 必须成功 recover 后才可继续。不会把 best-effort cleanup 当作成功。无关 cleanup 请求不会释放活跃 generation 的 lease。

## RED → GREEN 与验证

初始相关基线：154 passed。新增正式入口测试初次 10 failed，证明旧 helper 仍消费 main-only；接入后 GREEN。随后文件替换和 marker 写入中断各得到独立有效 RED，再作最小修正。

虚构覆盖包括正常 main+WAL、B 后 append 的冻结内容、checkpoint/main 改变、WAL reset/truncate/salt 和 prefix 故障、decrypt false/throw、cleanup 失败、未知 artifact、OS lease 竞争、实际 subprocess 强杀恢复、实际 Windows delete sharing failure、junction、marker 写入中断以及 manifest/RPC/Import Service/Facade contract。

验证快照（不作为固定测试数量契约）：

- Focused：最终串行运行相关 snapshot/PoC/lifecycle/bootstrap/client/service/facade/GUI wiring 文件，322 passed。
- Fast：2402 passed，3 skipped，164 deselected。
- Full：2549 passed，19 skipped，1 failed；唯一失败是既有 `known_failure` 的 `test_generate_share_button_creates_and_opens_share_image`。没有修改该测试或 GUI。
- Full 的 skips 来自未提供 frozen/portable/native/WeChat runtime 环境。
- 早期默认 pytest temp cleanup 遇到既有 pytest-current 权限问题；后续使用仓库外的专用 basetemp。一次并行 focused/full 运行使 bootstrap 全局临时目录集合断言发生竞争，随后串行复验，不修改业务代码或测试预期来掩盖该环境竞争。
- tracked `git diff --check` 和本轮 untracked 源码 whitespace check 通过；实际修改范围已复核。

Bootstrap 为 capture/workspace 两个模块固定 hash、注入并复核；runtime manifest 声明两个依赖。虚构 offline bootstrap 验证完整恢复、重复安装、hash 拒绝和旧 runtime 保留。当前本地 ignored runtime 的三个 helper 模块已同步，未启动或重启 QQ。

## 真人结果和 3.5K

仅输出匿名 health 结果：默认 bridge 和配置中的本地 bridge 均不可达。没有读取聊天内容或生成真人报告；不把 Stage 3.5I2 的真人 PoC 成功视作本轮正式链路验收。

可以进入 3.5K 的验收工作；正式真人 acquisition → session list → 一份报告仍是待完成的验收 gate，当前不能宣称正式真人链路已经通过或上线就绪。

## 当前未提交文件分类

1. 原有 tracked 修改，保留未编辑：application 的 QQ direct import service、Provider 的 snapshot runtime client，以及 analyze single generation、identity names、runtime client 三个测试文件。
2. 本轮 tracked 修改：ARCHITECTURE.md、snapshot helper、bootstrap、runtime pins、runtime manifest，以及 snapshot runtime 和 bootstrap 两个测试文件。
3. 原有 untracked 且本轮接入调整：main_wal_poc.mjs（共享模块 CLI/re-export）、test_qq_direct_main_wal_poc.py（driver reuse 和替换窗口 regression）。
4. 本轮新增：main_wal.mjs、workspace.mjs、正式 acquisition / workspace 两个测试文件和本记录。
5. 原有 untracked，保留未编辑：.codex、原 research 文档、main_wal_acceptance.py、main WAL lifecycle 测试。未清理其 artifacts。
6. ignored 本地 runtime：仅同步 snapshot/main_wal/workspace 三个 helper 模块，不包含真实数据或身份。
