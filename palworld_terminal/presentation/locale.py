from __future__ import annotations

MESSAGES: dict[str, str] = {
    "no_server_configured": "尚未配置 Palworld 服务器，请在插件配置页添加。",
    "no_server_resolved": "本会话未指定服务器。管理员可用 /pal link add <名称> 授权，/pal link list 查看服务器。",
    "server_unknown": "服务器「{server}」不存在或未就绪。",
    "not_authorized": "本会话未被授权使用服务器「{server}」。请管理员先执行 /pal link add {server}。",
    "link_single_mode": "当前为单世界模式，无需选择服务器：所有操作对应唯一服务器。",
    "group_no_actions": "该命令组暂无可用命令（可能未开放或需要管理员权限）。",
    "private_restricted": "restricted 模式下私聊不可查询，请在群聊中使用。",
    "single_not_authorized": (
        "本群未被授权查询本服务器。请在群里发 /pal whereami 获取本群标识，"
        "交管理员在插件设置页「连接」章的授权群名单中添加。"
    ),
    "setup_required": (
        "🔧 帕鲁世界终端尚未完成首次设置。请打开插件设置页，"
        "选择运行模式（单服务器 / 多服务器）并确认后即可使用。"
    ),
    "active_server_stale": "当前绑定的服务器已不可用，请管理员重新执行 /pal link add <名称>。",
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
    "rank_duration_strict": "时长榜（今日/累计）在 strict 隐私模式下停用。",
    "player_not_found": "未找到玩家「{name}」。",
    "me_unbound": "你还没绑定玩家，请用 /pal player bind <玩家名> 绑定。",
    "me_hidden": "已将你从玩家排行/查询中隐藏。用 /pal me show 可恢复。",
    "me_shown": "已恢复你在玩家排行/查询中的可见性。",
    "bind_ok": "已绑定到玩家「{name}」。",
    "bind_not_found": "未找到玩家「{name}」，无法绑定。",
    "player_usage": "用法：/pal player info <玩家名>",
    "bind_usage": "用法：/pal player bind <玩家名>",
    "whoami": "你的账号标识：{id}（建议私聊 bot 执行本命令，再把标识报给管理员加入管理员名单）",
    "whoami_no_sender": "当前场景无法识别你的账号，请在群聊里再试。",
    "whereami": "本群标识（UMO）：{umo}（把它交给管理员，在设置页「连接」章的授权群名单中添加即可授权本群查询）",
    "whereami_no_umo": "当前场景无法识别群标识，请在目标群聊里再试。",
    "server_usage": "用法：/pal link add <名称> 或 /pal link remove <名称>",
    "unbind_self_ok": "已解除你与玩家「{name}」的绑定。",
    "unbind_self_none": "你还没有绑定玩家，无需解绑。",
    # ---- 服务器管控（写命令 / 二次确认）----
    "admin_ok": "已在服务器「{server}」执行【{action}】。",
    "admin_shutdown_initiated": "已向服务器「{server}」发起【{action}】（服务器已断开连接，视为已发起）。",
    "admin_failed": "服务器「{server}」执行【{action}】失败：{error}",
    "admin_resolve_failed": "无法执行：{reason}",
    "target_none": "未找到目标玩家「{target}」。",
    "target_unreachable": "无法获取服务器在线玩家列表（服务器可能不可达），请稍后重试。",
    "target_multi": "目标「{target}」有多个同名玩家（{candidates}）。请用 steam_ 前缀的 userid 精确指定。",
    "admin_announce_usage": "用法：/pal server announce <要广播的公告内容>",
    "admin_target_usage": "用法：/pal server {action} <玩家名 或 steam_ 前缀 userid>（可在后面加理由）",
    "admin_unban_usage": "用法：/pal server unban <steam_ 前缀的 userid>",
    "admin_shutdown_usage": "用法：/pal server shutdown <秒数> [公告]（秒数须为 1–86400 的整数，倒计时结束后关服）",
    "admin_shutdown_summary": "（{seconds} 秒后关服）",
    "admin_confirm_preview": (
        "⚠️ 即将执行【{action}】{target}，目标服务器「{server}」。"
        "请在 {timeout} 秒内发送 /pal confirm 确认，逾期自动作废。"
    ),
    "admin_confirm_done": "已确认并执行【{action}】{target}，服务器「{server}」。",
    "admin_confirm_stale": "该操作已失效（相关功能已关闭或目标服务器不可用），请重新发起。",
    "admin_no_pending": "当前没有待确认的操作。",
}


def L(key: str, **kwargs: object) -> str:
    template = MESSAGES[key]
    return template.format(**kwargs) if kwargs else template
