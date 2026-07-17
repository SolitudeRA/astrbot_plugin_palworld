from palworld_terminal.presentation.locale import MESSAGES, L


def test_new_keys_present():
    # spec §4.21/4.22：usage 拆分 add/remove（旧 server_usage 退役）。
    assert "link_add_usage" in MESSAGES
    assert "link_remove_usage" in MESSAGES
    assert "server_usage" not in MESSAGES
    # spec §4.20/4.21：link list 空态 + link add 不存在拆键（routing 素文键保留）。
    assert "link_list_empty" in MESSAGES
    assert "link_add_unknown" in MESSAGES
    # spec §4.12：解绑成功新式样（{name}+{anchor} 尾锚），悬空绝不出哈希。
    assert L("unbind_self_ok", name="Alice", anchor=" · 主服") == (
        "✅ 已解除绑定 · Alice · 主服\n└ 重新绑定用 /pal player bind <玩家名>"
    )
    assert MESSAGES["unbind_self_none"]


def test_output_redesign_first_wave_dead_keys_removed():
    # spec §7：auth_error / derived_note 均零调用点，第一波删除。
    assert "auth_error" not in MESSAGES
    assert "derived_note" not in MESSAGES


def test_output_redesign_first_wave_new_keys():
    # spec §3 / §7：busy 与 arg_error 收编硬编码，戴 ⚠️ 前缀。
    assert L("busy") == "⚠️ 插件正在重载配置，请稍后重试"
    assert L("arg_error") == "⚠️ 一条命令只能指定一个 @服务器"


def test_events_empty_state_two_variants():
    # spec §4.4：events 空态两句变体（标题由 formatter 供，locale 只存空句）；旧 no_events 退役。
    assert L("events_empty") == "最近还没有新事件"
    assert L("events_empty_today") == "今天还没有新事件"
    assert "no_events" not in MESSAGES


def test_link_and_scene_keys_task12():
    # spec §4.20-4.22/§3：use_only_group 场景类戴 ⚠️；use_ok/unbind_ok 随结构化返回退役。
    assert L("use_only_group") == "⚠️ 该命令仅可在群聊中使用"
    assert "use_ok" not in MESSAGES
    assert "unbind_ok" not in MESSAGES
    # 拆键：link 专属键为新式，routing 六分支 no_server_configured/server_unknown 保原素文。
    assert L("link_add_unknown", server="X") == (
        "❌ 服务器「X」不存在或未就绪\n└ /pal link list 查看可用名称"
    )
    assert "❌" not in MESSAGES["server_unknown"]
    assert "link" not in MESSAGES["no_server_configured"]
    # whoami/whereami 取不到场景类戴 ⚠️（spec §4.27/4.28）。
    assert L("whoami_no_sender").startswith("⚠️")
    assert L("whereami_no_umo").startswith("⚠️")


def test_hint_strings_drop_old_command_names():
    # 用户可见提示串不得残留已删除的 /pal use、/pal servers
    for key in ("no_server_resolved", "not_authorized", "active_server_stale"):
        assert "/pal use" not in MESSAGES[key], key
    assert "/pal servers" not in MESSAGES["no_server_resolved"]
    # 改后指向新分级命令（服务器授权已收进 /pal link 组）
    assert "/pal link add" in MESSAGES["not_authorized"]
