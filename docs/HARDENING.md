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

2026-10-08 状态校准：以 fetch 后的远程 `origin/main`（`baaad4e`）、可访问的开发分支
和工作树、当前实现及人工提供的发布待办为依据。本地 `main` 仍在 `342eff6`，本次不更新它。
`feat/session-workspace-refresh` 的 `baaad4e` 已进入远程 main；
`release/portable-distribution` 基于 `b09e83b`，REL-06B 改动仍未提交、未合并。
分支工作成果、虚构数据测试和真人验收分别记录；下文旧 checkpoint 保留当时事实，
不代表当前发布已就绪。本阶段只同步本文，ARCHITECTURE.md 等文档待发布工程合并后另行同步。

## 0.1 当前待办总览

正式 QQ 产品链：NapCat → Direct DB → `qq_db_adapter` → 统一消息模型 → Analysis。
QQChatExporter / QCE 的 runtime、provider/service、CLI 命令、QCE JSON 和旧 QQ JSON/JSONL
兼容均已退休，不存在 QCE fallback。`echo-chat` 保留当前支持格式的本地文件分析入口，
WeChat 当前能力不变；架构细节以 `ARCHITECTURE.md` 为准。

| 当前待办 | 状态 / 收口边界 |
| --- | --- |
| REL-04 用户错误提示 | CLOSED：现役错误安全边界已收口；分享与最终真人验收仍各归原条目 |
| REL-06 Windows 普通用户发布 / 分发体验 | 未完成；REL-06B ZIP / 运行目录分离在发布工作树，Frozen / 异常恢复待验收；Setup 待收口 |
| REL-06C NapCat 升级与兼容性 | **Release Blocker：Yes**；尚未完成升级及兼容性验收，现有 pin 为 4.18.18 |
| QQ Guided Setup 启动前退出引导 | 待实现 / 验收；已有 QQ 后台进程可能阻碍登录，不能只提示关闭主窗口 |
| REL-07 GUI 最终 polish | 首页、QQ 引导、会话工作台与琴键回响阶段性验收通过且已合入 main；Processing 仍在设计验证，加载动画 / 完成反馈与最终 Frozen 验收待收口 |
| REL-08 分享闭环 | **Release Blocker：Yes**；`d67f51e` 已恢复入口及生成，完整真人闭环尚未确认 |
| GOV-04 权威版本号 | CLOSED：pyproject.toml 为唯一发布版本事实源；runtime / GUI / metadata 共用，frozen build 核对并携带安装元数据 |
| QA-03 / QA-04 GitHub Release / 检查更新 | 未完成；Update Check Core 已实现，GUI 异步提示/打开下载页待接线；仍需核对 tag、发布说明和最终 fresh build；不自动下载、替换或静默更新 |
| QA-05 0.1 → 0.2 本地数据兼容审计 | CLOSED：metadata provenance additive 收口；固定旧 0.1 包的 list / reopen / retention 与不改写回归；演进边界见 ARCHITECTURE.md |
| GOV-05 发布构建可复现性 | CLOSED：build toolchain 已 tracked 声明并精确 pin；文档与合同齐备；fresh build 重建验证通过 |
| QA-02 定点 release / privacy / build audit | CLOSED：发布树残留防线、构建依赖声明、WeChat native DLL pin 三项收口；fresh build + frozen 合同验收通过 |
| 版权 / 第三方分发合规 | 待核对最终随包资产、许可 / 声明及官方表情 PNG 处理；不以 QA-02 工程审计代替 |
| GUI native access violation | 已观察、待定位风险；重跑通过不能作为已修复证据，最终验收需关注 |
| QA-06 跨机器 Direct DB RC | 待真实验收；本机 checkpoint 不能替代 |
| QA-01 最终真实验收 | 未完成；覆盖主链、大小数据、报告、Local Data、分享和最终发布包 |

Architecture & Complexity Audit v1 已 COMPLETE / CLOSED，0.1 不再重复开展泛化全仓架构审计；
发布前定点收口的 GOV-05 与 QA-02 已于 2026-10-07 关闭（证据见「0.1 发布治理」）。
测试治理当前阶段已完成，非 Release Blocker。BUG-01 和旧 QCE Desktop 任务已退休；
BUG-02 随 QCE 输入移除标记 RETIRED，BUG-03 / 05 / 06 / 07 / 08 保持 CLOSED。REL-05 大数据性能 / UX 与
REL-09 语言画像优化均为非阻塞后续工作。完整历史证据保留在本文后半部。

已有分支验收、历史 build checkpoint 和测试治理完成不代表 0.1 已可发布。

## Active Bugs

BUG-01 / BUG-02 已退休，BUG-03 / 05 / 06 / 07 / 08 保持 CLOSED。
当前另有待收口的 QQ 登录引导缺口和待定位的 GUI native crash 风险；不因旧 Bug
已关闭而忽略它们。REL-08 的实现已恢复，完整真人闭环仍为 Release Blocker。

- **QQ 启动前引导**：已有 QQ 后台进程可能阻碍 Echo / NapCat 登录。启动前需明确
  引导用户自行完整退出 QQ（包括托盘 / 后台），再继续连接；不能以关闭窗口代替退出。
  当前远程 main 的连接引导尚未包含这一前置步骤。验收需覆盖已有 QQ 运行与完整退出后重试；
  不改变只清理 Echo 自有进程的 ownership 边界。归 REL-06 首次运行与 REL-07 引导体验收口。
