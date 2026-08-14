# Development State

## Stable

- QQ / WeChat 数据接入
- Identity Foundation
- stable sender aggregation
- conversation_type / is_self
- Conversation Sessions core
- Echo Conversation Sessions section
- GUI 会话数量与分析阶段显示逻辑

## Recently fixed

- WeChat DB self identity canonicalization
- QCE CLI force refresh regression
- Echo temporary report shutdown lifecycle

## Frozen

### QQ auth

当前真实连接已恢复。
除非出现明确 regression，不主动修改 auth / NapCat / QR lifecycle。

## Current acceptance

Conversation Sessions:
需要重新用真实微信私聊 + 群聊验证 self initiator 百分比。

## Next

1. real-data Conversation Sessions acceptance
2. project docs checkpoint
3. distinctive words
4. catchphrases
5. poke / pat interactions
6. emoji behavior

## Known debt

- persisted QQ runtime config may point to an obsolete installation
- report viewing requires continued real GUI acceptance