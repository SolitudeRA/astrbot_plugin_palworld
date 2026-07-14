"""命令注册表：gating 与 help 的唯一真相源（spec §5）。"""
from __future__ import annotations

# (name, 组)——命令 → 所属组
COMMANDS: list[tuple[str, str]] = [
    ("status", "core"), ("online", "core"), ("world", "core"), ("rules", "core"),
    ("guilds", "guilds_bases"), ("guild", "guilds_bases"),
    ("bases", "guilds_bases"), ("base", "guilds_bases"),
    ("events", "events"), ("today", "report"),
    ("rank", "players"), ("player", "players"),
    ("me", "players"), ("bind", "players"), ("unbind_self", "players"),
    ("server", "core"), ("whoami", "core"), ("help", "core"),
    # 服务器管控写命令（feature 组把守；help 中仅管理员可见）
    ("announce", "server_admin_basic"), ("save", "server_admin_basic"),
    ("kick", "server_admin_basic"), ("unban", "server_admin_basic"),
    ("ban", "server_admin_danger"), ("shutdown", "server_admin_danger"),
    ("stop", "server_admin_danger"),
    ("confirm", "core"),   # 二次确认元命令（core，但 help 中仅管理员可见）
]
COMMAND_GROUP: dict[str, str] = {name: group for name, group in COMMANDS}

# help 展示文案（带参数提示），保持与旧 _HELP_GUEST 一致的措辞
HELP_LINE: dict[str, str] = {
    "status": "/pal status  世界状态", "online": "/pal online  当前在线",
    "world": "/pal world  世界概览", "rules": "/pal rules  世界规则",
    "guilds": "/pal guilds  公会列表", "guild": "/pal guild <名称>  公会详情",
    "bases": "/pal bases  据点列表", "base": "/pal base <名称|#序号>  据点详情",
    "events": "/pal events  世界事件", "today": "/pal today  今日日报",
    "rank": "/pal rank [time|level]  排行榜",
    "player": "/pal player <玩家名>  玩家查询",
    "me": "/pal me [hide|show]  我的信息",
    "bind": "/pal bind <玩家名>  绑定我的玩家",
    "unbind_self": "/pal unbind  解除我的玩家绑定",
    "server": "/pal server  服务器列表",
    "whoami": "/pal whoami  查看我的账号标识（建议私聊使用）",
    "help": "/pal help  帮助",
    "announce": "/pal announce <消息>  全服广播",
    "save": "/pal save  保存世界存档",
    "kick": "/pal kick <玩家名|userid> [理由]  踢出玩家",
    "unban": "/pal unban <userid>  解封玩家",
    "ban": "/pal ban <玩家名|userid> [理由]  封禁玩家",
    "shutdown": "/pal shutdown <秒> [公告]  倒计时关服",
    "stop": "/pal stop  立即停止服务",
    "confirm": "/pal confirm  确认执行上一条危险操作",
}

# astrbot 命令串真相源(用户 /pal <X> 里的 X)。与 COMMANDS 的键(方法名)区分:
# unbind(串) vs unbind_self(方法名)。由 command_names_test 锚定到 main.py 注册。
PAL_COMMAND_STRINGS: list[str] = [
    "status", "online", "world", "rules", "guilds", "guild", "bases", "base",
    "events", "today", "rank", "player", "me", "bind", "unbind",
    "server", "whoami", "help",
    # 服务器管控写命令 + confirm 元命令（管理员名单 + feature 组双闸把守）
    "announce", "save", "kick", "unban", "ban", "shutdown", "stop", "confirm",
]

# 不可锁集(astrbot 命令串):服务器/元命令与服务器管控写命令由 feature 组 + 管理员
# 名单双闸把守,绝不可再被 admin_only_commands 锁。须与 config._NON_LOCKABLE 同集
# (command_names_test::test_non_lockable_matches_registry_complement 锚定两处一致)。
_NON_LOCKABLE: frozenset[str] = frozenset({
    "server", "whoami", "help", "confirm",
    "announce", "save", "kick", "unban", "ban", "shutdown", "stop",
})

# 可被 admin_only_commands 锁定的命令串 = 全部 − 不可锁集
LOCKABLE_COMMANDS: frozenset[str] = frozenset(PAL_COMMAND_STRINGS) - _NON_LOCKABLE
