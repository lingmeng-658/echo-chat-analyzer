# Echo Bug Journal

> **定位**：只记录「已经解决并验证」的真实工程问题。
>
> Active Bug 不放这里，放 `docs/HARDENING.md`（它同时承担 Active Bug Backlog）。

## 固定模板

每条记录按以下结构书写：

1. 现象
2. 为什么难查
3. 当时错误 / 竞争假设
4. 最终根因
5. 原代码的隐含假设
6. 为什么开发机或普通场景没有暴露
7. 哪个诊断 / 实验真正钉死根因
8. 最终修复
9. 可推广的工程经验
10. 可以反向审计仓库的规则
11. 对应 regression test

---

## Journal 001 — WeChat 多账号数据库与 Key 错配

### 1. 现象

在真实朋友机器上，微信连接 / 数据库读取失败；
机器存在非默认盘符和多个账号数据目录。

### 2. 为什么难查

Key 获取链和 `session.db` 选择链各自看起来都能成功，
失败发生在两条链组合之后。

### 3. 当时错误 / 竞争假设

包括路径发现错误、Key 提取失败、WCDB 兼容问题等。

### 4. 最终根因

Key capture 选择了一个 Weixin.exe / account，
Provider 又独立选择了另一个 `session.db`；
系统没有「Key 与数据库必须属于同一账号」的验证。

### 5. 原代码的隐含假设

「机器上只有一个可用微信账号 / 数据库候选，
任意成功 Key 可以读取任意发现的 `session.db`」。

### 6. 为什么开发机或普通场景没有暴露

现有封版记录不足以确定，本 Journal 不补充未经验证的推断。

### 7. 哪个诊断真正钉死根因

对数据库候选逐个使用捕获 Key 执行真实可读性验证，
确认只有匹配账号数据库可成功读取。

### 8. 最终修复

- 使用同一 WCDB InnerHandle prepare / step / read 路径做可读性验证；
- probe 候选数据库；
- 只有唯一 readable account 时选择；
- 持久化前再次 official verify；
- provider cache / invalidation 与 GUI directory recovery 配合。

### 9. 可推广的工程经验

任何 credential / key 与 resource / database 的自动发现都不能独立完成后直接组合；
必须验证它们属于同一 identity / domain。

### 10. 可以反向审计仓库的规则

搜索所有「独立发现 credential + 独立发现 resource + 最后组合使用」的链路，
确认是否存在 pairing verification。

### 11. 对应 regression test

以下测试名称已通过 git history 在仓库中核实，由本次修复引入并保留：

- `tests/test_wechat_database_probe.py::test_probe_uses_the_same_key_for_all_unique_candidates`
- `tests/test_wechat_database_recovery.py::test_probe_result_preserves_owning_account_data_root`
- `tests/test_wechat_database_recovery.py::test_unique_readable_candidate_recovers_to_owning_account_root`
- `tests/test_wechat_database_recovery.py::test_multiple_readable_candidates_do_not_auto_recover`
- `tests/test_wechat_db_source.py::test_verify_readable_keeps_the_key_off_the_command_line`
- `tests/test_wechat_db_source.py::test_sanitize_wcdb_message_redacts_path_key_and_sql`

该修复同时新增了 probe / recovery / setup service / facade 侧的多条覆盖，
此处只列与「Key 与数据库必须同账号」这一根因边界最直接相关的条目。

### 历史状态

CLOSED / merged。

历史修复 commit：

```text
387f1fa14ce209eb5bcc36a8e10b6fbce95416c8 fix(wechat): recover database root matching captured key
c118929b73f746e1f199ed3e7e96f33f0d089c3a Merge pull request #15 from lingmeng-658/fix/wechat-wcdb-prepare
```

---

## Journal 002 — QQ structured expression fallback 污染普通文本统计

> 说明：本条第 6 项没有足够历史证据，因此明确保留未知；
> 第 9、10 项为基于已确认根因总结出的工程经验与审计规则。

### 1. 现象

QQ 私聊 / 群聊普通词频和「你常说 / TA常说」
被结构化表情的 fallback name 污染。

### 2. 为什么难查

单条 QCE payload 同时含 aggregate text 与 structured expression，
单看两者都像合法数据。

### 3. 当时错误 / 竞争假设

tokenizer、stopwords、presentation、expression analyzer 等。

### 4. 最终根因

`qq_chat_exporter_adapter::_build_rich_contents()`
把 aggregate `content.text` 作为 `TextContent`，
同时又提取 `ExpressionContent`。

于是同一结构化表情同时进入：

- ordinary lexical text
- expression analytics

### 5. 原代码的隐含假设

QCE aggregate `content.text` 永远代表用户真正输入的普通文本。

### 6. 为什么开发机或普通场景没有暴露

封版记录未包含本项，待人工补充。

### 7. 哪个诊断真正钉死根因

构造三个最小样本：

- expression-only
- authored text + expression
- 用户真的手输 Laugh

这三个样本把「fallback text」和「真实 authored text」
的语义边界钉死。

### 8. 最终修复

结构化 QQ expression 保留在 `ExpressionContent`；
其 fallback text 不进入普通 lexical stats；
用户真实输入同名词仍正常统计。

### 9. 可推广的工程经验

（据根因补充）结构化能力与普通文本统计必须由显式的语义边界分开：
「展示用的 fallback 文本」不等于「用户 authored 的普通文本」。
两者若共用同一条进入统计的路径，就必然互相污染。

### 10. 可以反向审计仓库的规则

（据根因补充，供人工确认）检查所有「结构化内容 + 其展示 fallback 同时向后传递」的链路，
确认 fallback 文本是否也被当作普通文本进入 lexical 统计。

### 11. 对应 regression test

以下测试名称已通过 git history 在仓库中核实，为本修复的永久回归要求：

- `tests/test_qq_chat_exporter_adapter.py::test_structured_expression_fallback_is_not_text_content`
- `tests/test_qq_chat_exporter_adapter.py::test_mixed_expression_fallback_preserves_only_authored_text`
- `tests/test_qq_chat_exporter_adapter.py::test_plain_text_named_like_expression_is_preserved`
- `tests/test_analysis_reports_service.py::test_private_qce_expression_fallback_does_not_leak_into_voice_words`

永久保留：

- expression-only
- mixed authored + expression
- literal typed word
- private profile regression

### 历史状态

CLOSED / merged。

历史修复 commit：

```text
08b644df7d76975a0837e223932ca8f9431c20a0 fix(qq): keep structured expressions out of text stats
0892cd704e840ca04c30b115f3bcfb787779927c Merge pull request #16 from lingmeng-658/fix/qq-expression-text-leak
```

**特别注明**：后续观察到 Facepalm / Sob / Laugh / ThumbsUp 的截图属于 WeChat，
不能把它当作这个 QQ Bug 重新出现的证据。
QQ 与 WeChat 必须分别追根因。