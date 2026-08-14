# Development State

## Stable

- QQ / WeChat 数据接入
- Identity Foundation
- stable sender aggregation
- conversation_type / is_self
- Conversation Sessions core
- Echo Conversation Sessions section
- Echo Expression chapter (Unicode emoji + QQ face + QQ market_face + WeChat sticker
  + WeChat official text emoji, frequency/composition and text association)
- Echo Expression visual assets (wechat-emojis icons via asset_key, no md5/path exposure)
- Echo Expression Echo-style top cards, Top10 recurring-expression filtering, image + readable name
- Echo Expression v1.2 habits: nearby words Top5 and same-message expression combinations Top3
- Echo Expression v1.2.1: combination common members, nearby Top3 cleanup, image-only display
- Echo Expression v1.2.2: Top5 display, valid-combination filtering, unified card layout
- Echo Expression v1.2.3: member scroll container, nearby wxid cleanup, Voices expression-marker removal
- Echo Voices/Expression final boundary: cleaner preserves expression markers, tokenizer excludes them from language tokens, Voices profiles include expression:<key> tokens
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
6. expression temporal follow-ups

## Known debt

- persisted QQ runtime config may point to an obsolete installation
- report viewing requires continued real GUI acceptance
