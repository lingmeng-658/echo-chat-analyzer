# Echo 三分支集成验收记录（2026-10-10）

状态：源码集成完成；本机测试未全绿，发行与真实用户验收仍待台式机完成。

## 基线、拓扑与修改范围

- 原工作树 `local-chat-analyzer` 保持干净，仍在原 `main`，没有更新或合并 main。
- fetch 后基线：`origin/main` = `937d0d6ed5f835ba0d3ecdea4d2e0d4286fc3e25`。
- 集成 worktree：`D:\ChatAnalyzerWorkspace\wt-pre-release-acceptance`。
- 集成分支：`integration/pre-release-acceptance`。
- 按顺序使用普通 `git merge --no-ff`，保留来源提交历史：

| 来源 | 固定提交 | 合并提交 |
| --- | --- | --- |
| `origin/audit/algorithm-quality` | `ec855814fe21c3ca22103acb66c34fa8c3232b94` | `347d298` |
| `origin/audit/qq-expression-assets` | `4a11099d6faa47c8ad13bd3678e5d5d5de1c793f` | `b9f39d6` |
| `origin/fix/echo-report-voices-layout` | `98bca269cde4cbf62c7da5501f6b613c571450ca` | `479246c` |

资源分支直接继承算法分支；算法四个提交只保留一份，资源与布局分别增加一个来源提交。
三次合并均无文本冲突；Git 自动合并 `tests/test_report_package_catalog.py` 和
`src/qq_chat_analyzer/presentation/echo_report_template.py`，未手工改写生产代码或测试。
代码集成提交为 `479246c1032a1ed6e6d6e6afaf0460ea20c69f2a`，后续提交仅增加本记录。

相对基线的 114 个来源变更文件与三分支文件集合完全一致；额外范围仅为本验收记录。
没有加入真实聊天数据、账号信息、测试日志、虚拟环境或 runtime。

## 保留内容与验证

- 分析 revision 为 `echo-analysis.v5`，包含稳定身份过滤、模板字面量转义、表达组合统计与有界报告留存。
- QQ 新增 77 张 PNG：逐张验证格式、128×128 尺寸、RGBA、静态帧、非空白、内容哈希不重复。
- `frontend/echo_report/app.js` 与资源分支内容一致；组合的无图成员保留文字兜底。
- `frontend/echo_report/style.css` 与布局分支内容一致；内联模板保留两项改动。
- focused 中真实 Chromium 桌面双列/窄屏单列布局测试通过，覆盖全部虚构成员、六张可见卡片及溢出检查。

## 环境与执行方法

Python 为恢复后的项目 `.venv` 中 Python 3.12.10；pytest 8.4.2。
必需依赖 `jieba / matplotlib / wordcloud / zstandard` 可导入，`pip check` 通过。
新 worktree 的 `.venv` 是指向原项目虚拟环境的本地 junction；没有新建环境或安装依赖。
每次测试显式设置源码路径，已验证导入文件来自集成 worktree：

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')
$env:PYTHONIOENCODING = 'utf-8'
```

所有测试使用仓库虚构 fixture 与隔离临时目录，没有连接真实 QQ/微信或读取真实聊天。
Chrome 与 PySide6 可用；本机 PATH 无 Node.js，虚拟环境无 PyInstaller。
集成 worktree 无 QQ/NapCat 本地 runtime，微信的 `WCDB.dll / wcdb_cli.exe / wx_key.dll`
也不存在；没有 Frozen/Portable 构建产物。未尝试安装、复制 runtime 或构建发行包。

focused 选择三分支变更的测试文件，再加资源、词汇边界、展示和 Frozen 资源合同测试：

```powershell
$focused = @(git diff --name-only 937d0d6 HEAD -- tests | Where-Object { $_ -like '*.py' })
$focused += @('tests/test_expression_assets.py', 'tests/test_expression_lexical_boundary.py',
              'tests/test_presentation.py', 'tests/test_frozen_qq_resource_contract.py')
