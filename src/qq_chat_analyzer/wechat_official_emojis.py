"""Official WeChat built-in emoji names and their English bracket aliases.

The canonical names below are vendored from the bundled wechat-emojis assets.
WeChat also accepts English bracket codes for the same emoji (``[Facepalm]``
is the same expression as ``[捂脸]``), so aliases are kept as one
alias -> canonical map shared by the tokenizer and the WeChat adapter.
"""

from __future__ import annotations


OFFICIAL_WECHAT_EMOJI_NAMES = frozenset(
    {
        "666",
        "爱心",
        "OK",
        "Emm",
        "傲慢",
        "白眼",
        "爆竹",
        "鄙视",
        "闭嘴",
        "擦汗",
        "呲牙",
        "菜刀",
        "蛋糕",
        "打脸",
        "大哭",
        "得意",
        "凋谢",
        "调皮",
        "发抖",
        "发呆",
        "发怒",
        "翻白眼",
        "福",
        "尴尬",
        "鼓掌",
        "害羞",
        "憨笑",
        "汗",
        "好的",
        "合十",
        "嘿哈",
        "红包",
        "坏笑",
        "机智",
        "加油",
        "奸笑",
        "惊恐",
        "惊讶",
        "囧",
        "咖啡",
        "可怜",
        "恐惧",
        "抠鼻",
        "骷髅",
        "苦涩",
        "快哭了",
        "困",
        "脸红",
        "礼物",
        "裂开",
        "流泪",
        "玫瑰",
        "啤酒",
        "难过",
        "撇嘴",
        "破涕为笑",
        "敲打",
        "亲亲",
        "庆祝",
        "拳头",
        "让我看看",
        "弱",
        "色",
        "社会社会",
        "生病",
        "失望",
        "胜利",
        "衰",
        "睡",
        "太阳",
        "叹气",
        "天啊",
        "跳跳",
        "偷笑",
        "吐",
        "哇",
        "旺柴",
        "微笑",
        "委屈",
        "握手",
        "无语",
        "捂脸",
        "笑脸",
        "心碎",
        "嘘",
        "烟花",
        "耶",
        "疑问",
        "阴险",
        "悠闲",
        "拥抱",
        "右哼哼",
        "愉快",
        "月亮",
        "晕",
        "再见",
        "炸弹",
        "咒骂",
        "猪头",
        "转圈",
        "皱眉",
        "抓狂",
        "嘴唇",
        "發",
        "抱拳",
        "便便",
        "吃瓜",
        "勾引",
        "强",
    }
)


