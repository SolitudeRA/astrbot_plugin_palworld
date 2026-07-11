"""config/save 编排：锁 409、频率限制、校验失败、重启回调透传。"""
import asyncio

from palchronicle.presentation.web_api import handle_config_save

_OLD = {
    "servers": [{"name": "a", "base_url": "http://h", "username": "admin",
                 "password": "oldpw", "password_env": "", "timeout": 10,
                 "enabled": True, "verify_tls": True, "timezone": ""}],
    "custom_headers": [], "group_bindings": [],
    "routing": {"access_mode": "restricted", "default_server": ""},
    "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
    "history": {},
}


def _body():
    return {
        "servers": [{"__row_id": "srv-0", "name": "a", "base_url": "http://h",
                     "username": "admin", "password": "__unchanged__",
                     "password_env": "", "timeout": 10, "enabled": True,
                     "verify_tls": True, "timezone": "", "password_set": True}],
        "custom_headers": [], "group_bindings": [],
        "routing": {"access_mode": "restricted", "default_server": ""},
        "polling": {}, "world": {}, "bases": {}, "privacy": {"mode": "balanced"},
        "history": {},
    }


async def _ok_restart(cand):
    return {"ok": True, "warnings": {"skipped_servers": [], "skipped_headers": []}}


async def test_lock_busy_returns_save_in_progress():
    lock = asyncio.Lock()
    await lock.acquire()
    try:
        code, p = await handle_config_save(
            _body(), old_raw=_OLD, env={}, lock=lock, now=100.0,
            last_save_ts=None, apply_and_restart=_ok_restart)
        assert code == 200 and p["error"] == "save_in_progress"
    finally:
        lock.release()


async def test_too_frequent():
    code, p = await handle_config_save(
        _body(), old_raw=_OLD, env={}, lock=asyncio.Lock(), now=102.0,
        last_save_ts=100.0, apply_and_restart=_ok_restart)
    assert p["error"] == "too_frequent"


async def test_validation_failure_does_not_restart():
    called = False

    async def spy(cand):
        nonlocal called
        called = True
        return {"ok": True}

    body = _body()
    body["routing"]["access_mode"] = "bad"
    code, p = await handle_config_save(
        body, old_raw=_OLD, env={}, lock=asyncio.Lock(), now=200.0,
        last_save_ts=None, apply_and_restart=spy)
    assert p["ok"] is False and p["error"] == "invalid_field"
    assert called is False   # 校验失败不触发重启


async def test_success_passes_warnings_and_saved_ts():
    code, p = await handle_config_save(
        _body(), old_raw=_OLD, env={}, lock=asyncio.Lock(), now=300.0,
        last_save_ts=None, apply_and_restart=_ok_restart)
    assert code == 200 and p["ok"] is True
    assert p["saved_ts"] == 300.0
    assert p["warnings"] == {"skipped_servers": [], "skipped_headers": []}


async def test_lock_released_after_success():
    lock = asyncio.Lock()
    await handle_config_save(_body(), old_raw=_OLD, env={}, lock=lock, now=1.0,
                             last_save_ts=None, apply_and_restart=_ok_restart)
    assert not lock.locked()   # async with 已释放


async def test_restart_failure_propagated():
    async def boom(cand):
        return {"ok": False, "error": "restart_failed_rolled_back"}

    code, p = await handle_config_save(
        _body(), old_raw=_OLD, env={}, lock=asyncio.Lock(), now=400.0,
        last_save_ts=None, apply_and_restart=boom)
    assert p["ok"] is False and p["error"] == "restart_failed_rolled_back"
