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

已知事实：

- 用户无法确信 GUI 所称删除操作真正删除了预期的本地数据。
- 生产路径中的 `ChatDataSnapshot` 已删除；QQ raw export 改为 Echo-owned transient
  lease，正常分析结束后自动 cleanup，重新分析会重新 acquisition 而不复用长期 stale raw snapshot。
- 仍需要从 filesystem / transient run / report history / persisted result 整条链审计；
  上述完成项不等同于完整的“删除全部本地数据”产品语义。

状态：部分修复，仍待审计

Release Blocker：Yes。

### BUG-04（候选）成员「代表词 / 像 TA」结果缺乏代表性

已知事实：

- 真实报告中出现用户本人认为完全不像自己的代表词。
- 目前不能直接认定算法 Bug。
- 需要检查 raw counts、ranking formula、时间覆盖、事件集中度、最少活跃天数 / 稳定性，
  以及文案是否过度承诺。

状态：候选 Bug / 未审计

Release Blocker：TBD。

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

同一次 acquisition 审计还发现并独立修复另一个 correctness defect：Provider / native
helper 将 no-limit / `limit=0` 静默回退到 100000 行。修复后，synthetic 100001-row
SQLite 验收由 rebuilt binary 返回 100001 行且 `truncated=false`。这与 shard rollover
根因不同，不能合并为同一根因。

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

### REL-02 History 可以直接 reopen 完整分析结果

当前历史能力不等于完整结果恢复。
目标是避免用户点击历史后必须重新分析。

状态：未审计。

### REL-03 Cache / Snapshot / History 生命周期统一

当前已完成：

- 生产 `ChatDataSnapshot` 已删除；QQ raw acquisition 是一次性 transient lease。
- 正常分析结束后会清理 transient payload；重新分析会重新 acquisition。
- Echo Report 是保留的结果资产；history 当前保存的是元数据，不是 raw snapshot。

仍待审计 / 完成：

- 异常终止后的 orphan transient run cleanup；
- report history reopen；
- report deletion；
- retention / max-count policy；
- “删除全部本地数据”的最终用户措辞。

状态：部分完成，未关闭。

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

包体变化：

| 阶段 | unpacked | ZIP |
| --- | --- | --- |
| Initial | 487.00 MiB | 199.86 MiB |
| PACK-SIZE-01 | 417.18 MiB | 178.74 MiB |
| PACK-SIZE-02B | 358.12 MiB | 146.60 MiB |

PACK-SIZE-01（Windows native pruning）：

- build 时过滤 Windows x64 不需要的 QQ native binaries；
- source runtime 不删除；
- Linux / Darwin / ARM native 不进入 Windows portable package。

PACK-SIZE-02B（legacy desktop artifacts + dependency pruning）：

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

---

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

当前 build script 在缺 PyInstaller 时可能动态安装未固定版本。
先记录，不在本任务处理。

状态：未审计。

### GOV-05.1 Build / runtime environment debt（本机 gitignored runtime 资产不完整）

当前开发机 main worktree 的 gitignored：

```text
runtime/qq
runtime/wechat
```

本地资产并不完整。因此 merge 后 Fast Suite 结果为：

- 2121 passed
- 3 failed（environment-dependent）
- 1 skipped
- 30 deselected

失败节点与缺口：

- `tests/test_qq_auth_bridge.py::test_launcher_user_exits_without_pause_in_echo_mode`
- `tests/test_qq_auth_bridge.py::test_launcher_user_keeps_pause_for_interactive_mode`
  —— 缺 `runtime/qq/launcher-user.bat`；
  这两个节点在 PACK-SIZE-02B 的完整 runtime worktree 中已单独验证通过。
- `tests/test_wechat_key_service.py::test_bundled_helper_reaches_process_enumeration_before_dll_load`
  —— 缺完整 bundled runtime；
  同文件 1 skipped：缺 bundled Windows Node.js / koffi / wx_key.dll。

明确结论：

- 这不是本次 merge 的产品代码 regression；
- 不应靠旧 dist 恢复资产并将其当作正式 runtime source；
- Final Build 前必须通过权威 bootstrap / source 恢复完整 runtime；
- 该问题单独处理，不在本次 documentation checkpoint 修复。

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
