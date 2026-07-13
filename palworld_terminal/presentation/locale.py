from __future__ import annotations

MESSAGES: dict[str, str] = {
    "no_server_configured": "尚未配置 Palworld 服务器，请在插件配置页添加。",
    "no_server_resolved": "本会话未指定服务器。管理员可用 /pal server add <名称> 授权，或 /pal server 查看可用服务器。",
    "server_unknown": "服务器「{server}」不存在或未就绪。",
    "not_authorized": "本会话未被授权使用服务器「{server}」。请管理员先执行 /pal server add {server}。",
    "private_restricted": "restricted 模式下私聊不可查询，请在群聊中使用。",
    "active_server_stale": "当前绑定的服务器已不可用，请管理员重新执行 /pal server add <名称>。",
    "degraded": "当前无法获取 Palworld 世界数据。最后成功更新：{minutes} 分钟前。",
    "degraded_never": "当前无法获取 Palworld 世界数据（尚无成功记录）。",
    "auth_error": "世界数据接口配置异常，请联系管理员。",
    "guild_not_found": "未找到公会「{name}」。",
    "base_not_found": "未找到据点「{name}」。",
    "bases_disabled_strict": "据点模块因 strict 隐私模式停用。",
    "guilds_unavailable": "公会数据暂不可用。",
    "use_only_group": "该命令仅可在群聊中使用。",
    "admin_required": "该命令需要管理员权限。",
    "use_ok": "已授权本群使用服务器「{server}」并设为当前活动服务器。",
    "unbind_ok": "已撤销本群对服务器「{server}」的授权。",
    "empty_day": "平静的一天，没有值得记录的事件。",
    "no_events": "近期暂无世界事件。",
    "derived_note": "（插件推导）",
    "feature_disabled": "该功能未开放：当前配置或服务器不支持。",
    "rank_empty": "本服务器暂无玩家排行数据。",
    "rank_time_strict": "时长榜在 strict 隐私模式下停用。",
    "player_not_found": "未找到玩家「{name}」。",
    "me_unbound": "你还没绑定玩家，请用 /pal bind <玩家名> 绑定。",
    "me_hidden": "已将你从玩家排行/查询中隐藏。用 /pal me show 可恢复。",
    "me_shown": "已恢复你在玩家排行/查询中的可见性。",
    "bind_ok": "已绑定到玩家「{name}」。",
    "bind_not_found": "未找到玩家「{name}」，无法绑定。",
    "player_usage": "用法：/pal player <玩家名>",
    "bind_usage": "用法：/pal bind <玩家名>",
    "whoami": "你的账号标识：{id}（建议私聊 bot 执行本命令，再把标识报给管理员加入受托名单）",
    "whoami_no_sender": "当前场景无法识别你的账号，请在群聊里再试。",
    "server_usage": "用法：/pal server add <名称> 或 /pal server remove <名称>",
    "unbind_self_ok": "已解除你与玩家「{name}」的绑定。",
    "unbind_self_none": "你还没有绑定玩家，无需解绑。",
}


def L(key: str, **kwargs: object) -> str:
    template = MESSAGES[key]
    return template.format(**kwargs) if kwargs else template