- **GUI native access violation**：QA-04 历史 Fast 验证曾在微信 GUI worker 出现，
  重跑通过但根因未确认。状态为待定位风险，不声称已修复或已证明是环境问题；
  按现象 / 最小复现 / worker 生命周期诊断推进，并纳入 QA-01 最终稳定性验收。

## 0.1 产品交付条目

### REL-04 按阶段区分的用户安全错误提示

现役 NapCat / Direct DB 与微信主链的错误提示已完成必要收口，覆盖：

- 数据获取失败
- 导出失败
- 数据读取失败
- 分析失败
- 保存 / 分享失败

GUI 不展示 traceback。
真实诊断写 privacy-safe diagnostics。

状态：CLOSED（现役用户安全错误提示的已确认缺口已修复；登录引导与 native crash 另行追踪）。

证据：`9ef734e` 不向用户透传未知异常正文；`633249d` 避免日志失败阻断启动；
`1b4da6e` 让 content-only 报告生成失败进入正式错误生命周期；`cbdf85b` 让微信
会话读取失败退出 loading 并允许重新开始（BUG-08）。对应 Facade / analysis / GUI
regression 保留。此关闭不代表 REL-08 Share、最终真实验收或跨机器 RC 已完成。

### REL-06 Windows 普通用户发布 / 安装体验

历史 portable build 与 frozen 合同已有验证记录；最终普通用户分发仍未完成。
当前分为 Setup 安装交付、REL-06B Portable ZIP / 运行目录分离及 REL-06C 升级兼容性。

#### REL-06B Portable ZIP 与运行目录分离

2026-10-08 可见进度位于 `release/portable-distribution` 未提交工作树，尚不属于 main：

- `scripts/package_windows_portable.py` 已有 ZIP + SHA-256 包装实现，读取权威版本，
  检查发行树状态、拒绝链接与已有输出覆盖，并验证归档和源文件一致性。
  它包装已有 build，不执行 fresh build，也不替代 native 资产 pin 与 Frozen 验收。
- QQ managed runtime 已有程序目录、用户运行目录、Direct DB transient 目录分离实现；
  QR / 启动 / snapshot 消费端正在使用同一套路径合同，GUI 经 Facade 获取 QR 路径。
  旧配置归属不明时拒绝猜测；custom runtime 保留独立边界。
- ZIP、路径和 workspace 测试代码使用虚构样本，含拒绝污染、并发、只读 / 不可写、
  中断准备和恢复等场景。测试存在不等于本次已运行，也不等于真实包验收通过。

本轮源码环境真人验收（2026-10-08，用户确认；不等同于 Frozen 包验收）：

| 验收项目 | 状态 | 实际结果 / 边界 |
| --- | --- | --- |
| QQ 首次启动与扫码登录 | 通过 | 退出原有后台 QQ 后，正常启动、扫码并连接；启动前退出引导仍待产品收口 |
| QQ 会话列表加载 | 通过 | 成功加载会话列表 |
| Direct DB 分析 | 通过 | 正常读取和分析聊天数据 |
| HTML 报告生成 | 通过 | 成功生成，人工检查未发现明显问题 |
| 第二次启动与连接 | 通过 | 重新启动后正常连接，未发现明显异常 |
| 程序与用户数据目录分离 | 初步通过 | 程序目录五项可变状态检查均为 False，用户工作区及快照根均存在 |
| 正常退出后的快照清理 | 通过 | staging、generations 剩余项目数及数据库残留文件数均为 0 |
| 完整退出生命周期 | 部分验证 | 正常关闭后快照清理符合预期；未逐项验证全部进程终止和恢复日志 |
| Frozen 可执行程序 | 未验收 | 尚未完成本分支完整 Frozen 构建及只读安装目录测试 |
| 异常退出与恢复 | 未真实验收 | 已有自动化测试，尚未进行真实 Frozen 异常退出与恢复测试 |
| 跨机器运行 | 未验收 | 尚未在其他 Windows 机器验证 |

以上只记录验收结论，不记录个人路径、账号或敏感日志；不将历史 Direct DB E2E
当成本轮目录分离验收，也不从快照清理通过推断全部进程终止或异常恢复已通过。

仍需：分支提交 / 合并后正式 fresh Frozen build、实际 Portable ZIP 解压运行、
只读安装目录与发行目录不承载运行状态的验证、完整退出生命周期，
以及实际中断 / 崩溃后的异常恢复与清理验收。
不得用源码环境通过或虚构恢复测试关闭上述待办。

状态：进行中（发布工作树成果未提交 / 未合并）；Frozen / 异常恢复真实验收未完成。

#### REL-06C NapCat 版本升级与兼容性验收

现有 tracked pins 与 build 校验仍固定 NapCat 4.18.18；截至本次可见分支尚无版本升级成果。
发布前需确认目标版本，升级正式资产及 pin，核对 Echo patch / plugin、启动登录、
QR freshness、会话读取、main + WAL snapshot / decrypt、分析、退出清理和异常恢复，
并在最终 Frozen / ZIP 包上验收。现有版本的历史通过记录不能替代升级验收。

状态：未完成。Release Blocker：Yes。

#### Setup 与首次运行

Setup 安装器的交付与普通用户首次运行仍待收口；Portable ZIP 完成不等于 Setup 完成。
QQ 启动前退出引导归本项与 REL-07 共同验收；最终分发资产归 QA-03，跨机器归 QA-06。

