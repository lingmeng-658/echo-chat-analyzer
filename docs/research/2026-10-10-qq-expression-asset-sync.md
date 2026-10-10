# QQ 系统表情资源补齐记录

**日期：** 2026-10-10
**分支/worktree：** `audit/qq-expression-assets`（独立 worktree `wt-algorithm-audit-qqface`）
**状态：** 已完成资源同步与组合文字兜底改造，暂未 commit/push/merge

---

## 1. 资源来源

- 仓库：https://github.com/koishijs/QFace
- 索引：https://koishi.js.org/QFace/assets/qq_emoji/_index.v2.json（`syncedAt=2026-09-28T03:43:28.805Z`）
- 资源 CDN：`https://koishi.js.org/QFace/<索引中 assets[].path>`
- 授权/合规：QFace 为社区维护的 QQ 表情资源镜像；仅做**本地静态资源同步**，不进入任何分析逻辑。

## 2. 索引与现有资源对比

- 索引条目总数 537：其中**数字 id 372** 个、Unicode 表情字符键 165 个（不在本次范围，忽略）。
- 同步前 Echo 内置：`frontend/echo_report/qq-emojis/` 250 个 PNG，id 覆盖 0–432（有空洞）。
- 对比结果：缺失 77 个 id = `{55, 418} ∪ {433..507}`，全部有**静态 PNG** 资源（无 apng-only，0 个过期）。

## 3. 同步结果

| 项 | 数量 |
| --- | --- |
| 同步前 | 250 |
| 本次新增 | 77 |
| 同步后 | 327 |
| 数字 id 覆盖率 | 327 / 372 = 87.9%（有栅格资源的 id 覆盖 100%） |
| 无法补齐 | 45 个 id（索引中无 PNG/APNG，仅 lottie 或无资源） |

**优先验证：**
- `474` `/给你一拳` → `qq:474`，128×128 静态 RGBA PNG，透明背景保留；
- `479` `/不对不对` → `qq:479`，128×128 静态 RGBA PNG，透明背景保留。

**图片处理（不简单改扩展名，最终统一为 128×128 方形 RGBA）：**
- 默认取索引的静态 `png` 资源（方形），用 Pillow 归一为 RGBA PNG；`449/466/468/469` 的 `png` 实为 APNG 内容，提取首帧；
- `485/486/487/501/502`（"开学啦/秋秋"横版 surprise 表情）的 `png` 是**共享占位图**（多 id 同一张），改用 `<id>_0.png` 首帧**居中裁方 + 重采样到 128×128**；
- 最终 77 张全部为 128×128 方形 RGBA，透明背景保留，SHA-256 校验无重复内容。

## 4. 使用边界（未补齐部分）

- **45 个无栅格资源 id**（lottie-only / 空）：`122,180,193,194,198,200,202,203,204,206,210,211,214,215,216,217,218,219,221,222,223,224,225,226,227,229,230,231,232,233,235,237,238,239,240,241,243,244,278,288,290,292,301,322,348`。这些 id 在报告里仍走文字兜底，不再影响次数/邻近词/组合展示。
- 索引中 165 个 Unicode 表情字符键不属于 `<face_id>.png` 契约，未处理。
- MarketFace（`45002=11`）的 sha256 派生 key 仍是结构性缺口，与本次资源补齐无关。
- `isHide` 不是"无效"信号（同步前 250 个均 `isHide=True`），未据此过滤。

## 5. 代码改动（组合文字兜底）

需求：缺图表情组合仍应显示文字，不能因一张图缺失整组消失。

- `presentation/models.py`：`EchoExpressionCombination` 增加 `labels` 字段。
- `presentation/builders.py`：`_display_expression_combinations` 去掉"成员全部有图"过滤；`_to_echo_expression_combination` 计算每个成员的 `labels`（`[...]` 归一为"表情"）。
- `presentation/echo_serializer.py`：组合序列化输出 `labels`。
- `presentation/echo_report_template.py` 与 `frontend/echo_report/app.js`：组合渲染对无图成员回退为文字 span。

## 6. 打包契约

`LocalChatAnalyzer.spec:37,46` 已把整个 `frontend/echo_report/qq-emojis` 目录作为 datas 打包，新增 PNG 自动纳入，**无需改 spec**。

## 7. 测试结果

- 聚焦测试（expression analyzer / serializer / frontend / presentation）：117 passed。
- Fast Suite：3308 passed，5 skipped；4 个失败全部为 `test_frozen_qq_resource_contract.py`，原因 `ModuleNotFoundError: No module named 'PyInstaller'`（venv 未装 build 依赖，与本改动无关的既有环境问题）。
- `git diff --check`：通过。

## 8. 收口检查结果（2026-10-10）

1. **真实 Chromium 验证**（`chrome.exe --headless=new --dump-dom`，虚构数据）：
   `474`/`479` 渲染为 `<img class="expression-asset" alt="/给你一拳"|"/不对不对">`（base64 内联），
   缺图组合（474 + 999）渲染为图片 + `<span class="expression-fallback">表情</span>`，组合区 2 项正常。✅
2. **77 张 PNG 完整性**：128×128 方形 RGBA、无空白/损坏/动图、透明背景保留、SHA-256 无重复；**总体积 1,183 KiB（约 1.16 MB）**。✅
3. **原始 250 张未变**：`git ls-files` 确认 250 张均为 tracked 且 `git diff --name-only` 无改动，77 张为新增 untracked。✅
4. **双前端同步**：模板内联 `ECHO_REPORT_APP_JS` 与 `frontend/echo_report/app.js` 均含组合文字兜底；`test_template_js_syntax`（node --check）与 marker 同步测试通过。✅
5. **版本 revision**：`schema_version` 维持 `echo-report.v0.7`（新增 `labels` 为向后兼容的纯展示增量，reader 忽略未知字段）；`analysis/revision.py` 未动（纯 presentation 改动，符合 `ARCHITECTURE.md:409-411`）。✅
6. **Top-N 组合榜 + 有界留存**：组合榜/边界/留存相关测试 8 + 2 passed，无回归。✅
7. **PyInstaller 环境性失败**：`test_frozen_qq_resource_contract.py` 4 项失败为 venv 缺 PyInstaller 所致（spec 顶层 `from PyInstaller.utils.hooks import copy_metadata`），与本次改动无关，已单独记录；QQ 表情资源打包由 `LocalChatAnalyzer.spec:37,46` 整目录 datas 覆盖，无需改 spec。

**结论：可以提交。新增资源 77 张，总体积约 1.16 MB（1,183 KiB）。**
