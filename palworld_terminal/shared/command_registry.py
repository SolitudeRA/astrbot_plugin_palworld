"""命令注册表：gating 与 help 的唯一真相源（spec §5）。"""
from __future__ import annotations

# ============================================================================
# 分级命令真相源（v0.9.5 Phase 1，spec §3 命令树 / §8 锚定）。
# 门控（commands._gated 经 METHOD_PATH）与 help（format_help 经 HELP_TEXT）均按
# 完整路径消费下方真相源。
# 两种粒度分家（spec §8）：
#   - 注册身份 = 12 首词（PAL_REGISTERED），AstrBot 只认首词，供 @pal.command 锚定。
#   - 门控/help/锁身份 = 完整路径（PAL_COMMAND_STRINGS：`world status`/`server kick`/
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
        "overview": ("world", "guilds_bases", "read"),   # overview = 旧 /pal world 方法；2026-07-16 归队 game-data 家族
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
    # dex 服务器图鉴（spec §8）：扁平命令（group=null，参数内解析，与 rank 对齐——非命令组）；
    # feat_group guilds_bases（同一 game-data 命脉，随 guild 命令共启轮询）。
    "dex": ("dex", "guilds_bases", "read"),
    "help": ("help", "core", "read"),
    "whoami": ("whoami", "core", "read"),
    "whereami": ("whereami", "core", "read"),
    "confirm": ("confirm", "core", "admin"),  # 仅管理员可见/可用
}

# 读方法名 → 完整路径（供 commands._gated）。仅收 gate==read 方法（写走 admin_write）。
# 必须覆盖全部 @_gated 方法，否则运行时 METHOD_PATH[fn.__name__] KeyError
# （command_permissions_meta_test.test_all_gated_methods_in_method_path 防回归）。
METHOD_PATH: dict[str, str] = {
    method: f"{grp} {sub}"
    for grp, actions in DISPATCH.items()
    for sub, (method, _feat, gate) in actions.items()
    if gate == "read"
}
METHOD_PATH.update({
    name: name for name, (_m, _f, gate) in FLAT_ACTIONS.items() if gate == "read"
})

# 注册身份：13 首词（5 组 + 8 扁平）——供 @pal.command 注册锚定（T8 翻新时消费）。
PAL_REGISTERED: list[str] = [*DISPATCH.keys(), *FLAT_ACTIONS.keys()]

# 门控/help/锁身份：完整路径集（`world status` … + 扁平命令名）。
# astrbot 命令串真相源现为完整路径；由 command_names_test 锚定到 main.py 的 12 注册。
PAL_COMMAND_STRINGS: frozenset[str] = frozenset(
    [f"{group} {sub}" for group, actions in DISPATCH.items() for sub in actions]
    + list(FLAT_ACTIONS)
)

# 不可锁集（完整路径）：server 各动作 + link 各动作 + 元命令（help/whoami/whereami/confirm）。
# 这些各有内置权限语义，command_permissions 的 admin_only 轴对其无效。
# 须与 config._NON_LOCKABLE 跨源全等（command_names_test 锚定两处一致）。
_NON_LOCKABLE: frozenset[str] = frozenset(
    [f"server {sub}" for sub in DISPATCH["server"]]
    + [f"link {sub}" for sub in DISPATCH["link"]]
    + ["help", "whoami", "whereami", "confirm"]
)

# 可设置 admin_only 的完整路径 = 全部 − 不可锁集。
LOCKABLE_COMMANDS: frozenset[str] = frozenset(PAL_COMMAND_STRINGS) - _NON_LOCKABLE

# 分级 help 文案：完整路径 → 描述（含参数提示）。format_help / 裸组迷你帮助的展示真相源。
# 键须与 PAL_COMMAND_STRINGS 双向全等（formatters_hierarchy_test 防漂移锚定）。
HELP_TEXT: dict[str, str] = {
    "world status": "世界状态",
    "world overview": "世界概览",
    "world rules": "世界规则",
    "world events": "世界事件",
    "world today": "今日日报",
    "guild list": "公会列表",
    "guild info": "公会详情（<名称>）",
    "guild bases": "据点列表",
    "guild base": "据点详情（<名称|#序号>）",
    "player info": "玩家查询（<玩家名>）",
    "player bind": "绑定我的玩家（<玩家名>）",
    "player unbind": "解除我的玩家绑定",
    "server announce": "全服广播（<消息>）",
    "server save": "保存世界存档",
    "server kick": "踢出玩家（<玩家名|userid> [理由]）",
    "server unban": "解封玩家（<userid>）",
    "server ban": "封禁玩家（<玩家名|userid> [理由]）",
    "server shutdown": "倒计时关服（<秒> [公告]）",
    "server stop": "立即停止服务",
    "link list": "服务器列表",
    "link add": "授权本群并设为活动服务器（<名称>）",
    "link remove": "撤销本群授权（<名称>）",
    "rank": "排行榜（[today|total|level|climb]）",
    "online": "当前在线",
    "me": "我的名片（[hide|show|card|卡|图]）",
    "dex": "服务器图鉴（已观测物种进度）",
    "help": "帮助",
    "whoami": "查看我的账号标识（建议私聊使用）",
    "whereami": "查看当前群标识（UMO）",
    "confirm": "确认执行上一条危险操作",
}
