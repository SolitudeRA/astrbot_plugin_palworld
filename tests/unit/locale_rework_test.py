from palworld_terminal.presentation.locale import MESSAGES, L


def test_new_keys_present():
    assert "server_usage" in MESSAGES
    assert L("unbind_self_ok", name="Alice") == "已解除你与玩家「Alice」的绑定。"
    assert MESSAGES["unbind_self_none"]


def test_hint_strings_drop_old_command_names():
    # 用户可见提示串不得残留已删除的 /pal use、/pal servers
    for key in ("no_server_resolved", "not_authorized", "active_server_stale"):
        assert "/pal use" not in MESSAGES[key], key
    assert "/pal servers" not in MESSAGES["no_server_resolved"]
    # 改后指向新命令
    assert "/pal server add" in MESSAGES["not_authorized"]
