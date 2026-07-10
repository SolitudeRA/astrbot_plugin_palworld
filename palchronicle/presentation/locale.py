from __future__ import annotations

MESSAGES: dict[str, str] = {
    "no_server_configured": "尚未配置 Palworld 服务器，请在插件配置页添加。",
    "no_server_resolved": "本会话未指定服务器。管理员可用 /pal use <名称> 绑定，或 /pal servers 查看可用服务器。",
    "server_unknown": "服务器「{server}」不存在或未就绪。",
    "not_authorized": "本会话未被授权使用服务器「{server}」。请管理员先执行 /pal use {server}。",
    "private_restricted": "restricted 模式下私聊不可查询，请在群聊中使用。",
    "active_server_stale": "当前绑定的服务器已不可用，请管理员重新执行 /pal use <名称>。",
    "degraded": "当前无法获取 Palworld 世界数据。最后成功更新：{minutes} 分钟前。",
    "degraded_never": "当前无法获取 Palworld 世界数据（尚无成功记录）。",
    "auth_error": "世界数据接口配置异常，请联系管理员。",
    "guild_not_found": "未找到公会「{name}」。",
    "base_not_found": "未找到据点「{name}」。",
    "bases_disabled_strict": "据点模块因 strict 隐私模式停用。",
    "guilds_unavailable": "公会数据暂不可用。",
    "use_only_group": "该命令仅可在群聊中使用。",
    "use_ok": "已授权本群使用服务器「{server}」并设为当前活动服务器。",
    "unbind_ok": "已撤销本群对服务器「{server}」的授权。",
    "empty_day": "平静的一天，没有值得记录的事件。",
    "no_events": "近期暂无世界事件。",
    "derived_note": "（插件推导）",
}


def L(key: str, **kwargs: object) -> str:
    template = MESSAGES[key]
    return template.format(**kwargs) if kwargs else template
