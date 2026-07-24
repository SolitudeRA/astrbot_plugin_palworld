from __future__ import annotations

MESSAGES: dict[str, str] = {
    "no_server_configured": "尚未配置 Palworld 服务器，请在插件配置页添加。",
    "no_server_resolved": "本会话未指定服务器。管理员可用 /pal link add <名称> 授权，/pal link list 查看服务器。",
    "server_unknown": "服务器「{server}」不存在或未就绪。",
    "not_authorized": "本会话未被授权使用服务器「{server}」。请管理员先执行 /pal link add {server}。",
    "link_single_mode": "当前为单世界模式，无需选择服务器：所有操作对应唯一服务器。",
    "group_no_actions": "该命令组暂无可用命令（可能未开放或需要管理员权限）。",
    # 场景类拦截（spec §3）：从 routing 六分支素文豁免中摘出——戴 ⚠️（沿 PR#22 句仅加前缀）。
    "private_restricted": "⚠️ restricted 模式下私聊不可查询，请在群聊中使用。",
    "single_not_authorized": (
        "本群未被授权查询本服务器。请在群里发 /pal whereami 获取本群标识，"
        "交管理员在插件设置页「连接」章的授权群名单中添加。"
    ),
    "setup_required": (
        "🔧 帕鲁世界终端尚未完成首次设置。请打开插件设置页，"
        "选择运行模式（单服务器 / 多服务器）并确认后即可使用。"
    ),
    "active_server_stale": "当前绑定的服务器已不可用，请管理员重新执行 /pal link add <名称>。",
    "degraded": "🔴 当前无法获取世界数据 · 最后成功于 {minutes} 分钟前",
    "degraded_never": "🔴 尚未成功连接过服务器，请检查「连接」配置",
    # guild 组四条（spec §4.6-4.9）：找不到带引导脚注；无参补 usage（§6#11）；
    # 空态素文；bases/base 整命令拒执行统一 ⚠️（§3 配置停用类；接线死键）。
    "guild_not_found": "❌ 未找到公会「{name}」\n└ /pal guild list 查看已观察公会",
    "guild_usage": "用法：/pal guild info <公会名>",
    "guilds_empty": "暂无公会观察数据",
    "base_not_found": "❌ 未找到据点「{name}」\n└ /pal guild bases 查看列表（可用 #序号）",
    "base_usage": "用法：/pal guild base <据点名 或 #序号>",
    "bases_empty": "暂无可展示的据点",
    "base_no_observation": "⚠️ 该据点尚无观测数据",
    "bases_disabled_strict": "⚠️ 据点模块在 strict 隐私模式下停用",
    # 场景/环境不符类拦截统一 ⚠️（spec §3；link add/remove 共用同键同待遇）。
    "use_only_group": "⚠️ 该命令仅可在群聊中使用",
    # 配置停用类拦截（spec §3）：整命令被拒执行的停用主句统一戴 ⚠️。
    "admin_required": "⚠️ 该命令需要管理员权限",
    # ---- link 组回执（spec §4.20-4.22）；渲染上提自 RoutingService 结构化返回 ----
    # 空态拆键（routing 的 no_server_configured 保持原素文，§3/§7）。
    "link_list_empty": "尚未配置 Palworld 服务器\n└ 在插件设置页「连接」章添加",
    # add 成功统一用 srv.name；换活动服务器时补脚注。
    "link_add_ok": "✅ 已授权本群 · {server}（设为当前活动）",
    "link_add_ok_replaced": (
        "✅ 已授权本群 · {server}（设为当前活动）\n└ 原活动服务器「{old}」已替换"
    ),
    # 不存在/未就绪拆键（routing 的 server_unknown 保持原素文，§3/§7）。
    "link_add_unknown": "❌ 服务器「{server}」不存在或未就绪\n└ /pal link list 查看可用名称",
    "link_add_usage": "用法：/pal link add <服务器名>",
    # remove 成功；撤活动服务器时补脚注；无授权记录素文中性无操作。
    "link_remove_ok": "✅ 已撤销本群授权 · {server}",
    "link_remove_ok_active": (
        "✅ 已撤销本群授权 · {server}\n└ 该服务器原为本群活动服务器，后续需重新授权指定"
    ),
    "link_remove_none": "本群没有「{server}」的授权记录",
    "link_remove_usage": "用法：/pal link remove <服务器名>",
    "empty_day": "平静的一天，没有新事件",
    # events 空态两句变体（spec §4.4；标题锚点由 formatter 供，此处只存空句）。
    "events_empty": "最近还没有新事件",
    "events_empty_today": "今天还没有新事件",
    # feature_disabled 主句戴 ⚠️（配置停用类，spec §3）；引导脚注为独立键，由 commands 渲染层
    # 条件拼接——upstream_unavailable(path) 时省略（设置页开不了，假承诺；当前空集，休眠）。
    "feature_disabled": "⚠️ 该功能未开启",
    "feature_disabled_hint": "└ 管理员可在插件设置页「权限」章开启",
    # rank 空榜（spec §4.23）：标题锚点由 formatter 供，此处只存素文空句。
    "rank_empty": "暂无排行数据",
    # rank strict 停用（spec §3/§4.23）：配置停用类统一 ⚠️ + 等级榜不受影响引导脚注。
    "rank_duration_strict": "⚠️ 时长榜在 strict 隐私模式下停用\n└ 等级榜不受影响：/pal rank level",
    # online 空态（spec §4.24）：标题锚点由 formatter 供，此处只存素文空句（收编硬编码）。
    "online_empty": "当前无玩家在线",
    # player info / bind / me not-found 脚注共用（spec §4.10/§4.11）。
    "player_not_found": (
        "❌ 未找到玩家「{name}」\n└ 名字须与游戏内完全一致，可用 /pal online 查在线玩家"
    ),
    # me 未绑定（spec §4.25）：多模式句内带服 / 单模式去锚；脚注两态皆带。
    "me_unbound": "你还没有绑定玩家\n└ 用 /pal player bind <玩家名> 绑定",
    "me_unbound_scoped": "你在「{server}」还没有绑定玩家\n└ 用 /pal player bind <玩家名> 绑定",
    # me hide/show（spec §4.25）：多模式带服务器锚 / 单模式去服名。
    "me_hidden": "✅ 已将你从排行与查询中隐藏\n└ /pal me show 恢复",
    "me_hidden_scoped": "✅ 已将你从「{server}」的排行与查询中隐藏\n└ /pal me show 恢复",
    "me_shown": "✅ 已恢复你的可见性",
    "me_shown_scoped": "✅ 已恢复你在「{server}」的可见性",
    # bind（spec §4.11）：{anchor} 由 commands 层按模式给（多模式 ` · {srv}` / 单模式 ""）。
    "bind_ok": "✅ 已绑定玩家「{name}」{anchor}\n└ 现在可以用 /pal me 查看自己的状态了",
    "bind_rebind": "✅ 已改绑到玩家「{name}」（原绑定「{old}」）{anchor}",
    "bind_not_found": (
        "❌ 未找到玩家「{name}」，无法绑定\n└ 名字须与游戏内完全一致，可用 /pal online 查在线玩家"
    ),
    "player_usage": "用法：/pal player info <玩家名>",
    "bind_usage": "用法：/pal player bind <玩家名>\n└ 绑定后可用 /pal me 查看自己的状态",
    # whoami（spec §4.27）：账号标识 + 引导脚注；已是管理员次行加注；取不到场景类 ⚠️。
    "whoami": (
        "🪪 我的账号标识\n{id}\n└ 建议私聊使用；把标识交给管理员加入权限名单"
    ),
    "whoami_admin": (
        "🪪 我的账号标识\n{id}\n你已在管理员名单中\n"
        "└ 建议私聊使用；把标识交给管理员加入权限名单"
    ),
    "whoami_no_sender": "⚠️ 当前场景无法识别你的账号，请换个聊天场景再试",
    # whereami（spec §4.28）：按 access_mode 分流；标题+群标识两行，授权段/脚注由 commands 拼。
    "whereami_head": "📍 本群标识\n{umo}",
    "whereami_open": "当前为开放模式，无需授权即可查询",
    "whereami_authed": "本群已授权：{servers}",
    "whereami_unauthed": "本群尚未授权",
    "whereami_footer": "└ 未授权时把标识交给管理员即可开通查询",
    "whereami_no_umo": "⚠️ 当前场景无法识别群标识，请在群聊中使用",
    # unbind（spec §4.12）：{anchor} 同 bind；悬空绑定绝不渲染 player_key 哈希（§6#10）。
    "unbind_self_ok": "✅ 已解除绑定 · {name}{anchor}\n└ 重新绑定用 /pal player bind <玩家名>",
    "unbind_self_dangling": "✅ 已解除绑定{anchor}",
    "unbind_self_none": "你还没有绑定玩家，无需解绑",
    "unbind_self_none_scoped": "你在「{server}」还没有绑定玩家，无需解绑",
    # ---- 服务器管控（写命令 / 二次确认；spec §4.13-4.19 / §4.29）----
    # 成功回执统一式 `✅ 动作短语 · {server}`（用上目标尾4）：per-action 短语键族，
    # 可选脚注（announce 回显 / ban 理由 / shutdown 倒计时）由 commands 渲染层拼接。
    "admin_ok_announce": "✅ 公告已广播 · {server}",
    "admin_ok_save": "✅ 已执行存档 · {server}",
    "admin_ok_kick": "✅ 已踢出 {target} · {server}",
    "admin_ok_unban": "✅ 已解封 {target} · {server}",
    "admin_ok_ban": "✅ 已封禁 {target} · {server}",
    "admin_ok_shutdown": "✅ 已发出关服指令 · {server}",
    "admin_ok_stop": "✅ 已停止服务进程 · {server}",
    # 脚注片段（回执补充信息；全角引号回显随 §2.3）。
    "admin_fn_announce": "└ “{content}”",
    "admin_fn_ban_reason": "└ 理由：{reason}",
    "admin_fn_shutdown": "└ {seconds} 秒后关服",
    "admin_fn_shutdown_msg": "└ {seconds} 秒后关服 · 公告：“{message}”",
    # 断连已发起（直接路径，仅 shutdown/stop）：通用「指令已发出」+ 断连脚注。
    "admin_initiated": "✅ 指令已发出 · {server}\n└ 服务器连接已断开，按已生效处理",
    # 失败：❌ 回执头 + error 脚注（{action} 由渲染层转中文动作名）。
    "admin_failed": "❌ {action}失败 · {server}\n└ {error}",
    # resolve 失败：❌ 为回执头，{reason} 内嵌 routing 六分支原素文（§3，不加图标到六分支本身）。
    "admin_resolve_failed": "❌ 无法执行：{reason}",
    # 目标族三态（§4.13-4.19）。
    "target_none": "❌ 未找到在线玩家「{target}」\n└ 离线玩家可用 steam_ userid 直接指定",
    "target_unreachable": "❌ 无法获取在线玩家列表（服务器可能不可达），请稍后重试",
    "target_multi": "⚠️ 「{target}」有多个同名在线玩家\n{candidates}\n└ 用 steam_ userid 精确指定",
    # usage 全英文子命令（修「/pal server 踢出」不通顺）。
    "admin_announce_usage": "用法：/pal server announce <要广播的公告内容>",
    "admin_target_usage": "用法：/pal server {sub} <玩家名|steam_userid> [理由]",
    "admin_unban_usage": "用法：/pal server unban <steam_userid>",
    "admin_unban_prefix": "❌ userid 须以 steam_ 开头",
    "admin_shutdown_usage": "用法：/pal server shutdown <秒数> [公告]（秒数须为 1–86400 的整数，倒计时结束后关服）",
    # 二次确认预览（⚠️ 待确认 · 动作短语 · 服务器 + 引导脚注）。
    "admin_confirm_preview": (
        "⚠️ 待确认 · {phrase} · {server}\n"
        "└ {timeout} 秒内发送 /pal confirm 执行，逾期自动作废"
    ),
    # confirm 执行成功（正常完成）；断连已发起走 admin_confirm_initiated（§6#6 语义分立）。
    "admin_confirm_done": "✅ 已确认执行 · {phrase} · {server}",
    "admin_confirm_initiated": (
        "✅ 已确认 · {verb}指令已发出 · {server}\n└ 服务器连接已断开，按已生效处理"
    ),
    "admin_confirm_stale": "⚠️ 该操作已失效（功能已关闭或服务器不可用），请重新发起",
    "admin_no_pending": "当前没有待确认的操作（可能已超时作废）",
    # ---- 横切回执（命令输出重设计第一波；收编硬编码，spec §3/§7）----
    "busy": "⚠️ 插件正在重载配置，请稍后重试",
    "arg_error": "⚠️ 一条命令只能指定一个 @服务器",
    # ---- 取数失败态（具体目标已定位但数据缺失；spec §4.2/§4.3/§9）----
    "world_snapshot_missing": "⚠️ 尚未获取到世界快照，稍后再试",
    "rules_unavailable": "⚠️ 尚未从服务器获取到规则数据，稍后再试",
}


def L(key: str, **kwargs: object) -> str:
    template = MESSAGES[key]
    return template.format(**kwargs) if kwargs else template
