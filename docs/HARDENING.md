# Echo Hardening 工作地图

> **唯一定位**：本文是 Echo 当前「上线前 Hardening 阶段」的唯一实时工作地图。
>
> 本文同时承担 **Active Bug Backlog**。
> 不要再单独创建 `bug-backlog.md`，避免出现两个「当前事实源」。

Echo 已经过了「先证明有没有人愿意用」的阶段。
已有真实用户使用和反馈。

当前核心目标不是扩功能，而是：

- 修复肉眼可见和阻塞使用的 Bug
- 提高 QQ / 微信主链稳定性
- 保证分析结果可信
- 完成本地数据生命周期
- 完成结果导出 / 分享闭环
- 改善关键 UX 和错误可诊断性
- 在真实机器、真实数据上持续验收

默认不新增大型功能或新数据来源。
新能力需要人工确认。

---

## 状态词

统一使用：

- 未审计
- 审计中
- 已审计
- Ready for RED
- 实现中
- 待真实验收
- CLOSED
- DEFERRED

同时允许：

- 候选 Bug
- Release Blocker：Yes / No / TBD

---

## Active Bugs

### BUG-01 巨大 QQ 数据源分析失败

已知事实：

- GUI 最终显示「分析过程中出现未预期的错误，请稍后重试。」
- 目前还不能确认失败位于 QCE 导出、文件生成、Import、Analysis、内存 / 性能或其他阶段。
- 不能提前猜根因。
- QQ 真实导出进度和 diagnostics 是定位它的重要前置。
- 已完成的基础设施改善：有限分析范围会下推至 QCE，且一次 acquisition 使用
  Echo-owned transient lease；这两项不能单独证明“大型 QQ 数据源分析失败”已解决。
- 上述记录属于旧 QCE acquisition 路径；桌面 QQ 当前已改用 Direct DB，不能将旧现象
  自动视为已修复或直接归因于新路径。

状态：未审计

Release Blocker：TBD，如果正常大型群可稳定复现则升级为 Yes。

### BUG-02 QQ market_face / type_17 兼容问题

已知事实：

- 真实数据中发现 `market_face`，且观察到 `type_17`。
- 当前 QQ adapter 对这类消息的 rich pipeline 语义需要专项审计。
- 不允许直接「把 `type_17` 加进允许列表」作为修复。
- 必须先确认 QCE 字段语义、rich message 映射和分析影响。

状态：未审计

Release Blocker：TBD。

### BUG-03 「删除全部本地数据 / 缓存」语义与实际生命周期不完整

状态：CLOSED。

Release Blocker：No / CLOSED。

完成边界：

- Report Package 是唯一持久分析对象；四文件完整发布，`metadata.json` 驱动 Local Data
  catalog，损坏 package 作为 issue 可见。`analysis_history.jsonl` / `ReportHistoryManager` 已退休。
- `reports/` 保存正式报告，默认 scratch 位于 `transient/`；首次创建默认 scratch 前
  recovery 遗留自有 scratch，正常替换、失败及 shutdown 清理遵守 ownership / reparse 边界。
- Local Data 支持“删除选中报告”、“删除全部报告”、安全 reopen 与纯内存轻量搜索；删除目标是完整自有
  package，不是 QQ / 微信原始数据或用户另存文件。单项删除已完成，刷新后保留搜索 query，失败明确可见。
- listing、retention 与 delete 共用正式 package 候选边界：reports root 的直属真实目录，
  且名称严格符合 ownership naming。合法名称的普通文件忽略并保留；reparse / symlink / junction
  仍走安全拒绝，不跟随外部目标。
- 固定 max-50 retention 在新 package 发布成功后执行；损坏 metadata package 仍计数、
  时间未知者优先淘汰。清理失败保留新报告成功结果，公开 warning，并允许暂时超限。
- Automated tests 通过 autouse fixture 隔离真实用户数据目录，默认 packaging / production
  composition 测试也落入临时环境；sentinel regression 固定该边界。

真人验收：已通过批量删除及真实分析 → 正式报告保存 → 删除链路，确认实际 package 被删除。
此前一次“GUI 列表为空但磁盘 package 仍在”的观察后来未复现，根因未确定；不将测试污染
或某个未经证实的路径错误写成该观察的确定原因。

工程复盘：`docs/BUG_JOURNAL.md` Journal 011。

