"""根因 A 回归：用户名只在 quart g 上；_has_identity 据此，三端点无身份回 unauthorized。"""
import sys
import types


def _install_fake_quart(username):
    """装一个最小 quart 假模块：g（可选 username）、jsonify（透传 payload）、request（有 get_json，无 username）。"""
    q = types.ModuleType("quart")

    class _G:
        pass

    g = _G()
    if username is not None:
        g.username = username
    q.g = g
    q.jsonify = lambda payload: payload  # 薄壳测试只关心 payload 内容

    class _Req:
        # 关键：request 上没有 username（印证根因 A：读 request.username 恒 None）
        async def get_json(self, silent=False):
            return {}

    q.request = _Req()
    sys.modules["quart"] = q
    return q


def _install_fake_quart_no_app_context():
    """装一个模拟无 app context 的 quart 假模块：g 抛 RuntimeError。"""
    q = types.ModuleType("quart")

    class _GNoContext:
        """模拟 Quart LocalProxy 在 app context 外的行为：访问任何属性都抛 RuntimeError。"""
        def __getattr__(self, name):
            raise RuntimeError("Working outside of application context.")

    q.g = _GNoContext()
    q.jsonify = lambda payload: payload

    class _Req:
        async def get_json(self, silent=False):
            return {}

    q.request = _Req()
    sys.modules["quart"] = q
    return q


def _raw():
    return {
        "servers": [], "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
        "history": {}, "features": {},
    }


class _FakeContext:
    def register_web_api(self, *a, **k):
        pass


def test_current_username_reads_g_not_request():
    _install_fake_quart("admin")
    import main as main_mod
    assert main_mod.PalChronicle._current_username() == "admin"


def test_has_identity_true_when_g_has_username():
    _install_fake_quart("admin")
    import main as main_mod
    assert main_mod.PalChronicle._has_identity() is True


def test_has_identity_false_when_g_missing_username():
    _install_fake_quart(None)
    import main as main_mod
    assert main_mod.PalChronicle._has_identity() is False


async def test_config_get_returns_unauthorized_without_identity():
    _install_fake_quart(None)
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    payload = await plugin._web_config_get()
    assert payload == {"ok": False, "error": "unauthorized", "detail": {}}


async def test_config_get_ok_with_identity():
    _install_fake_quart("admin")
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    payload = await plugin._web_config_get()
    assert payload.get("ok") is True and "config" in payload


def test_current_username_none_without_app_context():
    _install_fake_quart_no_app_context()
    import main as main_mod
    assert main_mod.PalChronicle._current_username() is None


async def test_config_get_unauthorized_without_app_context():
    _install_fake_quart_no_app_context()
    import main as main_mod
    plugin = main_mod.PalChronicle(_FakeContext(), _raw())
    payload = await plugin._web_config_get()
    assert payload == {"ok": False, "error": "unauthorized", "detail": {}}
