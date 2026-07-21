"""guild 组命令层：strict 四分派 / 无参 usage / 找不到脚注（spec §4.6-4.9；§6#4/#11）。

guild 组随 gamedata 上游锁定 force-off（effective_enabled 恒 False）；本测试用
monkeypatch 清空 UPSTREAM_UNAVAILABLE_FEATURES 模拟「上游恢复」，验证过门后的分派
逻辑——落码即备。门关抑制由 commands_gating_test / gamedata_output_suppression_test
独立守（不在此弱化）。
"""
from types import SimpleNamespace

import pytest

from palworld_terminal.application import command_permissions
from palworld_terminal.application.command_permissions import CommandOverride
from palworld_terminal.application.dtos import (
    BaseDetailDTO,
    BaseDTO,
    EventView,
    GuildDetailDTO,
    GuildDTO,
)
from palworld_terminal.domain.enums import Confidence, EventType
from palworld_terminal.presentation.commands import Commands
from palworld_terminal.presentation.locale import L


@pytest.fixture(autouse=True)
def _upstream_restored(monkeypatch):
    # 模拟上游恢复：清空不可用集，让 guild 组过门（门关抑制另有独立测试守）。
    monkeypatch.setattr(command_permissions, "UPSTREAM_UNAVAILABLE_FEATURES", frozenset())


class _Query:
    def __init__(self, **dtos):
        self._dtos = dtos

    async def guilds(self, world):
        return self._dtos.get("guilds", [])

    async def guild(self, world, name):
        return self._dtos.get("guild")

    async def bases(self, world):
        return self._dtos.get("bases", [])

    async def base(self, world, key):
        return self._dtos.get("base")


def _cmds(query, mode="balanced"):
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(command_overrides={"guild": CommandOverride(enabled=True)}),
        privacy=SimpleNamespace(mode=mode),
        routing=SimpleNamespace(world_mode="multi"),
        world=SimpleNamespace(timezone="Asia/Tokyo"),
        servers=[SimpleNamespace(server_id="w", timezone="")],
    )
    c = Commands(routing=None, query=query, repo=None, cfg=cfg,
                 clock=SimpleNamespace(now=lambda: 0))

    async def _rw(umo, msg, sub, is_group):
        world = SimpleNamespace(world_id="w1", server_id="w")
        return world, SimpleNamespace(name=msg, server_override=None), None, "主服"
    c._resolve_world = _rw
    return c


# ---- guild list（§4.6：字段级裁剪）----

async def test_guild_list_renders_with_server_anchor():
    c = _cmds(_Query(guilds=[GuildDTO("Matrix", 4, 28, 2)]))
    out = await c.guilds("u", "@主服", True)
    assert out.startswith("🏰 公会 · 主服")
    assert "· Matrix 成员 ~4 · 工作帕鲁 28 · 据点 2" in out


async def test_guild_list_strict_field_trim_not_refused():
    c = _cmds(_Query(guilds=[GuildDTO("Matrix", 4, 28, 2)]), mode="strict")
    out = await c.guilds("u", "", True)
    assert "🏰 公会" in out       # 命令仍产出（非拒执行）
    assert "据点 2" not in out    # 字段级：砍据点计数位
    assert "成员 ~4" in out


# ---- guild info（§4.7：字段级裁剪 + 无参 usage + 找不到脚注）----

async def test_guild_info_empty_arg_usage():
    out = await _cmds(_Query(guild=None)).guild("u", "", True)
    assert out == "用法：/pal guild info <公会名>"


async def test_guild_info_not_found_with_footnote():
    out = await _cmds(_Query(guild=None)).guild("u", "Zion2", True)
    assert out.startswith("❌ 未找到公会「Zion2」")
    assert "/pal guild list" in out


async def test_guild_info_strict_field_trim_not_refused():
    dto = GuildDetailDTO(
        "Matrix", 900, 1200, 4, 28, 2, [("海岸木材场", Confidence.HIGH)],
        [EventView(occurred_at=0, event_type=EventType.NEW_BASE, name="河谷矿场")],
    )
    out = await _cmds(_Query(guild=dto), mode="strict").guild("u", "Matrix", True)
    assert out.startswith("🏰 公会 · Matrix")  # 命令仍产出
    assert "据点 2" not in out
    assert "近期动态" not in out
    assert "成员 ~4 · 工作帕鲁 28" in out


# ---- guild bases（§4.8：整命令拒执行 strict）----

async def test_guild_bases_renders_with_server_anchor():
    c = _cmds(_Query(bases=[BaseDTO(1, "海岸木材场", "Matrix", Confidence.HIGH, 18)]))
    out = await c.bases("u", "@主服", True)
    assert out.startswith("🏕️ 据点 · 主服")
    assert "· #1 海岸木材场 置信度高 · 工作帕鲁 18" in out


async def test_guild_bases_strict_refuses_whole_command():
    # 整命令拒执行（非字段级）——strict 切换后 DB 残留据点不经本命令绕出（§6#4）。
    c = _cmds(_Query(bases=[BaseDTO(1, "x", None, Confidence.HIGH, 1)]), mode="strict")
    out = await c.bases("u", "", True)
    assert out == L("bases_disabled_strict")
    assert out == "⚠️ 据点模块在 strict 隐私模式下停用"


# ---- guild base（§4.9：整命令拒执行 strict + 无参 usage + 找不到脚注）----

async def test_guild_base_renders():
    dto = BaseDetailDTO("海岸木材场", "Matrix", Confidence.HIGH, 18, 12, 17.5, 0.92,
                        {"working": 8}, 90.0)
    out = await _cmds(_Query(base=dto)).base("u", "#1", True)
    assert out.startswith("🏕️ 据点 · 海岸木材场")


async def test_guild_base_empty_arg_usage():
    out = await _cmds(_Query(base=None)).base("u", "", True)
    assert out == "用法：/pal guild base <据点名 或 #序号>"


async def test_guild_base_not_found_with_footnote():
    out = await _cmds(_Query(base=None)).base("u", "神秘据点", True)
    assert out.startswith("❌ 未找到据点「神秘据点」")
    assert "/pal guild bases" in out


async def test_guild_base_strict_refuses_whole_command():
    # 详情命令亦整命令拒执行（§6#4：DB 残留据点不可经 base 详情绕出）。
    dto = BaseDetailDTO("x", None, Confidence.HIGH, 1, 1, 1.0, 1.0, {}, 50.0)
    out = await _cmds(_Query(base=dto), mode="strict").base("u", "#1", True)
    assert out == L("bases_disabled_strict")