### BUG-05 WeChat 英文官方表情别名污染普通语言画像

状态：CLOSED。

Release Blocker：No / CLOSED。

现象与根因：

- 曾观察到 Facepalm / Sob / Laugh / ThumbsUp 等出现在普通「常说」词中；
  这是 WeChat 证据，不是 QQ。
- 根因：WeChat 官方表情存在英文 bracket alias（`[Facepalm]` / `[Grin]` /
  `[Laugh]` / `[Lol]` 等），旧逻辑主要识别中文 canonical name，
  因此英文 alias 未被 expression recognizer 接住；
  bracket punctuation 被 tokenizer 的 lexical preprocessing 去除后，
  alias 本体进入普通 lexical token，污染「你常说 / TA常说 / 同频」等语言画像。
- 这是 source representation compatibility 问题，
  不是 stopword 覆盖不足，也不是「英文词本身不该统计」。

修复：

- 建立 official alias -> canonical expression normalization；
- 110 个 aliases 建立 mapping / tokenizer / adapter 三层契约；
- 不使用 stopword；
- 不泛化删除任意 `[A-Za-z]+`：
  `[TODO]` / `[AI]` / `[Python]` 等普通 bracket text 保留；
- bare `Laugh` / `Lol` 等用户真实输入保留；
- 修复中发现 `[Pooh-pooh]` 会被 hyphenated ASCII protection 抢先处理，
  因此调整 preprocessing order：
  expression masking 必须先于 hyphenated ASCII protection。

验证：

- focused：485 passed；
- 该分支 Fast Suite：2121 passed / 26 deselected；
- Windows build 成功；
- 真实朋友机器 / 真实 WeChat 数据用最新版本复验通过：
  原英文 expression names 不再进入语言画像，使用过程中未发现新 Bug。

工程记录：`docs/BUG_JOURNAL.md` Journal 003。

### BUG-06 WeChat 会话数据明显不完整 / 不随新消息更新

状态：CLOSED

Release Blocker：No / CLOSED

已验证证据：

- 配置的 DB 文件本身仍在更新；直接 DB 读取可见近期数据。
- 真实目标 session 的同一 `Msg_*` table 分布在多个 `message_N.db` shard。
- 原 Provider 在第一个 matching shard 即返回，因此只读取旧 shard。
- 修复后 Provider 读取全部 matching shards，以相同范围查询、merge 并全局排序；
  真实 GUI 重新分析一个仅在新 shard 中存在的日期范围成功。

历史归类说明：原 BUG-04「成员代表词 / 像 TA 缺乏代表性」的真实证据来自 WeChat
分析结果。目标 session 因原 Provider 只读取第一个 matching shard，近期大量消息未进入
分析；当时的上游输入明显不完整，原证据已无法支持“存在独立代表词算法 Bug”的判断。
BUG-04 不再作为 Active Bug 单独追踪；这不表示代表词算法已被实验证明修复。
相关语言画像优化见 REL-09。

同一次 acquisition 审计还发现并独立修复另一个 correctness defect：Provider / native
helper 将 no-limit / `limit=0` 静默回退到 100000 行。修复后，synthetic 100001-row
SQLite 验收由 rebuilt binary 返回 100001 行且 `truncated=false`。这与 shard rollover
根因不同，不能合并为同一根因。

### BUG-07 Direct DB 偶发 `database disk image is malformed`

状态：CLOSED（2026-10-02 最终真人验收）。Release Blocker：No。

历史 main-only 解密路径未纳入 committed WAL；正式链路已替换为 hardened
main+WAL acquisition，在固定 SHM committed boundary 内校验、合并，再解密。
Windows/libuv identity 比较统一为 descriptor fstat，保留 dev / ino 保护；
瞬时 `snapshot_unstable` 允许 bounded retry，无法证明一致性时仍 fail closed。
Stage 3.5 已关闭，正式真人 E2E 与最终 smoke 均 PASS。长期 correctness 诊断继续保留；
本机验收不替代跨机器 Direct DB RC 验证。历史研究结论仍保留在 `docs/research/`。

**明确注明：QCE / Windows 权限弹窗不是 Bug。**

这是正常权限行为，UX 已经做过优化，不应重新进入 Active Bugs。

---

## Release Improvements

### REL-01 QQ 真实导出进度

目标：GUI 显示真实 QCE progress / messageCount / status，绝不伪造 totalMessages。

