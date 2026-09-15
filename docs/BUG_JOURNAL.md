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

---

## Journal 003 — WeChat 英文官方表情别名污染普通语言统计

### 1. 现象

真实 WeChat 会话中，英文官方表情 code（`Facepalm` / `Sob` / `Laugh` /
`ThumbsUp` 等）出现在普通语言画像里，例如「你常说 / TA常说 / 同频」词表。
表情本身在 UI 中显示为图片，但这些英文名以普通 token 的形式进入了统计。

### 2. 为什么难查

同一段 `[Facepalm]` 文本同时穿过三条链：

- expression 识别（本应命中官方表情）；
- tokenizer lexical preprocessing（负责处理 bracket 标点）；
- 普通词频 / 语言画像统计。

三条链各自看都「正常」：表情报告里有表情，词频里也有词。
污染只在两条链的**交界处**成立，单看任何一条链都不像错误。

### 3. 当时错误 / 竞争假设

- 英文 stopword 覆盖不足：应该补更多英文停用词；
- 英文词本来就不该进入中文语言画像：应该屏蔽所有英文；
- bracket 文本都是噪声：应该删除所有 `[A-Za-z]+`；
- tokenizer 或 expression analyzer 单点故障。

这些假设都被最终证据否定：污染词不是功能词，而是官方表情 code；
`[TODO]` / `[AI]` / `[Python]` 是用户真实内容；
bare `Laugh` / `Lol` 也是用户真实输入。

### 4. 最终根因

```text
official WeChat expression English alias
→ expression recognizer 未接住
→ bracket punctuation 被 lexical preprocessing 去除
→ alias body 被当成 ordinary English token
→ 泄漏进 language profile
```

即：官方表情的英文 bracket alias 不在 expression 识别表的覆盖范围内，
识别失败后文本没有被标记为「未知表达式」，
而是被当作普通文本继续走 lexical 预处理，最终成为普通 token。

### 5. 原代码的隐含假设

「WeChat 官方 expression bracket code 只有中文 canonical name 一种书写形式。」
以及由此导出的：「expression 识别未命中时，bracket 内容不会成为普通语言 token。」

### 6. 为什么开发机或普通场景没有暴露

已确认的部分：既有样本与测试使用的中文 canonical name（`[捂脸]` 等）
一直能正常识别，链路不会出错；
只有出现英文 alias 输入时，才进入「未命中 → 降级为普通文本」路径。
封版记录未包含本项的完整暴露条件，未经验证的推断不补写。

### 7. 哪个诊断 / 实验真正钉死根因

用虚构样本做最小对照，同时观察 expression 识别与 tokenize 输出：

- `[Facepalm]`（英文 alias）→ 未命中 expression，本体进入 lexical token；
- `[捂脸]`（中文 canonical）→ 正常识别为同一表情，不进入 lexical token；
- `[TODO]`（普通 bracket text）→ 本来就应该保留为普通 token。

后续在 alias 全量核对时，`[Pooh-pooh]` 暴露了第二个缺陷：
hyphenated ASCII protection 比 expression masking 先执行，
把带连字符的 alias 提前替换成占位符，expression 识别再也看不到它。
这钉死了「preprocessing order 也是契约」这一结论。

### 8. 最终修复

- 建立 official alias -> canonical expression normalization：
  `[Facepalm]` 与 `[捂脸]` 归一到同一 canonical expression；
- 110 个官方英文 aliases 全部纳入 mapping / tokenizer / adapter 三层契约；
- alias 匹配大小写不敏感；`[LetDown]` 与 `[Let Down]` 归一到同一表情；
- 不做泛化规则：不把任意 `[A-Za-z]+` 当表达式，
  `[TODO]` / `[AI]` / `[Python]` 保留为普通文本；
- bare `Laugh` / `Lol` 等无 bracket 的用户真实输入保留；
- 调整 preprocessing order：expression masking 必须先于
  hyphenated ASCII protection，保证 `[Pooh-pooh]` 这类 alias 能被识别。

### 9. 可推广的工程经验

- 「格式识别」的覆盖单位应是官方 source representation 全集，
  而不是最常见的书写形式；官方同时接受中文名与英文 code，
  识别器就必须同时覆盖两者。
- 识别失败时的**静默降级**是污染的真正入口：本应报「未知表达式」的文本
  被降级成普通文本，错误不会消失，只会流入下游统计。
- placeholder / 保护性正则的**执行顺序是契约的一部分**：
  两个各自正确的步骤按错误顺序执行，会产生错误结果。

### 10. 可以反向审计仓库的规则

- 搜索所有「识别 → 未命中 → 降级为普通文本」的链路，
  确认未命中不会静默进入统计；
- 搜索所有 placeholder / protection 正则链，
  确认 masking 步骤先于 protection 步骤；
- 对照 vendored 官方 code 表，确认 alias 全集（含带空格、带连字符、
  大小写变体）都有对应条目。

### 11. 对应 regression test

以下测试名称已在当前测试文件中逐一核实，与本次修复直接相关：

`tests/test_wechat_official_emojis.py`（mapping 契约）：

- `test_alias_map_only_normalizes_to_official_names`
- `test_alias_lookup_is_case_insensitive_and_rejects_unknown_codes`
- `test_previously_missing_english_alias_normalizes_to_canonical_name`
- `test_english_alias_keys_never_shadow_a_canonical_name`
- `test_spaced_let_down_and_joined_let_down_both_map_to_disappointment`
- `test_awesome_normalizes_to_the_numeric_canonical_666`
- `test_legacy_english_aliases_are_preserved`
- `test_every_current_client_code_is_recognized`
- `test_every_alias_resolves_to_declared_canonical`
- `test_alias_keys_do_not_collide_after_case_folding`

`tests/test_tokenizer.py`（tokenizer 契约）：

- `test_official_wechat_english_alias_is_not_a_language_token`
- `test_standalone_official_wechat_english_aliases_are_not_tokens`
- `test_bracketed_plain_english_words_are_not_expressions`
- `test_literal_english_words_without_brackets_are_preserved`
- `test_every_alias_bracket_is_masked_as_an_expression`
  （对 110 个 alias 全量参数化，`[Pooh-pooh]` 的 preprocessing order
  缺陷由它永久锁定）
- `test_newly_added_english_aliases_are_masked_as_expressions`
- `test_newly_added_english_alias_never_leaks_into_language_tokens`
- `test_undocumented_bracketed_english_stays_a_plain_word`
- `test_all_current_official_codes_are_masked_as_expressions`

`tests/test_wechat_db_source.py`（adapter 契约）：

- `test_text_row_keeps_unknown_bracket_text_as_plain_text`
- `test_english_alias_is_normalized_to_the_chinese_official_expression`
- `test_english_alias_and_chinese_name_share_one_expression`
- `test_new_english_alias_normalizes_to_canonical_expression`
- `test_spaced_and_joined_let_down_share_one_expression`
- `test_awesome_and_chinese_666_share_one_expression`
- `test_every_current_official_code_is_recognized_in_one_text_row`
- `test_every_alias_bracket_becomes_canonical_expression`
- `test_plain_bracketed_english_stays_plain_text`

真实验收：

朋友机器 / 真实 WeChat 数据使用最新版本复验通过：
原先的英文 expression names 不再进入语言画像，使用过程中未发现新 Bug。

### 历史状态

CLOSED / merged。

历史修复 commit：

```text
8cf051889664e37ae76dcd61a29de8404a00151b fix: support WeChat English expression aliases
1d2942d9dc0642da288479d30e0f8e38be6095b4 Merge branch 'fix/wechat-english-expression-aliases'
```