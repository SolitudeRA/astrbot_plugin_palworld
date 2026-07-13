"""命令注册表：gating 与 help 的唯一真相源（spec §5）。"""
from __future__ import annotations

# (name, 组)——命令 → 所属组
COMMANDS: list[tuple[str, str]] = [
    ("status", "core"), ("online", "core"), ("world", "core"), ("rules", "core"),
    ("guilds", "guilds_bases"), ("guild", "guilds_bases"),
    ("bases", "guilds_bases"), ("base", "guilds_bases"),
    ("events", "events"), ("today", "report"),
    ("rank", "players"), ("player", "players"),
    ("me", "players"), ("bind", "players"),
    ("server", "core"), ("help", "core"),
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
    "server": "/pal server  服务器列表", "help": "/pal help  帮助",
}