该功能同时是 BUG-01 的诊断前置。

当前已有审计结论：
QCE 提供 messageCount、progress、status、message，
没有可靠标准 totalMessages / processedMessages。

状态：已真实验收通过。

最终设计：

- QCE 的 `progress` 字段不足以为用户提供可靠的完成百分比；实际表现为类似
  0% → … → 97% 后长时间不变，因此不再作为面向用户的百分比展示。
- facade 不再把 `progress` 渲染为 `{value}%`，也不透传可能含百分比的 QCE `message`。
- `message_count > 0` 时显示：`正在获取 QQ 聊天记录 · 已获取 N 条`；
  无可信数量时只显示：`正在获取 QQ 聊天记录`。
- 不插值、不估计 total、不伪造 100%，也不把 `messageCount` 当作 total。
- `progress` / `status` / `message` 仍在 Application 层 `QQExportProgress` 中原样透传，
  只是不再渲染成百分比。

真实验收结果：

- QCE 阶段显示 `已获取 4,379 条`，未再出现 0% / 97% / 100% 等假百分比。
- 数量很快到 4,379 后约数秒不增长，随后进入报告生成。
- 最终 Echo Report 分析消息为 234 条：4,379 是获取到的原始消息数，234 是过滤后
  进入分析的消息数，二者语义允许且符合预期（该验收群以机器人 / 模板噪声为主）。

大数据 QCE 卡住 / 超时转入 BUG-01，本阶段不处理。

### REL-01.1 QQ 导出停滞感提示（非阻塞 UX debt）

当 `message_count` 一段时间没有增长、但导出任务仍未结束时，用户容易误以为程序卡死。

后续可考虑显示类似：
`已获取 4,379 条 QQ 聊天记录 · 正在完成导出，请稍候…`

约束：

- 只能说明“任务仍在处理中 / 导出尚未结束”；
- 不得猜测 QCE 正在进行审核、校验、安全检查等具体内部步骤；
- 不显示虚假百分比；
- 不预测剩余时间。

状态：已记录，本次不实现。

### REL-02 History 可以直接 reopen 已保存的 Echo Report

已随 BUG-03 完成：Local Data 选中或双击历史报告，通过 Facade / Catalog 安全定位
package 内的 HTML，使用系统默认浏览器打开，无需重新分析。
文件缺失或 opener 失败显示明确错误，不崩溃、不静默隐藏报告；不重建历史 Dashboard。

状态：CLOSED。

### REL-03 Cache / Snapshot / History 生命周期统一

当前已完成：

- 生产 `ChatDataSnapshot` 已删除；QQ raw acquisition 是一次性 transient lease。
- 正常分析结束后会清理 transient payload；重新分析会重新 acquisition。
- Report Package 是唯一持久分析对象，Local Data 从 package metadata 构建 catalog；
  独立 JSONL history 已退休。报告 reopen、完整 package deletion、固定 max-50 retention
  与默认 analysis scratch / stale recovery 已随 BUG-03 完成。
- Local Data 的最终用户措辞为“删除全部报告”，不承诺删除 QQ / 微信原始数据或用户另存文件。
- 桌面 QQ Direct DB generation 在会话查询或 payload 物化后清理；启动与 shutdown
  的 `recover` 负责遗留 plaintext。真人验收确认正常 shutdown 后 `snapshot.db` 无残留。
- 所选会话的 `qq-db-json` payload 位于本次分析临时目录，由 consumer 完成或异常退出时
  清理；它与 runtime generation 的 `snapshot.db` 是两个不同的 transient 资源。

仍待审计 / 完成：

- 旧 QCE transient run 在异常终止后的 orphan cleanup；Direct DB runtime generation
  已有启动/关闭 `recover`，不能混为同一项；

状态：Report Package / 默认 analysis scratch 部分已随 BUG-03 关闭；旧 QCE orphan run
cleanup 仍属单独待审计项，本条不扩大其完成范围。

### REL-04 按阶段区分的用户安全错误提示

例如：

- 数据获取失败
- 导出失败
- 数据读取失败
- 分析失败
- 保存 / 分享失败

GUI 不展示 traceback。
真实诊断写 privacy-safe diagnostics。

状态：未审计。

### REL-05 大型数据容量和 UX

只有 BUG-01 根因确认后才设计。
不要提前把逻辑 Bug 当性能优化问题。

状态：DEFERRED until BUG-01 root cause。