WECHAT_EMOJI_ALIASES = {
    # 只收录公开微信 code 对照表明确给出 ``英文 code ↔ 中文表情`` 的条目。
    # 键是英文中括号 code（不含方括号），值是 OFFICIAL_WECHAT_EMOJI_NAMES
    # 中已存在的名称；仅凭英文词义、位置或猜测得到的候选一律不收录。
    #
    # 来源 A：qiuyinghua/wechat-emoticons README 的「英文名 ↔ 简体中文名」对照表
    # （微信/QQ 共用的经典表情 code），此处只保留中文名与 canonical 名称完全一致
    # 的条目。``Bah！R`` 的全角感叹号取自来源 B 的新版 code 表，来源 A 写作
    # ``Bah! R``。
    "Smile": "微笑",
    "Grimace": "撇嘴",
    "Drool": "色",
    "Scowl": "发呆",
    "CoolGuy": "得意",
    "Sob": "流泪",
    "Shy": "害羞",
    "Silent": "闭嘴",
    "Sleep": "睡",
    "Cry": "大哭",
    "Awkward": "尴尬",
    "Angry": "发怒",
    "Tongue": "调皮",
    "Grin": "呲牙",
    "Surprise": "惊讶",
    "Frown": "难过",
    "Scream": "抓狂",
    "Puke": "吐",
    "Chuckle": "偷笑",
    "Joyful": "愉快",
    "Slight": "白眼",
    "Smug": "傲慢",
    "Drowsy": "困",
    "Panic": "惊恐",
    "Laugh": "憨笑",
    "Commando": "悠闲",
    "Scold": "咒骂",
    "Shocked": "疑问",
    "Shhh": "嘘",
    "Dizzy": "晕",
    "Toasted": "衰",
    "Skull": "骷髅",
    "Hammer": "敲打",
    "Wave": "再见",
    "Speechless": "擦汗",
    "NosePick": "抠鼻",
    "Clap": "鼓掌",
    "Trick": "坏笑",
    "Bah！R": "右哼哼",
    "Pooh-pooh": "鄙视",
    "Shrunken": "委屈",
    "TearingUp": "快哭了",
    "Sly": "阴险",
    "Kiss": "亲亲",
    "Whimper": "可怜",
    "Cleaver": "菜刀",
    "Beer": "啤酒",
    "Coffee": "咖啡",
    "Pig": "猪头",
    "Rose": "玫瑰",
    "Wilt": "凋谢",
    "Lips": "嘴唇",
    "Heart": "爱心",
    "BrokenHeart": "心碎",
    "Cake": "蛋糕",
    "Bomb": "炸弹",
    "Poop": "便便",
    "Moon": "月亮",
    "Sun": "太阳",
    "Gift": "礼物",
    "Hug": "拥抱",
    "ThumbsUp": "强",
    "ThumbsDown": "弱",
    "Shake": "握手",
    "Peace": "胜利",
    "Fight": "抱拳",
    "Beckon": "勾引",
    "Fist": "拳头",
    "Waddle": "跳跳",
    "Tremble": "发抖",
    "Twirl": "转圈",
    # 来源 B：微信新版表情「中括号输入对照」表（含 [Facepalm] 捂脸 等），
    # 逐条给出英文中括号 code 与中文名。
    "Hey": "嘿哈",
    "Facepalm": "捂脸",
    "Smirk": "奸笑",
    "Smart": "机智",
    "Concerned": "皱眉",
    "Yeah!": "耶",
    "Onlooker": "吃瓜",
    "GoForIt": "加油",
    "Sweats": "汗",
    "OMG": "天啊",
    "Respect": "社会社会",
    "Doge": "旺柴",
    "NoProb": "好的",
    "Wow": "哇",
    # 来源 C：macOS 微信客户端 newemoji-config.xml 的 key / cn-value / en-value
    # 显式映射（并与 Android WeChat 8.0.48 实测 109 code 列表交叉核对），用于补齐
    # 来源 A/B 缺失的当前官方英文 code。``Awesome`` 的 canonical 是数字名 ``666``；
    # ``LetDown``（配置 key）与 ``Let Down``（配置 en-value）是同一个表情，两种
    # 写法都收录并映射到 ``失望``。逐条收录，不使用泛化英文方括号规则。
    "Bye": "再见",
    "Salute": "抱拳",
    "Happy": "笑脸",
    "Sick": "生病",
    "Flushed": "脸红",
    "Lol": "破涕为笑",
    "Terror": "恐惧",
    "LetDown": "失望",
    "Let Down": "失望",
    "Duh": "无语",
    "MyBad": "打脸",
    "Boring": "翻白眼",
    "Awesome": "666",
    "LetMeSee": "让我看看",
    "Sigh": "叹气",
    "Hurt": "苦涩",
    "Broken": "裂开",
    "Party": "庆祝",
    "Packet": "红包",
    "Rich": "發",
    "Blessing": "福",
    "Fireworks": "烟花",
    "Firecracker": "爆竹",
    "Worship": "合十",
    "Blush": "囧",
}

_EXPRESSION_BRACKET_NAMES = (
    *OFFICIAL_WECHAT_EMOJI_NAMES,
    *WECHAT_EMOJI_ALIASES,
)
_ALIAS_LOOKUP = {
    alias.lower(): canonical
    for alias, canonical in WECHAT_EMOJI_ALIASES.items()
}


def wechat_expression_names() -> tuple[str, ...]:
    """Return every accepted bracket code: canonical names plus English aliases."""
    return _EXPRESSION_BRACKET_NAMES


def canonical_wechat_emoji_name(name: str) -> str | None:
    """Return the canonical official name for one bracket code, else ``None``.

    Canonical names keep their existing exact-match contract; English aliases
    are matched case-insensitively so ``[facepalm]`` and ``[Facepalm]``
    normalize to the same expression.
    """
    if not isinstance(name, str):
        return None
    if name in OFFICIAL_WECHAT_EMOJI_NAMES:
        return name
    return _ALIAS_LOOKUP.get(name.lower())
