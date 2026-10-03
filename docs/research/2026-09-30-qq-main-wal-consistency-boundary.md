# Stage 3.5I：main + WAL PoC 一致性边界

范围仅为 `scripts/qq_direct_db_snapshot/main_wal_poc.mjs` 及虚构 fixture 测试。
两个入口（加密合并、直接明文输出）共用同一个 capture 窗口；未修改正式
Provider、GUI、snapshot runtime、A4/A5 或原有 fail-closed 保护。

格式依据：[SQLite WAL 文件格式](https://www.sqlite.org/fileformat2.html#wal_format)、
[SQLite WAL-index 格式](https://www.sqlite.org/walformat.html)。当前 PoC 限定
Windows little-endian SHM、4096 字节页和既有 QQ 加密页布局。

## 确定 committed boundary

在读取 main 内容及 WAL 前读取必需的 SHM witness。检查两个 index header 副本、
header checksum、版本、初始化标志、页大小、checksum 字节序和文件身份。
复读 header 与 checkpoint counters；读 mark 和锁字节不作为一致性证据。
SHM 缺失、过短、撕裂或不支持的格式直接失败，不能退回 WAL 文件大小猜测。

冻结该 witness 的 `mxFrame = B`。仅读取 WAL header 与 frame 1..B；
每帧验证合法 page number、generation salt、完整 rolling checksum 链。
WAL header 验证 magic、version、page size、checksum。
B 必须是非零 commit marker，数据库页数、末帧 checksum、salt、checksum
字节序必须与冻结的 index 对应。损坏的选定前缀不能退回较旧 commit。

每页选择 B 以内最近的 committed WAL 版本，否则读取 main。事务缩小时删除
已超出数据库大小的旧页映射；最终输出精确为 committed page count。
新增且 main 不存在的页必须在选定 WAL 中找到。页一必须保留同一加密 salt。

这使 boundary 表示 index 已公布的 commit，排除了虽写出 commit frame、
但尚未公布到 index 的事务，也排除了尾部旧 generation 遗留字节。

## 读取窗口和不变量

1. 首先记录 SHM witness；打开 main，记录文件身份、stat guard 和完整内容
   SHA-256。此后读取冻结 WAL，再构建输出。
2. main 读取结束后比较身份、stat guard、完整内容 SHA-256。hash 分块读取，
   不将整个 main 额外装入内存。原有 main 变化拒绝策略保留并加强。
3. 重新读取、完整校验 WAL 1..B；header、文件身份及选定前缀 SHA-256 必须相同。
   单独比较末帧存储的 checksum 字段不够，因为 payload 可以改变而字段不变。
4. 最后再次获取有效 SHM witness：文件身份、salt 不变，mxFrame 不倒退；
   `nBackfill` 和 `nBackfillAttempted` 与初始值完全一致。
   若 mxFrame 未增长，还须重新对应同一个 index commit。
5. 只有上述检查全部通过，调用者才能消费输出。末次校验后源库继续写入不影响
   已物化的产物，因为源文件已不再参与产物读取。

在同一 generation 内，checkpoint counters 的进度变化一律保守拒绝，
即使 checkpoint 目标不超过 B；main 内容变化也拒绝。
开始时 `nBackfill <= nBackfillAttempted <= B` 是必需条件。
已经启动且只会 backfill B 以内页的 checkpoint，即使 counters 暂时不变，
其写入页也由选定 WAL 覆盖；这不意味着可以接受 checkpoint 到 B 之后。
到 B 之后的 checkpoint 会推进 attempted；reset 会改变 generation 或使
boundary 失效；truncate、文件替换、缺失和短读均关闭输出。

这些是遵守 SQLite WAL/index 协议的本机数据源的乐观验证条件，不能替代
SQLite 持有 read transaction 的锁协议，也不证明抵抗恶意跨文件 ABA、
源程序绕过 WAL 协议、hash collision 或不可靠文件系统一致性。
如果真人 QQ 的 SHM 不符合这些条件，必须失败，不能为了可用性移除 witness。

## 允许与拒绝

| 读取期间行为 | 结果 |
| --- | --- |
| 同 generation append 新已公布 commit，main/checkpoint/选定前缀不变 | 成功，仍返回 B |
| append 已写 commit，但 index 尚未公布 | 成功，仍返回 B |
| append 未提交完整帧或部分尾字节 | 成功，仍返回 B，不读取尾部 |
| B 以内 header/frame/page number/salt/checksum/commit marker 无效 | 失败，无旧 commit fallback |
| main 内容、身份或原有 stat guard 变化 | 失败 |
| checkpoint counters 进度变化，包括 B 以内的进度 | 失败 |
| WAL reset / salt 改变 / truncate / 选定前缀改变 / 文件替换 | 失败 |
| SHM 缺失、撕裂、checksum 错误、身份变化、index 与 commit 不符 | 失败 |
| 异常、可捕获中断、缺页、输出创建或校验失败 | 失败并清理本次拥有的输出 |
| 输出文件已存在 | 失败，保留原文件 |

## 最小匿名 source state

内部必须比较：main 文件身份、stat guard、长度及完整内容 hash；WAL 文件身份、
完整 header（包括 generation salt）及 1..B 的完整前缀 hash；SHM 文件身份、
经校验的 index header、B、nPage、末帧 checksum、backfill/attempted。
身份、salt、内容 hash 和任何原始字节只在本次调用内使用，不输出或持久化。

返回的匿名摘要只有：前后 committed frame、backfill、attempted，选定 B、
page/frame/commit 数量，以及 main 身份/内容、WAL generation/前缀和
checkpoint witness 校验成功布尔值。摘要是本次程序验证结果，不能独立重建
或离线证明 snapshot；单凭 size/mtime 或几个匿名计数不构成一致性证明。

## 虚构数据验证与清理边界

测试用真实 SQLite 创建虚构表，再构造相同 framing 的加密 fixture 和 matching
SHM witness。确定性同步 barrier 覆盖 main 基线读取、WAL frame 读取、
boundary 冻结、逐页输出和输出完成阶段，无 sleep 竞争。

覆盖新 commit（包含不同的虚构正文）、未公布 commit、未提交帧、torn tail、
checkpoint counters、main/WAL payload 修改、header 字段、frame 字段、
commit marker、缺失/损坏 SHM、选定帧短读、相同内容文件替换、输出碰撞和异常。
同时检查固定 boundary 产物与之后新 boundary 产物的不同查询结果；执行
SQLite quick_check / integrity_check。两种 WAL checksum 字节序都有覆盖。

RED 揭示了旧 PoC 的缺失 witness 仍成功、输出碰撞误删文件，以及缺少确定性
并发 barrier。GREEN 后显式运行 focused subprocess integration 和 Fast Suite。
本测试文件归为 slow_integration，Fast 通过不能替代其显式运行。

finally 只清理本次独占创建的文件，并确保关闭失败不会跳过其他清理。
清理失败继续以异常返回，不报告成功。没有添加 SIGKILL/TerminateProcess
恢复机制：强制终止不能执行 JavaScript finally。正式接入必须把这类产物放进
既有受控 staging/generation 生命周期，由 recover 清理；不能直接把 PoC
任意 outputPath 当作正式可发布的文件。

## Stage 3.5J 判断

一致性算法和虚构并发回归可以作为 Stage 3.5J 的候选设计输入；本轮没有进行
真人 QQ 验收。Stage 3.5H 的真人成功不能证明新增 SHM witness 在 QQ/Windows
实际映射和文件读取语义下可用。进入正式接入前还需匿名验证这些新 guard，
并明确 staging/recover、强制终止清理、清理失败传播及正式发布窗口。
因此当前不应直接替换正式获取链路；不能声称已经达到正式接入验收标准。
