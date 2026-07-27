"""config/locale 编排：locale-only patch——只写 world.locale、不夹带/不回填其它字段。

顶栏语言切换器（T8）专用：复用 save 的锁/节流依赖，但仅校验并落 world.locale，
触发 reload 使 bot 输出语言同步。
"""
import asyncio
import copy
import json

import pytest

from palworld_terminal.presentation.web_api import handle_locale_patch

_OLD = {
    "servers": [{"name": "a", "base_url": "http://h", "username": "admin",
                 "password": "oldpw", "password_env": "", "timeout": 10,
                 "enabled": True, "verify_tls": True, "timezone": ""}],
    "custom_headers": [], "group_bindings": [],
    "routing": {"access_mode": "restricted", "default_server": ""},
    "polling": {}, "world": {"locale": "zh-CN", "fps_smooth": 55}, "bases": {},
    "privacy": {"mode": "balanced"}, "history": {},
}


async def _ok_restart(result):
    return {"ok": True}


async def _boom_if_called(result):
    raise AssertionError("apply_and_restart 不应被调用")


async def test_legal_locale_writes_only_world_locale():
    captured = {}

    async def spy(result):
        captured["result"] = result
        return {"ok": True}

    code, p = await handle_locale_patch(
        {"locale": "ja"}, old_raw=_OLD, env={}, lock=asyncio.Lock(),
        now=100.0, last_save_ts=None, apply_and_restart=spy)
    assert code == 200 and p["ok"] is True
    result = captured["result"]
    # 只写 world.locale：其余字段一律与 old_raw 相同——未夹带草稿、未回填
    expected = copy.deepcopy(_OLD)
    expected["world"]["locale"] = "ja"
    assert result == expected
    # world 节其它键（fps_smooth）保留，不被整节替换
    assert result["world"]["fps_smooth"] == 55
    # 深拷保护：old_raw 未被就地改写
    assert _OLD["world"]["locale"] == "zh-CN"


async def test_illegal_locale_rejected_and_no_restart():
    called = False

    async def spy(result):
        nonlocal called
        called = True
        return {"ok": True}

    code, p = await handle_locale_patch(
        {"locale": "fr"}, old_raw=_OLD, env={}, lock=asyncio.Lock(),
        now=100.0, last_save_ts=None, apply_and_restart=spy)
    assert code == 200 and p["ok"] is False
    assert p["error"] == "invalid_field"
    assert p["detail"] == {"path": "world.locale"}
    assert called is False   # 非法值不触发 reload


async def test_missing_locale_rejected():
    code, p = await handle_locale_patch(
        {}, old_raw=_OLD, env={}, lock=asyncio.Lock(),
        now=100.0, last_save_ts=None, apply_and_restart=_boom_if_called)
    assert p["ok"] is False and p["error"] == "invalid_field"
    assert p["detail"] == {"path": "world.locale"}


async def test_none_body_rejected_without_crash():
    code, p = await handle_locale_patch(
        None, old_raw=_OLD, env={}, lock=asyncio.Lock(),
        now=100.0, last_save_ts=None, apply_and_restart=_boom_if_called)
    assert code == 200 and p["ok"] is False and p["error"] == "invalid_field"


async def test_lock_busy_returns_save_in_progress():
    lock = asyncio.Lock()
    await lock.acquire()
    try:
        code, p = await handle_locale_patch(
            {"locale": "ja"}, old_raw=_OLD, env={}, lock=lock, now=100.0,
            last_save_ts=None, apply_and_restart=_boom_if_called)
        assert code == 200 and p["error"] == "save_in_progress"
    finally:
        lock.release()


async def test_too_frequent():
    code, p = await handle_locale_patch(
        {"locale": "ja"}, old_raw=_OLD, env={}, lock=asyncio.Lock(),
        now=102.0, last_save_ts=100.0, apply_and_restart=_boom_if_called)
    assert p["error"] == "too_frequent"


async def test_success_returns_redacted_config_and_saved_ts():
    code, p = await handle_locale_patch(
        {"locale": "en"}, old_raw=_OLD, env={}, lock=asyncio.Lock(),
        now=300.0, last_save_ts=None, apply_and_restart=_ok_restart)
    assert code == 200 and p["ok"] is True
    assert p["saved_ts"] == 300.0
    # 前端刷新用的脱敏配置：明文密码绝不回传
    assert "oldpw" not in json.dumps(p)
    for s in p["config"].get("servers", []):
        assert s.get("password", "") == ""
        assert "__row_id" in s


async def test_world_node_created_when_absent():
    old = {"servers": [], "routing": {}}   # 无 world 节
    captured = {}

    async def spy(result):
        captured["result"] = result
        return {"ok": True}

    code, p = await handle_locale_patch(
        {"locale": "ja"}, old_raw=old, env={}, lock=asyncio.Lock(),
        now=1.0, last_save_ts=None, apply_and_restart=spy)
    assert p["ok"] is True
    assert captured["result"]["world"] == {"locale": "ja"}


async def test_world_node_non_dict_replaced():
    old = {"world": None}   # world 节非 dict（异常态）→ 建新 dict，不崩
    captured = {}

    async def spy(result):
        captured["result"] = result
        return {"ok": True}

    code, p = await handle_locale_patch(
        {"locale": "en"}, old_raw=old, env={}, lock=asyncio.Lock(),
        now=1.0, last_save_ts=None, apply_and_restart=spy)
    assert p["ok"] is True
    assert captured["result"]["world"] == {"locale": "en"}


async def test_restart_failure_propagated():
    async def boom(result):
        return {"ok": False, "error": "restart_failed_rolled_back"}

    code, p = await handle_locale_patch(
        {"locale": "ja"}, old_raw=_OLD, env={}, lock=asyncio.Lock(),
        now=400.0, last_save_ts=None, apply_and_restart=boom)
    assert p["ok"] is False and p["error"] == "restart_failed_rolled_back"


async def test_lock_released_after_success():
    lock = asyncio.Lock()
    await handle_locale_patch(
        {"locale": "ja"}, old_raw=_OLD, env={}, lock=lock, now=1.0,
        last_save_ts=None, apply_and_restart=_ok_restart)
    assert not lock.locked()


async def test_lock_released_when_apply_raises():
    lock = asyncio.Lock()

    async def raiser(result):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await handle_locale_patch(
            {"locale": "ja"}, old_raw=_OLD, env={}, lock=lock, now=500.0,
            last_save_ts=None, apply_and_restart=raiser)
    assert not lock.locked()
