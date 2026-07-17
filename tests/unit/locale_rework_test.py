from palworld_terminal.presentation.locale import MESSAGES, L


def test_new_keys_present():
    assert "server_usage" in MESSAGES
    assert L("unbind_self_ok", name="Alice") == "已解除你与玩家「Alice」的绑定。"
    assert MESSAGES["unbind_self_none"]


def test_output_redesign_first_wave_dead_keys_removed():
    # spec §7：auth_error / derived_note 均零调用点，第一波删除。
    assert "auth_error" not in MESSAGES
    assert "derived_note" not in MESSAGES


def test_output_redesign_first_wave_new_keys():
    # spec §3 / §7：busy 与 arg_error 收编硬编码，戴 ⚠️ 前缀。
    assert L("busy") == "⚠️ 插件正在重载配置，请稍后重试"
    assert L("arg_error") == "⚠️ 一条命令只能指定一个 @服务器"


def test_hint_strings_drop_old_command_names():
    # 用户可见提示串不得残留已删除的 /pal use、/pal servers
    for key in ("no_server_resolved", "not_authorized", "active_server_stale"):
        assert "/pal use" not in MESSAGES[key], key
    assert "/pal servers" not in MESSAGES["no_server_resolved"]
    # 改后指向新分级命令（服务器授权已收进 /pal link 组）
    assert "/pal link add" in MESSAGES["not_authorized"]