### REL-07 GUI 上线前最终 polish

只处理明显影响用户体验的视觉 / 交互问题。
不重新设计整个 GUI。

远程 main 已包含微信 Guided Setup（`eb36bc5`）、QQ 连接体验（`b09e83b`）、
共享字体整理（`fbeea4b`）和 QQ / 微信会话分析工作区（`baaad4e`）；
长群成员列表滚动修复（`342eff6`）也已合并。不再把这些写成未合并的 GUI 分支成果。

#### GUI 改版阶段性人工验收（2026-10-08）

以下依据已知 GitHub 代码状态、此前审计结果及本轮人工反馈，区分已合并实现、
阶段性视觉验收与尚未集成的设计方案；不代表最终 Frozen 程序整体验收。

| 验收项目 | 状态 | 实际结果 / 边界 |
| --- | --- | --- |
| Home 首页视觉改版 | 阶段性通过 | 新版布局、配色与视觉语言已完成并合入 main，作为当前 GUI 设计基准 |
| QQ 连接引导界面 | 阶段性通过 | 连接流程视觉改版已合入 main；启动前完整退出已有 QQ 的引导仍待收口 |
| QQ 会话列表加载界面 | 已实现，待调整 | 当前为翻书动画；设计复盘决定改为「会话目录整理」意象，表达正在准备可选择的聊天 |
| 微信连接引导界面 | 部分验证 | 连接状态与引导文案设计已完成，需结合最终发布版本完整真实验收 |
| QQ / 微信会话工作台 | 阶段性通过 | 会话选择与分析配置界面视觉改版已合入 main |
| 会话选中琴键回响 | 通过 | 轻量交互动画已实现并合入 main，阶段性视觉验收通过，决定保留 |
| Processing 页面现状 | 已审计，待改版 | 当前主要为状态文字和取消按钮，尚无正式书写动画 |
| Processing 动画意象设计 | 方案已确定，待验收 | 采用「书页汇集成册 → 音符尾缀笔书写」双阶段设计；旧 HTML 原型未达预期，待 Astra 重新制作独立动态原型 |
| 书页汇集动画 | 待重新设计 | 纸页须逐渐汇入书本、沿书脊接合并成为书页；旧原型未正确实现动作 |
| 音符尾缀笔动画 | 待重新设计 | 正常笔杆从中后段自然过渡为音符尾缀；旧原型笔尾不自然，未通过视觉验收 |
| 分析进度与动效切换 | 已审计，未实施 | Facade 进度文案不完全等于真实耗时阶段；须以真实处理边界驱动动画，不设置虚假进度 |
| 微信真实分析耗时 | 已实测 | 16,852 条群聊消息：约 7 秒读取、2 秒生成结果，总计约 9 秒 |
| QQ 真实分析耗时 | 已实测 | 约 93,000 条消息：18 秒读取、9 秒生成结果，总计约 28 秒，约 1 秒未细分 |
| 分析完成反馈 | 待调整 | 已支持自动打开 HTML 报告并返回工作台；完成提示及结果操作入口视觉反馈待完善 |
| 本地报告管理页视觉统一 | 待验收 | 已有本地报告管理功能，尚未完成本轮视觉一致性验收 |
| 检查更新 GUI 入口 | 未实施 | 已列入后续 GUI 路线，本轮未开展；仍归 QA-04 发布前收口 |
| Echo Logo | 暂时冻结 | 已有候选设计，尚未最终定稿；决定不再阻塞 GUI 主线 |
| 新版 GUI Frozen 程序整体验收 | 未验收 | 尚未完成最终 Frozen 构建及端到端视觉、交互回归验收 |

真实耗时仅是此次人工实测，不作为固定性能合同或动画计时依据；本次未读取真实聊天数据。
Processing 动画仍处于设计验证阶段，不记为已完成产品功能。

#### 当前后续顺序

1. 由 Astra 重新制作 Processing 双阶段独立动态原型，先完成视觉验收。
2. 审核真实进度事件与动画状态映射，再进行 PySide6 集成。
3. 将 QQ 会话列表加载动画调整为「整理会话目录」。
4. 完善分析完成反馈，核对本地报告管理页视觉一致性，最后进行整套 GUI Frozen 真实验收。

最终验收仍需覆盖 QQ / 微信连接与登录引导、会话选择、时间范围、分析 / 取消 /
失败后的状态恢复，以及 Frozen 包中的视觉、布局与可操作性。本阶段仅记录上述路线，
不开展原型制作、进度事件改造或 GUI 实现。

本次校准 focused：`tests/test_gui.py` 的 workspace full-chain、取消后选择 / 日期保留、
分析失败回到工作区共 5 passed；使用虚构 Facade / 数据，不代表真人 QQ / 微信验收。

状态：主要 GUI 更新已进入 main 并有阶段性人工验收；剩余 polish、Processing 设计验证 /
集成及最终 Frozen 真人验收未完成，REL-07 整体尚未 CLOSED，0.1 发布前必做。

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

`d67f51e` 已进入远程 main：有可用分析结果时显示 / 启用分享按钮，经 Facade 生成图片，
展示生成 / 成功 / 失败状态并尝试打开图片；renderer / template 同步修复。
初始化或无结果时隐藏按钮仍是状态控制，不再是整个分享能力雪藏。
`test_generate_share_button_creates_and_opens_share_image` 已移除 `known_failure` 标记；
本次 `tests/test_gui.py -k generate_share` 为 5 passed，使用虚构数据和 stub，未验证实际 renderer。

