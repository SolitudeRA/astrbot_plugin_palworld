"""审查修复 E1:重载与在途命令的竞态防护(在途计数 + quiescence 等待)。

修复前:命令通过 busy 门后停在内部 await 时,保存配置触发的旧容器
stop() 会关掉它正在用的 DB 连接,命令崩溃。修复后重载在 stop 前等待
在途操作退出;新操作被 _restarting 挡在门外。
"""
import asyncio
from types import SimpleNamespace

from main import PalWorldTerminal
from tests.unit.main_test import _FakeContext, _raw_config

# 已确认安装：_guarded 现读 self._container.config.routing.setup_confirmed，
# 给替身容器装上（True = 首次设置闸放行，测试聚焦在途/busy 竞态而非设置闸）。
_CONFIRMED = SimpleNamespace(routing=SimpleNamespace(setup_confirmed=True))


def _plugin(tmp_path):
    return PalWorldTerminal(_FakeContext(), _raw_config(tmp_path))


async def test_guarded_call_returns_result(tmp_path):
    plugin = _plugin(tmp_path)

    class _Cmds:
        async def status(self, *a):
            return "ok"

    class _C:
        commands = _Cmds()
        config = _CONFIRMED

    plugin._container = _C()
    out = await plugin._guarded(lambda c: c.commands.status("u", "m", True), "world")
    assert out == "ok"
    assert plugin._inflight == 0 and plugin._idle.is_set()


async def test_guarded_rejects_while_restarting(tmp_path):
    plugin = _plugin(tmp_path)
    plugin._container = object()
    plugin._restarting = True
    # 重载中 busy 守卫先于设置闸命中，故 command_str 不影响（container 亦无 config）
    out = await plugin._guarded(lambda c: c.commands.status(), "world")
    assert "重载" in out


async def test_reload_waits_for_inflight_command(tmp_path):
    # 慢命令在途时触发重载:stop 必须等命令退出后才执行
    plugin = _plugin(tmp_path)
    order: list[str] = []
    release = asyncio.Event()

    class _Cmds:
        async def status(self, *a):
            order.append("cmd-start")
            await release.wait()
            order.append("cmd-end")
            return "done"

    class _OldContainer:
        commands = _Cmds()
        config = _CONFIRMED

        async def stop(self):
            order.append("stop")

    plugin._container = _OldContainer()

    cmd = asyncio.create_task(
        plugin._guarded(lambda c: c.commands.status("u", "m", True), "world"))
    await asyncio.sleep(0)  # 命令进入在途(停在 release.wait)
    assert order == ["cmd-start"]

    async def fake_wait_then_release():
        await asyncio.sleep(0.01)
        release.set()  # 模拟命令自然完成

    # 触发重载等待:_restarting 置位后等待 quiescence
    plugin._restarting = True
    rel = asyncio.create_task(fake_wait_then_release())
    await plugin._wait_quiescent(timeout=2.0)
    await plugin._container.stop()

    assert await cmd == "done"
    await rel
    # 关键顺序:命令先退出,stop 才发生
    assert order == ["cmd-start", "cmd-end", "stop"]


async def test_wait_quiescent_times_out_not_hangs(tmp_path):
    # 个别慢查询卡住时,重载不至于永久阻塞(超时兜底)
    plugin = _plugin(tmp_path)
    plugin._inflight = 1
    plugin._idle.clear()
    await asyncio.wait_for(plugin._wait_quiescent(timeout=0.05), timeout=1.0)
