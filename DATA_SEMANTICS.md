# Data Semantics

## ChatMessage identity

### sender_id

稳定发送者身份，不等于 display name。

QQ:
- sender uid/uin
- 显示名变化不得拆分同一成员

WeChat DB:
- 来自 Name2Id.user_name
- self identity 必须 canonicalize 到同一 namespace

### conversation_type

private / group / unknown

### is_self

True:
可靠确认该消息由本人发送

False:
已有可靠 self identity，并确认 sender != self

None:
来源无法可靠判断
禁止把 None 当作 peer

## WeChat self identity

账户目录可能为：
<基础 username>_<hex suffix>

只有在去掉 suffix 后的基础 username
确实存在于 contact.username 命名空间时才 canonicalize。

不得仅凭字符串形式粗暴截断。

## Conversation Sessions

默认 threshold = 1800 seconds

gap <= 1800:
same session

gap > 1800:
new session

private initiator:
is_self=True  -> self
is_self=False -> peer
is_self=None  -> unknown

group initiator:
使用 stable sender identity

Echo 不重新计算 session statistics。