仍待确认整条真人链：入口发现、实际图片生成与可读性、找到文件、发送、接收方无需 Echo
即可理解结果，并在最终发布包复验。保留历史 known_failure 记录，不将它作为当前测试状态。

状态：入口 / 生成实现已恢复并合并；完整真人闭环待验收。

Release Blocker：Yes。

## 0.1 发布治理

### 最终随包版权 / 第三方分发合规

发布前核对最终资产清单、第三方许可与所需声明，覆盖 NapCat、微信 native 工具、
字体 / 图形及官方表情 PNG。NapCat pins 已记录其 Limited Redistribution License，
但 hash 命中不是分发合规结论。`fix/echo-0.1-remove-official-emoji-png` 目前仍指向
`b09e83b`，未见独立移除提交；不能凭分支名记为完成。
本项只记录待核对状态，不作法律结论，不重开已完成的全仓架构审计。

状态：待核对 / 收口；最终 Release 前确认。QA-02 的历史工程审计保持 CLOSED。

### GOV-04 版本号权威统一

`pyproject.toml` 的 `0.1.0` 是唯一发布版本事实源；`version.py` 读取安装元数据，
GUI 启动日志与新报告 metadata 共用，不再保留 GUI 的 `0.8.0` 定义。
frozen build 校验安装版本与 pyproject 一致并携带元数据，无需源码目录读取版本。
测试：`tests/test_app_version.py`、`tests/test_frozen_desktop_package_contract.py`。
历史 docs version、report schema 与 NapCat runtime version 不作为 app version。

状态：COMPLETE / CLOSED。QA-03 的 tag / GitHub Release / 最终发布资产仍独立待验收。

### GOV-05 Windows build 可复现性

`scripts/build_windows_exe.ps1` 使用项目 `.venv\Scripts\pyinstaller.exe`，缺失时直接失败
（fail closed），不会在构建时动态下载或安装 PyInstaller；原“可能动态安装”的记录已过期。

2026-10-07 收口：构建工具链已在 tracked 位置声明并精确 pin —— `pyproject.toml` 的 `build`
extra（`pyinstaller==6.22.3`、`pyinstaller-hooks-contrib==2026.8`）；`DEVELOPMENT.md` §3.1.1
给出 `pip install -e ".[dev,gui,build]"`，新 clone 不再依赖本机口头知识。
`pyinstaller-hooks-contrib` 单独 pin 的原因：它的 hook 决定 frozen 包携带哪些 package data
（例如 jieba 的 `lac_small/model_baseline`，由 frozen 合同固定）。
合同：`tests/test_windows_runtime_contract.py::test_pyproject_declares_the_pinned_windows_build_toolchain`、
`::test_development_guide_documents_the_build_toolchain`（均在 Fast）。
重建验证：2026-10-07 正式 fresh build 成功；main `eb36bc5` 源码产出
`dist/Echo/Echo.exe` 3,418,956 bytes、SHA-256
`39B61806EC4F62165D6894E61FB43688FD5981D23F665F36B9E1BB4EE5ECD0D8`，随后
frozen / portable / Windows runtime 合同 144 passed。

状态：COMPLETE / CLOSED。dependency lockfile、CI 与 bit-for-bit reproducibility
经人工确认不在 0.1 范围，本轮不实现。

### GOV-05.2 Frozen artifact provenance

`tests/test_frozen_desktop_package_contract.py` 检查磁盘上已有的 `dist/Echo`，测试本身不会构建
fresh artifact。目前没有把已有 frozen artifact 与当前 Git HEAD 绑定的可验证 provenance；
旧 EXE 可被新 contract tests 检查并产生误导性的 RED；2026-10-04 checkpoint 的两个
packaging failures 即属于此类。2026-10-07 audit 再次观察同类现象：磁盘上的 `dist/Echo`
不含当时 HEAD 新增的 `application.update_check_service`（PYZ 309 模块 vs fresh 310 模块），
且带有一份 smoke 产生的 `logs/echo.log`。

当前处理原则：Final Release / packaging acceptance 必须先执行正式完整 fresh build，
不允许用历史 `dist/Echo` 代表当前源码。2026-10-07 已增加两项机械防线降低该风险：
发布树运行残留断言（`releaseTreePrivatePaths`，见 QA-02）与 WeChat native DLL pin。
commit marker / build provenance framework 经人工确认不在 0.1 范围，本轮不实现。

状态：已记录 / 未实施。Release Blocker：No（不是当前 Release Packaging blocker）。

## Release Gate

### QA-02 定点 release / privacy / build audit

针对最终发布候选包，核验资产白名单 / hash、敏感配置 / 日志 / plaintext 排除、
运行后清理边界与 fresh build 来源，并与 GOV-05 的实际构建风险收口对齐。
Architecture & Complexity Audit v1 已完成（见 GOV-06），本项不重复泛化全仓架构审计，
也不提前扩展新的结构调整。

2026-10-07 只读审计结论：**未发现新增 build / privacy / frozen artifact Release Blocker。**
QQ / WeChat runtime 51/51 requirement 齐备、NapCat 39 项 SHA256 pin（32 个 requiredFiles，
其中 `napcat.mjs` 用 patched hash，6 个 template，1 个 `config/plugins.json`）全命中、
QCE 与 numpy / `jieba.lac_small` 全缺席、发行树零
config / account / 明文库 / JSONL / transient 残留（用户数据位于 `%LOCALAPPDATA%`，
不在 exe 同级），fresh 产物可正常冷启动。收口的三项：