### REL-06 Windows 普通用户发布 / 安装体验

Portable build 已存在。
安装器、分发方式、普通用户首次运行体验仍需收口。

状态：未审计（installer / 最终普通用户分发体验仍未完成，不标 CLOSED）。

#### REL-06 附：Windows portable package hardening 记录

当前 De-QCE 发布合同：先使用项目 `.venv` 的 Python 运行
`scripts/bootstrap_qq_napcat_runtime.py`（可用 `--archive` 复用官方 archive，仍校验 hash），
再运行 `scripts/build_windows_exe.ps1`。QQ 发布源为 `runtime/qq-napcat-candidate`，
不要求旧 QCE runtime 存在；Stage 4B 已移除旧 Desktop bootstrap 与 rollback。
CLI QCE 导出与既有 JSON 导入仍保留，CLI 使用自行部署的外部 QCE 服务。
正式发布不携带 qce-server、napcat-plugin-qce、static/qce 或账户配置、日志、snapshot
plaintext。程序白名单和关键 hash 在复制前后检查，MSVC DLL 复制至 candidate 与 WeChat。
本轮保留官方 NapCat 完整依赖布局，不应用下述历史 PACK-SIZE-01 native pruning。
发布验收必须使用新生成的 Echo.exe，不能以源码 GUI E2E 替代。

2026-10-04 Fresh Packaging checkpoint：

- 基线：`main`，HEAD `1ec22c1b636a8b24c359a55574bf6a6a114f46c2`。
- 此前 Full 的两个 frozen/package failure 均来自 stale `dist/Echo` 被当前 contract tests 检查：
  一个表现为整个新 `qq-napcat-candidate` runtime 缺失，首先断言缺 `NapCatWinBootHook.dll`；
  另一个表现为 EXE 内仍是旧 QCE Desktop wiring / 旧 module layout，缺当前 NapCat provider。
  当前源码 contract 未发现对应 packaging defect，未增加 hidden imports、未修改 runtime manifest。
