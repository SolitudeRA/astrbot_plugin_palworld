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
    "rank": "/pal rank [today|total|level]  排行榜",
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


# ============================================================================
# 分级命令真相源（v0.9.5 Phase 1，spec §3 命令树 / §8 锚定）——additive。
# 上方旧扁平 26 常量（COMMANDS/HELP_LINE/PAL_COMMAND_STRINGS/LOCKABLE_COMMANDS/
# _NON_LOCKABLE）保持不动、command_names_test 仍锚它们；T8 收口时统一改名删旧。
# 两种粒度分家（spec §8）：
#   - 注册身份 = 11 首词（PAL_REGISTERED），AstrBot 只认首词，供 @pal.command 锚定。
#   - 门控/help/锁身份 = 完整路径（PAL_COMMAND_PATHS：`world status`/`server kick`/
#     `rank`），功能门/管理员门/可锁性都按完整路径判定。
# ============================================================================

# 子动作分发规格：(实现方法名, 功能门组, gate)。
#   gate="read"        —— 功能门 + 可选 admin_only 锁（查询类）。
#   gate="admin_write" —— server 管控写：admin 硬门 + feature 门 + 审计（走 admin_write）。
#   gate="admin"       —— 需管理员但非 admin_write（如 link add/remove、confirm，
#                          照现 server add/remove 的 is_admin 判定）。
# 方法名此刻不必已存在（T7 建组分发/实现方法）；getattr introspection 锚定留 T7。
ActionSpec = tuple[str, str, str]

# {组: {子动作: ActionSpec}}——路由 + help 生成 + 锚定的单一真相源。
DISPATCH: dict[str, dict[str, ActionSpec]] = {
    "world": {
        "status": ("status", "core", "read"),
        "overview": ("world", "core", "read"),   # overview = 旧 /pal world 方法
        "rules": ("rules", "core", "read"),
        "events": ("events", "events", "read"),
        "today": ("today", "report", "read"),
    },
    "guild": {
        "list": ("guilds", "guilds_bases", "read"),
        "info": ("guild", "guilds_bases", "read"),
        "bases": ("bases", "guilds_bases", "read"),
        "base": ("base", "guilds_bases", "read"),
    },
    "player": {
        "info": ("player", "players", "read"),
        "bind": ("bind", "players", "read"),
        "unbind": ("unbind_self", "players", "read"),  # 串 unbind → 方法 unbind_self
    },
    "server": {  # 写命令：门序 admin 硬门先于 feature；basic/danger 分组不可混
        "announce": ("announce", "server_admin_basic", "admin_write"),
        "save": ("save", "server_admin_basic", "admin_write"),
        "kick": ("kick", "server_admin_basic", "admin_write"),
        "unban": ("unban", "server_admin_basic", "admin_write"),
        "ban": ("ban", "server_admin_danger", "admin_write"),
        "shutdown": ("shutdown", "server_admin_danger", "admin_write"),
        "stop": ("stop", "server_admin_danger", "admin_write"),
    },
    "link": {  # 服务器选择/绑定（多模式）；单模式运行时拒 + help 省略（T9）
        "list": ("link_list", "core", "read"),
        "add": ("link_add", "core", "admin"),
        "remove": ("link_remove", "core", "admin"),
    },
}

# 扁平（顶层）命令 → ActionSpec（单一命令名，无组前缀）。
FLAT_ACTIONS: dict[str, ActionSpec] = {
    "rank": ("rank", "players", "read"),
    "online": ("online", "core", "read"),
    "me": ("me", "players", "read"),
    "help": ("help", "core", "read"),
    "whoami": ("whoami", "core", "read"),
    "confirm": ("confirm", "core", "admin"),  # 仅管理员可见/可用
}

# 注册身份：11 首词（5 组 + 6 扁平）——供 @pal.command 注册锚定（T8 翻新时消费）。
PAL_REGISTERED: list[str] = [*DISPATCH.keys(), *FLAT_ACTIONS.keys()]

# 门控/help/锁身份：完整路径集（`world status` … + 扁平命令名）。
PAL_COMMAND_PATHS: frozenset[str] = frozenset(
    [f"{group} {sub}" for group, actions in DISPATCH.items() for sub in actions]
    + list(FLAT_ACTIONS)
)

# 不可锁集（完整路径）：server 各动作 + link 各动作 + 元命令（help/whoami/confirm）。
# 这些由 feature 组 + 管理员名单双闸把守，绝不可再被 admin_only_commands 锁。
# T8 收口时会与 config._NON_LOCKABLE 跨源全等锚定（本任务不改 config）。
_NON_LOCKABLE_PATHS: frozenset[str] = frozenset(
    [f"server {sub}" for sub in DISPATCH["server"]]
    + [f"link {sub}" for sub in DISPATCH["link"]]
    + ["help", "whoami", "confirm"]
)

# 可被 admin_only_commands 锁定的完整路径 = 全部 − 不可锁集。
LOCKABLE_PATHS: frozenset[str] = frozenset(PAL_COMMAND_PATHS) - _NON_LOCKABLE_PATHS