1. **发布树残留防线**：`scripts/windows_runtime_manifest.json` 新增
   `releaseTreePrivatePaths`（`logs`、`scripts/wcdb-diagnostic.txt`），作为 build 与 tests
   共用的唯一清单；构建脚本新增 `Assert-ReleaseTreeStateAbsent`，在发布树完成后断言
   （覆盖 smoke 后 `-RuntimeOnly` 重打包与手工塞入）；frozen 合同对 `dist/Echo` 断言同一清单
   （覆盖 smoke 后直接打包的窗口）。证据：
   `tests/test_portable_runtime_copy.py::test_runtime_build_rejects_previous_run_residue`、
   `::test_runtime_build_leaves_no_release_tree_residue`、
   `tests/test_frozen_desktop_package_contract.py::test_frozen_release_tree_has_no_run_residue`
   与 `tests/test_windows_runtime_contract.py` 的残留结构合同。
2. **构建依赖声明**：见 GOV-05。
3. **WeChat native DLL pin**：manifest 新增 `wechatPinnedAssets`，pin 当前实际发布依赖的
   `wechat/WCDB.dll`、`wechat/wcdb_cli.exe`、`wechat/wx_key.dll` 的 SHA256；
   `Assert-WeChatArtifactPins` 在 source 与 portable 两个 phase 校验（路径安全、小写 64-hex、
   存在性、拒绝 reparse、hash 命中）；frozen 合同校验随包文件。证据：
   `tests/test_portable_runtime_copy.py::test_modified_wechat_native_asset_cannot_ship`、
   `tests/test_frozen_desktop_package_contract.py::test_frozen_package_ships_the_pinned_wechat_native_assets`
   与 `tests/test_windows_runtime_contract.py` 的 pin 合同。
   pin 值取自本机 `runtime/wechat/` 中被复制进发布树的那一份（`WCDB.dll` / `wcdb_cli.exe`
   由 `scripts/bootstrap_wechat_native.ps1` 从 Tencent/wcdb v2.1.15 本地构建，
   `wx_key.dll` 无 tracked bootstrap）。这是冻结“随包发布的那一份身份”，
   明确不是 bit-for-bit 复现（本地编译产物 PE 带时间戳）。

验收快照（只记录本次，不是固定测试数量要求）：Fast 2676 passed / 291 deselected；
Full 2964 passed、1 skipped、2 failed —— 1 个为已有 `known_failure`
（REL-08 分享按钮），另 1 个为与本项无关的环境性失败
（`tests/test_test_user_data_isolation.py` 的伪造 `LOCALAPPDATA` 被 Windows 物化出
`Microsoft\Windows\Caches`，守卫只拦 `Path.mkdir`）；skip 为未设置
`ECHO_NATIVE_WCDB_CLI_PATH` 的 native CLI 测试。fresh build 的 frozen / portable /
Windows runtime 合同 144 passed。

明确不在本次范围（人工确认）：EXE VersionInfo、commit marker / provenance framework、
code signing、CI/CD、bit-for-bit reproducibility。

状态：COMPLETE / CLOSED。本项关闭不代表 QA-01 / QA-03 / QA-06 完成。
REL-06B / REL-06C 合并后，最终候选包仍需重核资产 pin、隐私残留与 fresh build 来源；
历史 QA-02 通过不自动覆盖后续包变化。

### QA-03 版本号 / GitHub Release

统一版本权威（见 GOV-04），核对最终版本、tag、发布说明与 fresh build 资产后完成 GitHub Release。
历史 portable build 验收不等于正式 Release 已完成。
最终发布前需收口 Setup / Portable ZIP 资产、校验和、发布说明、第三方声明与已知限制；
以包含最终合并成果的 fresh build 为准。当前尚未完成最终 GitHub Release，
本次文档校准不执行 tag、上传或发布。

状态：未完成，0.1 发布前必做。

### QA-04 新版本检测与下载页

0.1 内置权威版本号 → 检查 GitHub 最新正式 Release → 提示新版 → 打开下载页，
由用户自行下载；不做自动下载、自动替换或静默更新。
Update Check Core 已实现：权威 `APP_VERSION` → GitHub latest formal Release →
严格 SemVer 比较 → Qt 无关 `UpdateCheckResult`。自动检查按所有尝试去重 24h，
手动检查复用核心并绕过去重；网络超时、离线、限流和非法响应返回安全结果。
仅在现有用户数据目录保存 `update-check.json` 的 `last_check_time`。
Facade 已提供 `check_for_updates(manual=False)`，构造/启动不访问网络。
截至 `baaad4e`，GUI 仍未接入 `check_for_updates`；后续需要 worker 异步调用、结果展示
及用户点击后打开校验后的 Release 页面。
当前未实现 GUI 接线、最终视觉与实际下载页交互验收；核心合同见 `ARCHITECTURE.md`。

自动化证据：`tests/test_update_check_service.py` 覆盖正式 Release、SemVer、异常响应、
网络失败、自动/手动检查、24h 边界、持久状态容错与同实例并发。
focused / Fast 通过；Full 唯一失败为既有 REL-08 分享按钮 `known_failure`。
Fast 验证过程中曾出现微信 GUI worker native access violation，重跑通过，原因尚未确认。
这是当时的验证快照；其中 REL-08 known_failure 已被 `d67f51e` 修复并移除标记，
native crash 风险仍见 Active Bugs，本次未重跑 Fast / Full，不能更新为当前整套通过。

