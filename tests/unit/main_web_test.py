"""main.py 插件页面接线：命令守卫在重启窗口拦截、web api handler 注册。"""


class _FakeContext:
    def __init__(self):
        self.registered = []

    def register_web_api(self, route, handler, methods, desc):
        self.registered.append((route, tuple(methods)))


class _Event:
    unified_msg_origin = "u1"
    message_str = ""
    role = "admin"

    def plain_result(self, text):
        return text

    def is_private_chat(self):
        return False


async def _collect(agen):
    out = []
    async for x in agen:
        out.append(x)
    return out


def _raw():
    return {
        "servers": [], "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
        "history": {},
    }


async def test_command_guarded_during_restart():
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    plugin._restarting = True
    out = await _collect(plugin.status(_Event()))
    assert len(out) == 1 and "重载" in out[0]  # 未触达 None 容器


async def test_command_guarded_when_container_none():
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    plugin._container = None
    plugin._restarting = False
    out = await _collect(plugin.online(_Event()))
    assert len(out) == 1 and "重载" in out[0]


def test_register_web_api_called_with_prefixed_routes():
    import main as main_mod
    ctx = _FakeContext()
    plugin = main_mod.PalChronicle(ctx, _raw())
    plugin._register_web_api()
    routes = {r for r, _ in ctx.registered}
    assert "/astrbot_plugin_palword/config/get" in routes
    assert "/astrbot_plugin_palword/config/save" in routes
    assert "/astrbot_plugin_palword/status/overview" in routes


def test_no_register_when_context_lacks_method():
    import main as main_mod

    class _Bare:
        pass

    plugin = main_mod.PalChronicle(_Bare(), _raw())
    # 不应抛异常（stub 护栏）
    plugin._maybe_register_web_api()
