from tests.unit._ns_loader import namespaced_main


class _Ev:
    def __init__(self, sender="u1"):
        self._sender = sender
    message_str = "whoami"
    unified_msg_origin = "test:GroupMessage:g1"
    role = "member"  # 关键:框架非管理员

    def is_private_chat(self): return False
    def get_group_id(self): return "g1"
    def get_platform_name(self): return "test"
    def get_sender_id(self): return self._sender
    def plain_result(self, s): return s


def _raw(admins, locked):
    return {
        "servers": [], "group_bindings": [],
        "routing": {"access_mode": "open", "default_server": ""},
        "polling": {}, "world": {}, "bases": {}, "privacy": {}, "history": {},
        "features": {"players": True},
        "permission_admins": [{"id": a, "note": ""} for a in admins],
        "admin_only_commands": list(locked),
    }


async def test_whoami_returns_composite_id(tmp_path, monkeypatch):
    with namespaced_main() as mod:
        monkeypatch.setattr(mod, "_resolve_data_dir", lambda: tmp_path)
        plugin = mod.PalWorldTerminal(object(), _raw([], []))
        await plugin.initialize()
        try:
            outs = [o async for o in plugin.whoami(_Ev(sender="12345"))]
            assert any("test:12345" in o for o in outs)
        finally:
            await plugin.terminate()


async def test_locked_command_blocks_non_admin(tmp_path, monkeypatch):
    with namespaced_main() as mod:
        monkeypatch.setattr(mod, "_resolve_data_dir", lambda: tmp_path)
        # 锁定完整路径 player info,请求者非名单成员(role=member 也不放行)
        plugin = mod.PalWorldTerminal(object(), _raw([], ["player info"]))
        await plugin.initialize()
        try:
            ev = _Ev(sender="12345"); ev.message_str = "player info Alice"
            outs = [o async for o in plugin.player(ev)]
            assert any("需要管理员权限" in o for o in outs)
        finally:
            await plugin.terminate()