状态：Update Check Core 已实现；QA-04 整体待 GUI 接线与交互验收，0.1 发布前必做。

### QA-05 0.1 → 0.2 本地数据兼容检查

已完成 Version / Data Evolution Contract 最小收口：新包在 `echo-report-meta.v1` 内
追加 app version、report schema version、analysis revision；旧包缺字段仍可读取，不补写。
固定虚构旧 0.1 metadata 回归覆盖 list / reopen / 超限 retention，并检查保留旧包的
文件内容与 mtime 未改变。证据：`tests/test_report_package_catalog.py`、
`tests/test_echo_report_export.py`；现有配置缺字段、portable 路径修复与 QCE 隔离覆盖沿用。

演进约束以 `ARCHITECTURE.md` 为准：历史分析快照不随 app upgrade 自动迁移或重算；
新算法 / 新数据库字段由新版重新 acquisition / analysis 生成新包。
0.2 reader 需保留 meta.v1 支持并对新增字段提供缺失语义；配置 loader 允许缺字段及
未知 key，但 writer 不保留未知 key，不承诺降级往返无损。
旧 JSON 新模板重渲染、自动重新分析 identity、migration framework 均不在本次范围。

验证：focused / Fast、正式 fresh Windows build、frozen package contract 与隔离用户数据的
EXE 启动版本 smoke 通过。Full 唯一失败为既有 REL-08 分享按钮 `known_failure`，
本次无新增失败；native WCDB CLI 测试因未设置专用路径跳过。

以上为该次收口的历史验证结果；分享测试的当前状态见 REL-08，不覆盖原有失败记录。

状态：COMPLETE / CLOSED。该合同不代表尚未实现的 0.2 软件已通过真人兼容验收。

### QA-06 跨机器 Direct DB RC

在其他 Windows 机器上验证 NapCat 启动 / 登录、Direct DB snapshot / decrypt、
分析报告及退出清理；本机已通过的 checkpoint 不替代此项。
使用包含 REL-06B / REL-06C 与 GUI 最终成果的候选包，覆盖首次运行、已有 QQ 后台进程、
升级后的 runtime、运行目录分离与异常恢复；不能用旧版本跨机器或源码运行替代。

状态：待真实验收，0.1 发布前必做，并纳入 QA-01 最终验收。

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

## Deferred Capabilities

明确不进入当前 Hardening 主线：

### 0.2 Backlog（已确认范围）

- Sticker / 表情包语义：现役 QQ Direct DB / WeChat 的完整身份、资源与语义支持；已有基础映射保留。
  已退休的 BUG-02 / QCE `type_17` 不属于后续兼容待办。
- Reply / 引用回复分析：已有 ReplyRelation 与 authored text 隔离不等于完整回复分析已交付。
- Local Data 高级批量管理：不重新打开已 CLOSED 的 BUG-03 基础生命周期能力。
- 快捷登录 / 统一 UX 优化：现有授权闭环不等于快捷登录完成，不阻塞 0.1。

以上均不阻塞 0.1。

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

非阻塞后续优化条目：

### REL-05 大型数据容量和 UX

旧 BUG-01 已退休，不再以其未知根因作为前置。
当前 Direct DB 大数据容量与响应体验先按 QA-01 验收，有新证据再决定是否需要优化。

状态：DEFERRED（普通后续性能 / UX 优化）。Release Blocker：No。
0.1 大数据真实验收仍属于 QA-01，不要求提前进行专项优化。

### REL-09 语言画像语义 / 代表词算法分工

后续审计“常说”与“更像 TA”的文案和算法是否对应：

- `top_words` 是成员自身纯词频排序，更接近“常说什么”，不宜承担过强的“代表性”语义。
- 现有 `DistinctiveWordAnalyzer` 的成员 vs 其他成员 distinctive-word / log-odds 排序
  更接近“哪些词更像 TA”；后续优化优先复用该能力。
- 数据不足时允许不展示特色词，避免强行生成低置信度结果。

状态：DEFERRED（后续产品 / 算法优化）。Release Blocker：No，不阻塞 0.1。

## 已完成的生命周期与工程治理

### GOV-06 Architecture & Complexity Audit v1

状态：COMPLETE / CLOSED（已确认完成）。Release Blocker：No。

已完成范围：

- Desktop QCE → NapCat + Direct DB 主链收敛；
- GUI ownership / lifecycle 审计；
- RichMessage / message consistency；
- QQ / WeChat source topology 与 application module grouping；
- package cohesion；
- readability cleanup；
- 相关高杠杆结构调整。

近期 main 中的主链收敛、GUI 生命周期、rich message 一致性、来源模块归组与可读性整理
均属于本阶段已完成工作。0.1 不再重复开展泛化全仓架构审计；发布前定点核验归 QA-02 / GOV-05。
历史 Direct DB / packaging checkpoint 保留，不将其验收范围扩大为最终发布已完成。

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

状态：当前桌面生命周期 CLOSED。旧 QCE transient orphan cleanup 已退出 Desktop 0.1 backlog，
历史限制见后文兼容边界，不重新打开 BUG-03。

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

状态：CLOSED（当前阶段已完成）。Release Blocker：No。