- 正式完整 fresh build 成功，替换旧 package：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows_exe.ps1
```

- Fresh frozen package contract、portable runtime contract、实际 `PYZ.pyz` module table 均 PASS：
  manifest requirements（含 NapCat DLL）完整，NapCat pinned hashes 正确，QQ / WeChat app-local
  MSVC runtime 完整；PYZ 包含当前 NapCat provider、`application.qq` Direct DB modules、database
  provider、snapshot runtime 和 adapter。无旧 `runtime/qq`、qce-server、napcat-plugin-qce、static/qce；
  smoke 后清理生成状态，release tree 无账户配置、日志或 plaintext snapshot 等 private state。
- 真实 frozen startup smoke PASS：fresh `Echo.exe` → 正常初始 GUI → QQ 页面 → NapCat launcher
  实际启动 → `waiting_auth`；无 frozen import、DLL 或发布资产错误。未登录真实 QQ、未读取聊天数据；
  正常退出后自有进程树清理完成，无 plaintext 残留。
- 本次验收快照：Focused **146 passed**；Fast **2655 passed，231 deselected**；Full **2884 passed，
  1 known unrelated failure，1 environment-dependent skip**，两个原 packaging failures 均已消失。
  唯一 failure 为已有 `known_failure`
  `tests/test_gui.py::test_generate_share_button_creates_and_opens_share_image`，与 packaging 无关；
  唯一 skip 为
  `tests/test_wcdb_cli_unlimited.py::test_native_cli_without_positive_limit_returns_more_than_100000_rows`，
  因未设置 `ECHO_NATIVE_WCDB_CLI_PATH`。这些数字只记录本次 checkpoint，不是固定测试数量要求。
- 两个 Release Packaging blocker：**CLOSED**；本轮无产品源码修改。
  REL-06 整体仍开放：installer、普通用户首次运行和最终分发体验尚未完成。

历史包体变化（不代表当前 fresh package 大小）：

| 阶段 | unpacked | ZIP |
| --- | --- | --- |
| Initial | 487.00 MiB | 199.86 MiB |
| PACK-SIZE-01 | 417.18 MiB | 178.74 MiB |
| PACK-SIZE-02B | 358.12 MiB | 146.60 MiB |

PACK-SIZE-01（Windows native pruning）：

- build 时过滤 Windows x64 不需要的 QQ native binaries；
- source runtime 不删除；
- Linux / Darwin / ARM native 不进入 Windows portable package。

PACK-SIZE-02B（legacy desktop artifacts + dependency pruning，以下为当时的历史 checkpoint）：

- Desktop / Application 不再生成 5 个 legacy artifacts：

```text
word_frequency.csv
word_speaker_summary.csv
word_speaker_frequency.csv
word_top_speakers.png
wordcloud.png
```

- CLI 旧 legacy word artifact 能力仍保留；
- desktop frozen import graph 排除旧 graphics / data stack：
  `pandas` / `matplotlib` / `wordcloud` / `PIL` / `contourpy` / `kiwisolver` /
  `mpl_toolkits` / `fontTools` / `pytest` / `_pytest` / `pygments`；
- 保留（未误删）：`numpy` / `jieba` / `PySide6` / `zstandard`；
- CLI console entrypoint 已额外验证：
  `test_console_script_and_module_help_are_consistent`（1 passed）。

后续 jieba LAC / numpy pruning 进一步将 `jieba.lac_small` 和 `numpy` 从 Desktop frozen package
排除；当前 `LocalChatAnalyzer.spec` 明确 excludes 两者，
`tests/test_frozen_desktop_package_contract.py` 对 numpy 模块及 numpy native libraries absence
有 frozen contract。2026-10-04 fresh package 验证通过，仍保留 plain jieba segmentation、
`PySide6`、`shiboken6`、`zstandard` 等实际 Desktop 依赖；不改变上面 PACK-SIZE-02B 的历史语义。

### REL-07 GUI 上线前最终 polish

只处理明显影响用户体验的视觉 / 交互问题。
不重新设计整个 GUI。

状态：未审计。

### REL-08 分析结果导出 / 分享闭环

不要只判断 Share renderer 是否存在。

需要验收整条用户链：

```text
分析完成
→ 用户发现分享入口
→ 生成
→ 明确生成状态
→ 找到结果
→ 可以发送
→ 接收方无需安装 Echo 即可理解结果
```

当前存在一个测试 / 产品契约冲突：
share button 当前产品行为隐藏，
但 existing test 期望其可见 / 可用。

该冲突属于产品决策，不属于测试治理遗留。

状态：未审计

Release Blocker：Yes。

### REL-09 语言画像语义 / 代表词算法分工

后续审计“常说”与“更像 TA”的文案和算法是否对应：

- `top_words` 是成员自身纯词频排序，更接近“常说什么”，不宜承担过强的“代表性”语义。
- 现有 `DistinctiveWordAnalyzer` 的成员 vs 其他成员 distinctive-word / log-odds 排序
  更接近“哪些词更像 TA”；后续优化优先复用该能力。
- 数据不足时允许不展示特色词，避免强行生成低置信度结果。

状态：后续产品 / 算法优化，未审计。

---

## QQ Direct DB 最终验收 checkpoint（2026-10-02）

桌面 QQ 会话查询与分析当前使用 Direct DB 主链；QCE CLI 与既有 JSON 文件兼容仍保留，
桌面分析没有自动 QCE fallback。架构与生命周期以 `ARCHITECTURE.md` 为准。

最终状态：Stage 3.5 CLOSED、A4 CLOSED、A5 CLOSED、A6 CLOSED、
Final Cleanup PASS、Final Smoke PASS。本分支 QQ Direct DB replacement 已完成最终
真人验收，不再修改产品代码；跨机器 RC 与以下 backlog 不作为本分支 blocker。

已完成并验证：

- Stage 3.5：正式 hardened main+WAL acquisition → decrypt → provider → adapter
  → analysis → report。保留 SHM / WAL / main / checkpoint guards、lease、native
  telemetry 与 SQLite quick_check；不回退 main-only，也不消费旧 generation。
  仅对 snapshot_unstable bounded retry。Windows/libuv identity 修复保留 dev / ino
  双重保护。QCE Proxy thenable 永久 pending 修复也已通过真人验收。
- A4：群成员元数据按已验证的 `result.infos` 读取，`cardName` 优先、`nick` 回退；
  缺失或已离群成员保留可靠身份与未知名称，不猜名称。
- A5：Provider 按时间与 record ID 排序，payload / imported / kept 的真人逆序计数均为 0；
  排序行为 regression tests 保留。
- A6：保留多段文本、QQ face 与 Unicode emoji；group reply / mention 保留结构化关系，
  元数据不污染 authored lexical text。图片与 unknown 非文本段按段次数保留，重复不去重，
  多图片与图文段顺序已真人验证；legacy 正文仅投影 TextContent。
  纯图片范围 `result.status=completed`，词频为空但消息统计及 JSON / HTML 正常。
  MarketFace 有实现与虚构测试，但不宣称充分真人覆盖；unknown 只保留 unknown，
  不推断具体媒体类型。
- 正式真人 E2E / 最终产品 smoke：冷启动后获取会话列表，选择已验证真实群聊，
  acquisition 最终成功，分析 completed，JSON / HTML 正常且数据一致，report_path
  有效并实际在浏览器打开；群成员名称和基础 reply / mention / face / image 语义正常。
  generation / staging / payload / 获取 scratch 清理正常；正常 shutdown 的自有进程树
  与 plaintext 清理也已验收。最新 smoke 日志无新增非 history ERROR，单条已知
  history metadata 兼容错误单独记录，不作为本轮失败。
- Final Cleanup：删除 analysis-ordering 三个边界的专用计数/日志及相应日志测试断言，
  删除闲置 pollCount，已同步 deployed runtime helper 与 pin。排序、隐私断言、
  analysis-timing、DEBUG member-shape、identity coverage、failure_stage / guard_code、
  WAL/SHM/identity/checkpoint witness、quick_check、cleanup/recover/shutdown 和 native
  telemetry 均保留。源模板、pin、部署 helper 哈希一致；无已确认的阶段诊断残留。

Final Cleanup 后的回归记录（本次 checkpoint 快照，不作为固定测试数量要求）：

- Focused 修改前 / 后均通过；Fast 无失败。
- Full：2664 passed、19 skipped，唯一失败为既有 `known_failure`
  `tests/test_gui.py::test_generate_share_button_creates_and_opens_share_image`；无新增失败。
- git diff --check 通过。本轮 documentation checkpoint 不重跑产品回归。

仍开放、非本分支 blocker（未在本轮修复）：

- history metadata `snapshot_reused` 兼容：旧记录与当前 identity summary 校验不兼容。
- unknown session/member UX 折叠。
- MarketFace 真人覆盖不足。
- unknown element 真人覆盖有限：仅确认自然出现的 unknown 段保留，不推断媒体类型。
- GUI share-image 既有 known_failure。
- 快捷登录尚未实现；现有 QQ 授权/连接闭环验收不等同于该功能完成。
- 跨机器 Direct DB RC 验证尚未完成；当前真人验收限定本机与已有场景，
  不构成跨 QQ 版本 schema 保证或全体发布环境准入。

## Engineering Governance

### DOC-01 文档事实源治理

当前事实源已明确：`ARCHITECTURE.md` 为架构唯一事实源，`docs/HARDENING.md` 为
Hardening / Active Bug 唯一实时工作地图，`docs/BUG_JOURNAL.md` 只记录已解决并验证的
真实工程问题；`PROJECT_STATUS.md` 与 `DEVELOPMENT_STATE.md` 为历史快照，正文不再维护。

状态：CLOSED。

### DOC-02 AI Onboarding v1

状态：CLOSED。

### GOV-01 Active Bug Backlog

由本 HARDENING.md 承担。

状态：CLOSED（基础结构已建立）。

### GOV-02 Bug Journal

由 `docs/BUG_JOURNAL.md` 承担。

状态：CLOSED（机制已建立，后续随已解决问题持续追加）。

### GOV-03 Test Governance v1

状态：CLOSED。

详细历史记录见：`docs/engineering/TEST_GOVERNANCE_V1.md`

### GOV-04 版本号权威统一

当前曾审计到：

- pyproject package version
- GUI runtime version
- 历史 docs version

存在多个版本来源。

状态：未审计 / 未实施。

### GOV-05 Windows build 可复现性

当前 `scripts/build_windows_exe.ps1` 使用项目 `.venv\Scripts\pyinstaller.exe`，缺失时直接失败
（fail closed），不会在构建时动态下载或安装 PyInstaller；原“可能动态安装”的记录已过期。
但 `pyproject.toml` 尚未声明或 pin PyInstaller，PyInstaller / release build environment 的版本
固定、版本来源与可重建性仍未形成完整的 tracked reproducibility contract，待进一步审计。
本轮不实现 dependency pinning。

状态：未审计。

### GOV-05.1 Build / runtime environment debt（本机 gitignored runtime 资产不完整）

状态：CLOSED / RESOLVED（2026-10-04，仅关闭当前开发机这项 runtime 资产债）。

历史 checkpoint：当时开发机 main worktree 的 gitignored：

```text
runtime/qq
runtime/wechat
```

本地资产并不完整。当时 merge 后 Fast Suite 结果为：

- 2121 passed
- 3 failed（environment-dependent）
- 1 skipped
- 30 deselected

当时的失败节点与缺口：

- `tests/test_qq_auth_bridge.py::test_launcher_user_exits_without_pause_in_echo_mode`
- `tests/test_qq_auth_bridge.py::test_launcher_user_keeps_pause_for_interactive_mode`
  —— 缺 `runtime/qq/launcher-user.bat`；
  这两个节点在 PACK-SIZE-02B 的完整 runtime worktree 中已单独验证通过。
- `tests/test_wechat_key_service.py::test_bundled_helper_reaches_process_enumeration_before_dll_load`
  —— 缺完整 bundled runtime；
  同文件 1 skipped：缺 bundled Windows Node.js / koffi / wx_key.dll。

历史结论与当前边界：

- 当时的缺口属于本机环境问题，不是产品代码 regression；
- 不应靠旧 dist 恢复资产并将其当作正式 runtime source；
- Final Build 前必须通过权威 bootstrap / source 恢复完整 runtime；
- 当前 QQ 正式 release source 已迁移到 `runtime/qq-napcat-candidate`。2026-10-04 当前开发机
  已具备满足正式 runtime contract 的 source assets，正式完整 fresh build 成功；Focused / Fast /
  Full 中此前这组 runtime-asset environment failures 不再存在（验收结果见 REL-06 checkpoint）。
- 此关闭不表示新机器天然拥有完整 runtime，也不表示 fresh checkout 可跳过 bootstrap 构建；
  Windows build reproducibility 仍属于开放的 GOV-05 / 后续发布治理范围。

### GOV-05.2 Frozen artifact provenance

`tests/test_frozen_desktop_package_contract.py` 检查磁盘上已有的 `dist/Echo`，测试本身不会构建
fresh artifact。目前没有把已有 frozen artifact 与当前 Git HEAD 绑定的可验证 provenance；
旧 EXE 可被新 contract tests 检查并产生误导性的 RED，本次两个 packaging failures 即属于此类。

当前处理原则：Final Release / packaging acceptance 必须先执行正式完整 fresh build，
不允许用历史 `dist/Echo` 代表当前源码。后续可考虑 build provenance / commit identity，
本轮不实现。

状态：已记录 / 未实施。Release Blocker：No（不是当前 Release Packaging blocker）。

---

## Deferred Capabilities

明确不进入当前 Hardening 主线：

### CAP-01

更完整的图片 / 语音 / 视频 / system message 分析。

### CAP-02

Rich Model 最终迁移、逐步减少 legacy projection。

以及：

- AI 内部梗
- 语言趋同
- 表达变化趋势
- 更复杂关系推断
- 新数据来源
- 大型智能过滤框架升级

这些可以进入后续版本，但不阻塞当前上线。

---

## Release Gate

### QA-01

上线前必须完成一次独立 Final Acceptance：

- QQ 主链
- WeChat 主链
- private / group
- 小数据 / 普通数据 / 大数据
- Echo Report
- History / local data
- export / share
- portable build
- 陌生 Windows 机器
- 真人实际使用

完成条件：

- 不存在已知 P0 / P1 恶性问题；
- 连续一轮真实验收不再出现新的 Release Blocker。

然后：

```text
Feature Freeze
→ Bugfix Only
→ Final Build
→ Release
```

---

## 工作规则

每个 Bug / Improvement：

```text
现象与证据
→ 调用链学习
→ Codex 只读调查
→ 竞争假设
→ 最小诊断
→ 根因 / 设计判断
→ RED
→ minimal GREEN
→ focused
→ Fast
→ 必要的 focused integration / Full
→ 真实验收
→ CLOSED
```

原则：

- 一项一个分支
- 不在已完成分支继续无关工作
- 真实 Bug regression 优先永久保留
- 不为测试变绿篡改需求
- 不上传真实聊天记录
- 每解决一个重要问题，同时形成一次「项目链路学习」
