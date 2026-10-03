# Stage 3.5I2：hardened PoC 准入验证

范围：独立真人验收 harness、虚构生命周期测试及本文；未修改 main/WAL 算法、
正式 snapshot helper、Provider、GUI、A4/A5 或旧 fail-closed 保护。
真人测试只通过本机 loopback RPC 获取目录、调用现有进程内解密，未获取密钥。
完整路径、原始 RPC envelope、payload、salt、内容 hash 和聊天字段均不输出或记录。

## 真人结果

在持续运行的 QQ/NapCat 下，hardened PoC 连续生成五次加密合并快照，调用进程内
DatabaseApi 解密，并以只读 immutable 连接执行 quick_check、完整 integrity_check、
schema 表数量和固定消息表的 count 查询。五次全部通过，且每次消费后 staging
均已删除。未将任何真实数据库或消息记录放入仓库。

| 次序 | 选定 B | 最终 index committed frame | 检查结果 | staging 清理 |
| --- | --- | --- | --- | --- |
| 1 | 17 | 17 | 全部通过 | 完成 |
| 2 | 40 | 41 | 全部通过，固定 B=40 | 完成 |
| 3 | 41 | 41 | 全部通过 | 完成 |
| 4 | 97 | 97 | 全部通过 | 完成 |
| 5 | 97 | 97 | 全部通过 | 完成 |

每次 main identity/content/stat、WAL generation/完整选定前缀及 SHM witness
校验均成立。每次 backfill/attempted 前后均为零。
第二次读窗口内 index 从 40 推进到 41，是实际 append-after-B 成功的证据；
产物仍绑定明确的 40。整个验收期间观测到源文件活动变化，结束后
DatabaseApi.hasPassphrase 仍返回 ready。未重启、停止或向 QQ 发送消息。

此次真人窗口未出现不兼容 checkpoint/reset，因此不声称真人触发了这些故障。
这些 fail-closed 条件由 Stage 3.5I 虚构并发测试覆盖；本轮重跑，未增加降级、
retry、checkpoint-lock 或 main-only fallback。

## 生命周期规则

`main_wal_acceptance.py` 是独立 Windows PoC harness，正式链路不 import 它。

- 根目录固定在仓库外的本机临时区域，须有固定版本的 PoC ownership marker。
  根目录不能与源 QQ 数据目录重叠；根路径和清理项不能经过 symlink/junction。
- acquisition/startup 先获得 OS byte-range 独占 lease，持有到消费和清理完成。
  其他活跃进程拿不到 lease，不能清理正在使用的 staging。
- kernel 在进程强制终止时释放 lease。下一次 acquisition 在 lease 内先 recover，
  无需 finally、PID 存活推测或可重用 PID 来判断遗留文件。
- staging 有自己的 owner marker，且只允许固定的 main/WAL/merged/plaintext
  和 SQLite sidecar 文件名。先验证全部成员，再删除任何成员；未知文件、
  不匹配 marker、reparse point 或子目录一律失败，不递归清理用户数据。
- marker 最后删除。删 plaintext 失败时 marker 和残留可安全识别，错误传播，
  后续 acquisition 必须先成功清理，才能生成新产物。
- kill 在 mkdir 与 marker 之间留下的空 staging 可安全移除；非空无 marker
  staging 拒绝处理。当前调用的 marker 写入异常会清除其刚创建的空 staging。
- 正常消费完成、普通异常和可捕获中断均走清理。强杀依靠下一次 recover。
  本轮不复制源 main/WAL；如果后续加入这些副本，也必须使用相同 staging
  allowlist。真实源文件只读，永远不作为删除目标。
- 输出独占创建，碰撞不能覆盖或误删已有输出。已属于本轮 staging 的文件
  在本轮消费窗口结束后统一清理；未知来源文件不能仅因名字相同就删除。

## 与正式 staging/generation 的映射

已审计既有 `snapshot.mjs`：acquire 在解密前 cleanSlate；recover 在 startup
清理旧 staging/generation；cleanup 删除消费完的 generation；所有 mutating
操作串行。对 staging 的整体回收也涵盖未来新增的加密合并文件和 sidecars。
本轮以原有 runtime/lease 测试回归这些行为，没有改变原 helper。

3.5J 接入时仍须落实这些已经确定的接口规则：同一受控 snapshot root 只有一个
活跃 owner；hardened 合并和解密只写 staging；加密副本在发布前删除；
发布后由既有 generation lease 在消费结束清理；startup/下一次 acquire 先 recover；
清理失败不能返回成功或使用旧 generation。正式 helper 的 best-effort
discardStaging 不能被解释为“清理已成功”，其遗留必须由 fail-closed recover
处理。本轮未将独立 harness 直接接入或改写正式 generation API。

## 测试与准入判断

虚构 RED → GREEN 覆盖正常/异常清理、真实 subprocess 强杀后重取、OS lease
跨进程竞争、未知根/未知 staging、源目录重叠、输出碰撞、cleanup 失败后阻断
及恢复、root/staging junction 和 marker 写入失败。测试不使用真实 QQ 数据。
重跑 main/WAL focused integration、runtime/lease focused 与 Fast Suite；
diff-check 同时覆盖 tracked 和本轮 untracked 文件。

两个遗留准入问题已得到本轮证据支持：真实 QQ 的 SHM/prefix/boundary guard
成立，受控 staging 的正常及强杀生命周期可验证。因此具备进入 3.5J 正式接入
开发的条件。此结论不等于正式链路已上线或接入后免于新的回归/真人验收。