.\.venv\Scripts\python.exe -m pytest @focused -q --tb=short
.\.venv\Scripts\python.exe -m pytest -m "not slow_integration and not known_failure" -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q --tb=short
```

## 本轮结果与限制

| 层级 | 通过 | 失败 | setup 错误 | 跳过 | 其他 |
| --- | ---: | ---: | ---: | ---: | --- |
| 合并前 focused 基线 | 35 | 15 | 0 | 0 | 均因缺少 Node.js |
| 集成 focused | 587 | 20 | 0 | 0 | 16 项 Node.js、4 项 PyInstaller；exit 1 |
| Fast | 3328 | 41 | 0 | 19 | 349 deselected；37 项 Node.js、4 项 PyInstaller |
| Full | 3448 | 56 | 155 | 78 | 1 条 Pillow 弃用 warning |

Full 的失败分类：49 项缺少 Node.js（46 项进程启动失败、3 项前提断言），
6 项缺少 PyInstaller，以及 1 项 Windows Job 句柄计数失败。
155 个 setup 错误均为虚构 main/WAL fixture 启动 Node.js 失败。
跳过项包含 Node.js、原生 runtime、Frozen 发行产物等环境前提缺失，不能算作通过。

Windows Job 用例 `test_normal_exit_unicode_env_cwd_pipes_and_no_handle_leak`：
Full 中句柄计数从 1238 增至 1244；集成 worktree 单独复跑为 191→197，exit 1。
为确认基线，在独立 detached worktree `D:\ChatAnalyzerWorkspace\wt-pre-release-baseline`
的最新 main `937d0d6` 上运行同一节点，同样为 191→197，exit 1。
相关实现和测试在本次集成中未变；这是本机最新 main 已可复现的原生问题，未修复、未改预期。

Fast 和 Full 均输出完整测试统计后返回 `-1073741819`（`0xC0000005`，Windows access violation）。
日志没有提供原生崩溃堆栈，原因未确定；不能将其等同于依赖缺失，也不能声称已修复。
这两轮 suite 均未通过。Fast 与 Full 在各自进程、隔离 fixture 下部分重叠执行；
台式机需串行复验原生稳定性。

日志仅在本机仓库外：`D:\ChatAnalyzerWorkspace\integration-acceptance-results`，
包含 `focused.log / fast.log / full.log / windows-job-focused.log / windows-job-main-baseline.log`。
本记录未纳入日志原文。已检查工作树 diff 与相对 main 的累计 diff，无空白错误。

## 台式机后续验收

1. fetch 集成分支，在干净独立 worktree 核对交付 SHA，使用台式机既有完整 `.venv`、
   Node.js、固定版本构建工具和受控 QQ/微信 runtime；串行重跑上述 focused、Fast、Full。
   单独复验 Windows Job 句柄节点，排查 `0xC0000005`；保留失败证据，不改测试预期。
2. 生成新报告确认 `analysis_revision=echo-analysis.v5`；对虚构样本核对同名不同身份、
   模板字面量、表情次数、组合排行、低排名补位及有界留存。
3. 在真实 QQ Direct DB 链路完成启动/登录、会话读取、main+WAL snapshot/decrypt、
   群聊与私聊分析；微信完成对应本地读取与分析。真实数据只留在该机器，不上网、不提交。
4. 新报告核对 QQ 474/479 图片、无资源表情及混合组合文字兜底；
   群语言画像宽屏双列、六成员可见、长名称不溢出、窄屏单列、全部成员可滚动查看。
5. 验收 HTML/JSON、报告历史、导出与分享图片；正常退出、异常退出再启动，
   确认 plaintext generation 清理/recover 与自有 QQ 进程树退出，不影响用户自开的 QQ。
6. 按既有构建/Portable 流程在台式机生成 fresh artifact，复跑 Frozen 合同与真实启动、
   图片资源、分享及退出验收，并检查包内无账号状态、聊天数据或密钥。

本任务仅提交并普通 push 集成分支，不合并 main、不创建 PR/Release、不删除其他分支。