2026-10-05 / 06 当前阶段记录：

- `7aebc6e`：41 个真实 subprocess cases 标记为 slow_integration，移出 Fast，Full 保留。
- `c512d62`（T2A）：参数化重复结构、将等价断言合并到已有覆盖，不砍业务覆盖。
- `4e99bc8`（T2B）：共享 fixture / 虚构样本构造与重复测试结构整理，不砍业务覆盖。
- 已确认的性能快照：Fast 从约 70s 降到约 40s；这是本阶段测量，不是固定耗时合同，
  也不是本次文档校准重新运行 Fast 的结果。
- 分享 known_failure 仍归 REL-08，不重新打开测试治理。

详细历史记录见：`docs/engineering/TEST_GOVERNANCE_V1.md`

## Retired / Closed Bugs

### BUG-01 巨大 QQ 数据源分析失败（旧 QCE 路径，已退休）

已知事实：

- 当时 GUI 最终显示「分析过程中出现未预期的错误，请稍后重试。」
- 原始观察来自旧 QCE acquisition 路径，未确认失败阶段或根因。
- 已确认该旧问题早已不再存在；桌面 QQ 已切换为 Direct DB，且完成正式真人 E2E / 最终 smoke
  （`684a4ff`），旧 Desktop QCE runtime / rollback 已移除（`0ccf383`）。
- 退休依据是旧观察不再代表当前产品问题，不声称某个补丁修复了未经确认的根因。
- 当前 Direct DB 大数据与跨机器验收仍纳入 QA-01；若出现新失败，按新证据追踪。

状态：RETIRED（退出 Active Bugs）。

Release Blocker：No。

### BUG-02 旧 QCE market_face / type_17 兼容问题

审计结论（2026-10-06）：

- 旧记录将 `market_face` 与 `type_17` 并列，但没有证据证明二者等价。
  Git 历史中 `type_17` 仅进入过此 backlog；当前代码和测试未建立它的字段语义契约。
- 当时的 QCE adapter 曾将 `market_face` / elementType 37 映射为 sticker `ExpressionContent`，
  有 adapter 与 analysis-report 测试；顶层消息类型仍只接受 text / reply，不宣称支持 `type_17`。
- 当前桌面 Direct DB adapter 使用 protobuf `45002=11` 与 `45600` bytes 建立
  `qq-marketface:sha256:` 不透明身份，保留标签或安全 fallback；这不是 QCE 数字 emoji ID，
  也不能与旧 `type_17` 混同。已有虚构测试证明纯贴图、混合内容、重复次数与词频隔离。
- 前一轮校准的 focused tests：48 passed（本轮不重跑）。MarketFace 真人覆盖仍不足，完整 sticker 身份、资源与语义
  支持属于 0.2；现有证据未确认当前 0.1 correctness defect。
- 不把未知 `type_17` 加进允许列表，也不将其标记为已修复；后续若有正文丢失、分析失败或统计污染
  的新证据，应另按 correctness regression 审计。

状态：RETIRED（QCE JSON 与旧 QQ JSON/JSONL 输入能力已正式移除；退出当前兼容待办）。
退休不等于修复或确认 `type_17` 语义；现役 Direct DB / WeChat 的 sticker 扩展仍归 0.2。

Release Blocker：No。

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

### BUG-08 微信会话读取失败后仍停留在 loading

状态：CLOSED。Release Blocker：No。

`cbdf85b` 已让 query failure / unexpected error 清除会话读取状态，恢复空会话提示，
禁用分析并允许“重新开始”；成功路径仍显示实际会话。regression 为
`tests/test_gui.py::test_wechat_session_load_failure_exits_reading_state_and_allows_restart`。
本轮仅同步既有修复状态，不声称完成新的真人登录验收。

### QCE Final Retirement

状态：CLOSED（Stages 2–4 已移除全部产品与文件输入能力；Stage 5 同步事实源和发行合同）。

保留 public/product/file retirement tests、config migration protection、runtime forbidden
checks 和 frozen module absence 检查；它们只能阻止能力复活，不提供 QCE 运行或导入能力。
fresh build 与验收结果记录在本轮 Stage 5 checkpoint；不替代 QA-01 / QA-06 人工验收。

### QCE Final Retirement Stage 5 checkpoint（2026-10-07）

- 源码基线：Stage 4 `76d7476` 已提交并推送；本轮 Stage 5 working diff 尚未提交。
- RED：旧 frozen artifact 的 PYZ 仍含 7 个已退休 Python modules，新 absence 合同失败。
  fresh build 后该合同 GREEN；保留 runtime forbidden checks，不靠删除检查来通过验收。
- Focused：来源 / retirement / release 合同 337 passed；诊断 / template pin / bootstrap
  合同 218 passed；fresh package / release / Windows runtime 合同 100 passed。
- Fast：标准单进程命令 2617 passed、282 deselected；没有 GUI native crash。
- `scripts/build_windows_exe.ps1` fresh build 成功（PyInstaller 6.22.3，项目 Python 3.13.9）。
  `dist/Echo/Echo.exe` 为 Windows x64，3,398,866 bytes；生成时间为
  `2026-10-06T17:09:32.020700Z`（本地 2026-10-07）。SHA-256：
  `eeab7c5fa50211bd246e10735870f5b5a423199a28e1491dae7e75a23eeb21a6`。
