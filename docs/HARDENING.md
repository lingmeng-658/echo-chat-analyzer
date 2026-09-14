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
- 需要从 filesystem / snapshot / history / persisted result 整条链审计。
- 与 History / Cache / Snapshot 架构相关，但 Bug 与架构改进要分别判断。

状态：未审计

Release Blocker：Yes。

### BUG-04（候选）成员「代表词 / 像 TA」结果缺乏代表性

已知事实：

- 真实报告中出现用户本人认为完全不像自己的代表词。
- 目前不能直接认定算法 Bug。
- 需要检查 raw counts、ranking formula、时间覆盖、事件集中度、最少活跃天数 / 稳定性，
  以及文案是否过度承诺。

状态：候选 Bug / 未审计

Release Blocker：TBD。

### BUG-05（候选）WeChat 普通语言画像可能混入 expression fallback names

已知事实：

- 曾观察到 Facepalm / Sob / Laugh / ThumbsUp 等出现在普通「常说」词中。
- 这是 WeChat 证据，不是 QQ。
- 截图对应版本状态尚未确认。
- 必须先在最新 main / build 上复验。

状态：待复验

Release Blocker：TBD。

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

状态：已审计，可进入 RED。

### REL-02 History 可以直接 reopen 完整分析结果

当前历史能力不等于完整结果恢复。
目标是避免用户点击历史后必须重新分析。

状态：未审计。

### REL-03 Cache / Snapshot / History 生命周期统一

需要明确：

- 什么是 acquisition snapshot
- 什么是 analysis result cache
- 什么是 history metadata
- 哪些持久化
- 谁拥有文件
- reopen 依赖什么
- delete 应删除什么
- 是否存在 orphan files

状态：未审计。

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

状态：未审计。

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

已完成只读审计。
后续分阶段更新 README / ARCHITECTURE，
退役 DEVELOPMENT_STATE / PROJECT_STATUS 的 live-fact 身份。

状态：已审计，未实施。

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