- fresh PYZ 与发行树未发现 QCE provider/service、`qce_compat`、QCE adapter、旧 parser
  或 QCE runtime assets；Direct DB / WeChat provider、adapter 与 application modules 保留。
- Full：2897 passed、1 skipped、1 failed。失败为已有 `known_failure`
  `test_generate_share_button_creates_and_opens_share_image`（REL-08 按钮仍隐藏）；
  skip 为未提供 `ECHO_NATIVE_WCDB_CLI_PATH` 的 native CLI 测试。不能宣称 Full passed。
- `git diff --check` 通过。QCE Final Retirement CLOSED；这不是整体 Release Ready。
  REL-08、GOV-04、update check、RC / cross-machine acceptance 仍未完成。
  本轮未做真人 QQ / WeChat 登录、shutdown 或 report acceptance，保留人工验收安排。

## 历史 checkpoint 与兼容边界

以下记录保留工程证据，不作为当前 0.1 待办清单；当前归属以开头总览为准。

### 已退休的 Desktop QCE 项

REL-01 / REL-01.1 和 REL-03 中旧 QCE transient orphan cleanup 均已退出 Desktop 0.1 backlog。
当时保留的 QCE CLI 与既有 JSON 兼容也已在 Final Retirement 中移除；以下仍为历史证据。

REL-03 旧 QCE transient orphan cleanup：RETIRED（仅退休旧 Desktop 待办，不声称已实现）。
原记录关注 QCE transient run 异常终止后的遗留清理；当前 Direct DB generation 已有启动 / 关闭
`recover`，二者不是同一资源。保留该历史限制，不将其写成当前 Direct DB 生命周期缺口。

### REL-01 QCE 导出进度（Desktop 已退休）

目标：GUI 显示真实 QCE progress / messageCount / status，绝不伪造 totalMessages。

以下为旧 Desktop QCE 路径的历史设计与验收，不作为当前 Direct DB GUI 合同。

当时审计结论：
QCE 提供 messageCount、progress、status、message，
没有可靠标准 totalMessages / processedMessages。

状态：RETIRED（历史验收通过；退出当前 Desktop 0.1 backlog）。

当时设计：

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

旧 BUG-01 已退休；当前数据容量验收见 QA-01。

### REL-01.1 QCE 停滞提示（Desktop 已退休）

当 `message_count` 一段时间没有增长、但导出任务仍未结束时，用户容易误以为程序卡死。

当时考虑显示类似：
`已获取 4,379 条 QQ 聊天记录 · 正在完成导出，请稍候…`

约束：

- 只能说明“任务仍在处理中 / 导出尚未结束”；
- 不得猜测 QCE 正在进行审核、校验、安全检查等具体内部步骤；
- 不显示虚假百分比；
- 不预测剩余时间。

状态：RETIRED（旧 QCE UX debt；退出当前 Desktop 0.1 backlog）。

### Windows portable package hardening checkpoint（REL-06 历史记录）

当前 QCE Final Retirement 发布合同：先使用项目 `.venv` 的 Python 运行
`scripts/bootstrap_qq_napcat_runtime.py`（可用 `--archive` 复用官方 archive，仍校验 hash），
再运行 `scripts/build_windows_exe.ps1`。QQ 发布源为 `runtime/qq-napcat-candidate`，
不要求旧 QCE runtime 存在；Stage 4B 已移除旧 Desktop bootstrap 与 rollback。
QCE CLI、provider/service、文件 adapter 与旧 parser 均已退休；fresh PYZ 与发行树
不得包含这些 Python modules 或 `qce_compat`。
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

### QQ Direct DB 最终验收 checkpoint（2026-10-02）

桌面 QQ 会话查询与分析当前使用 Direct DB 主链；QCE CLI 与既有 JSON 文件兼容已在
Final Retirement 中移除，不存在 QCE fallback。架构与生命周期以 `ARCHITECTURE.md` 为准。

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

当时开放项与当前归属（历史记录，不是额外的 0.1 backlog）：

以下是 2026-10-02 当时的开放项：其中独立 history / `snapshot_reused` 兼容债已随
`ec766f2` 退休旧 history 并统一 Report Package 生命周期退出当前追踪，见 CLOSED 的 BUG-03。
GUI 分享仍开放且阻塞 0.1（REL-08）；MarketFace 完整语义归 0.2。
unknown session/member 展示按 REL-07 的实际 polish 范围收口；unknown 媒体语义不扩展 0.1。
快捷登录归 0.2 统一 UX 优化；跨机器 Direct DB RC 是当前发布待办，见 QA-06。

- history metadata `snapshot_reused` 兼容：旧记录与当前 identity summary 校验不兼容。
- unknown session/member UX 折叠。
- MarketFace 真人覆盖不足。
- unknown element 真人覆盖有限：仅确认自然出现的 unknown 段保留，不推断媒体类型。
- GUI share-image 既有 known_failure。
- 快捷登录尚未实现；现有 QQ 授权/连接闭环验收不等同于该功能完成。
- 跨机器 Direct DB RC 验证尚未完成；当前真人验收限定本机与已有场景，
  不构成跨 QQ 版本 schema 保证或全体发布环境准入。

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
  Windows build reproducibility 当时属于开放的 GOV-05 / 后续发布治理范围（2026-10-07 已随 GOV-05 收口）。

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
- RETIRED（旧条目退出当前追踪，不声称根因已修复）

同时允许：

- 候选 Bug
- Release Blocker：Yes / No / TBD

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
