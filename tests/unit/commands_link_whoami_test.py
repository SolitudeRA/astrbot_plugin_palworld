"""Task 12：link 组回执（add/remove/list）+ whoami + whereami（spec §4.20-4.22/§4.27-4.28）。

真 Repository + 真 RoutingService（结构化返回）+ 真 Commands 端到端渲染：
- link add 成功/换活动脚注/不存在（拆键 link_add_unknown）/私聊 ⚠️/usage 拆分。
- link remove 成功/撤活动脚注/无授权记录素文（先查存在性）/私聊 ⚠️/usage 拆分。
- link list 三态点（可达性=metric_stale 派生）/私聊授权段省略。
- whoami 正常/管理员/取不到；whereami restricted 多模式·单模式变体/open 分流/取不到。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.routing_service import RoutingService
from palworld_terminal.config import parse_config
from palworld_terminal.domain.models import World, WorldMetric
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.commands import Commands

_NOW = 1_700_000_000


def _raw(*, world_mode="multi", access="restricted", admins=None,
         single_groups=None, extra_servers=None) -> dict:
    servers = [
        {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": True,
         "timezone": ""},
    ]
    servers.extend(extra_servers or [])
    raw = {
        "servers": servers,
        "group_bindings": [],
        "routing": {"access_mode": access, "default_server": "", "world_mode": world_mode,
                    "setup_confirmed": True},
        "polling": {"metrics_seconds": 30, "players_seconds": 30, "info_seconds": 600,
                    "settings_seconds": 1800, "game_data_seconds": 120, "jitter_ratio": 0.1,
                    "max_concurrency": 6},
        "world": {"timezone": "Asia/Tokyo", "locale": "zh-CN", "fps_smooth": 50,
                  "fps_moderate": 35, "fps_laggy": 20},
        "bases": {"enabled": True, "assignment_radius": 5000, "ambiguity_ratio": 0.2,
                  "confirmation_samples": 3, "position_grid_size": 2000, "z_weight": 0.5},
        "privacy": {"mode": "balanced", "public_exact_ping": False, "public_positions": False,
                    "ping_good_ms": 60, "ping_ok_ms": 120, "uncertain_timeout": 900},
        "history": {"raw_metrics_days": 7, "aggregate_days": 90, "session_days": 365,
                    "observation_days": 180},
    }
    if admins is not None:
        raw["permission_admins"] = [{"id": a, "note": ""} for a in admins]
    if single_groups is not None:
        raw["single_allowed_groups"] = [{"umo": g, "note": ""} for g in single_groups]
    return raw


@pytest.fixture
async def env(tmp_path: Path):
    db = Database(tmp_path / "t.sqlite3")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(_NOW)
    repo = Repository(db, clock)

    async def _seed_world(server_id: str, world_id: str, observed_at: int | None):
        """给某服务器种一个 world；observed_at 非 None 时种一条 metric 定其可达性。"""
        await repo.upsert_world(World(
            world_id=world_id, server_id=server_id, worldguid="g", epoch=0,
            server_name="S", version="1", first_seen_at=_NOW, last_seen_at=_NOW, current_day=1,
        ))
        if observed_at is not None:
            await repo.insert_metric(WorldMetric(
                world_id=world_id, observed_at=observed_at, fps=60, frame_time=16.0,
                online_players=1, world_day=1, basecamp_count=0, max_players=32,
            ))

    def build(raw: dict):
        cfg = parse_config(raw, {})
        routing = RoutingService(repo, cfg)
        return Commands(routing=routing, query=None, repo=repo, cfg=cfg, clock=clock)

    yield build, repo, _seed_world
    await db.close()


# ---- link add（§4.21）----

async def test_link_add_success(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.link_add("umo1", "alpha", is_group=True)
    assert out == "✅ 已授权本群 · alpha（设为当前活动）"


async def test_link_add_replaced_active_footnote(env):
    build, _repo, _seed = env
    c = build(_raw(extra_servers=[
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": True,
         "timezone": ""},
    ]))
    await c.link_add("umo1", "alpha", is_group=True)  # alpha 成活动
    out = await c.link_add("umo1", "beta", is_group=True)
    assert "✅ 已授权本群 · beta（设为当前活动）" in out
    assert "└ 原活动服务器「alpha」已替换" in out


async def test_link_add_unknown_split_key(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.link_add("umo1", "ghost", is_group=True)
    assert out == "❌ 服务器「ghost」不存在或未就绪\n└ /pal link list 查看可用名称"


async def test_link_add_private_warns(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.link_add("umo1", "alpha", is_group=False)
    assert out == "⚠️ 该命令仅可在群聊中使用"


async def test_link_add_usage_split(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.link_add("umo1", "", is_group=True)
    assert out == "用法：/pal link add <服务器名>"


# ---- link remove（§4.22）----

async def test_link_remove_success(env):
    build, _repo, _seed = env
    c = build(_raw(extra_servers=[
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": True,
         "timezone": ""},
    ]))
    await c.link_add("umo1", "alpha", is_group=True)  # alpha 活动
    await c.link_add("umo1", "beta", is_group=True)   # beta 活动，alpha 退非活动
    out = await c.link_remove("umo1", "alpha", is_group=True)
    assert out == "✅ 已撤销本群授权 · alpha"


async def test_link_remove_active_footnote(env):
    build, _repo, _seed = env
    c = build(_raw())
    await c.link_add("umo1", "alpha", is_group=True)  # alpha 活动
    out = await c.link_remove("umo1", "alpha", is_group=True)
    assert "✅ 已撤销本群授权 · alpha" in out
    assert "└ 该服务器原为本群活动服务器，后续需重新授权指定" in out


async def test_link_remove_no_record_plain(env):
    # 无授权记录 → 素文中性无操作（先查存在性，修幂等假成功）
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.link_remove("umo1", "alpha", is_group=True)
    assert out == "本群没有「alpha」的授权记录"


async def test_link_remove_private_warns(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.link_remove("umo1", "alpha", is_group=False)
    assert out == "⚠️ 该命令仅可在群聊中使用"


async def test_link_remove_usage_split(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.link_remove("umo1", "", is_group=True)
    assert out == "用法：/pal link remove <服务器名>"


# ---- link list 三态点 + 私聊省略（§4.20）----

async def test_link_list_three_state_dots(env):
    build, _repo, seed = env
    c = build(_raw(extra_servers=[
        {"name": "beta", "enabled": True, "base_url": "http://127.0.0.1:8213",
         "username": "admin", "password": "pw", "timeout": 10, "verify_tls": True,
         "timezone": ""},
        # gamma 无凭据 → 未就绪
        {"name": "gamma", "enabled": True, "base_url": "http://127.0.0.1:8214",
         "username": "admin", "password": "", "timeout": 10, "verify_tls": True,
         "timezone": ""},
    ]))
    await seed("alpha", "alpha:g:0", _NOW - 10)     # 新鲜 → 🟢 在线
    await seed("beta", "beta:g:0", _NOW - 10_000)   # 陈旧 → 🔴 离线
    out = await c.link_list("umo1", is_group=True, is_admin=False)
    assert "· alpha 🟢 在线" in out
    assert "· beta 🔴 离线" in out
    assert "· gamma 🟡 未就绪" in out


async def test_link_list_ready_no_world_is_offline(env):
    build, _repo, _seed = env
    c = build(_raw())  # alpha ready 但从未有 world/metric
    out = await c.link_list("umo1", is_group=True, is_admin=False)
    assert "· alpha 🔴 离线" in out


async def test_link_list_private_omits_auth(env):
    build, _repo, seed = env
    c = build(_raw())
    await seed("alpha", "alpha:g:0", _NOW - 10)
    out = await c.link_list("umo1", is_group=False, is_admin=False)
    assert "· alpha 🟢 在线" in out
    assert "本群" not in out


# ---- whoami（§4.27）----

async def test_whoami_normal(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.whoami("aiocqhttp:1234567890")
    assert out == (
        "🪪 我的账号标识\naiocqhttp:1234567890\n"
        "└ 建议私聊使用；把标识交给管理员加入权限名单"
    )


async def test_whoami_admin_note(env):
    build, _repo, _seed = env
    c = build(_raw(admins=["aiocqhttp:1234567890"]))
    out = await c.whoami("aiocqhttp:1234567890")
    assert "你已在管理员名单中" in out
    assert out.startswith("🪪 我的账号标识\naiocqhttp:1234567890")


async def test_whoami_no_sender(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.whoami("aiocqhttp:")
    assert out == "⚠️ 当前场景无法识别你的账号，请换个聊天场景再试"


# ---- whereami（§4.28）----

async def test_whereami_restricted_multi_authorized(env):
    build, _repo, _seed = env
    c = build(_raw(access="restricted", world_mode="multi"))
    await c.link_add("g1", "alpha", is_group=True)  # 授权并活动
    out = await c.whereami("g1")
    assert out.startswith("📍 本群标识\ng1")
    assert "本群已授权：alpha（当前活动）" in out
    assert "└ 未授权时把标识交给管理员即可开通查询" in out


async def test_whereami_restricted_multi_unauthorized(env):
    build, _repo, _seed = env
    c = build(_raw(access="restricted", world_mode="multi"))
    out = await c.whereami("g2")
    assert "本群尚未授权" in out
    assert "└ 未授权时把标识交给管理员即可开通查询" in out


async def test_whereami_restricted_single_authorized_no_active(env):
    build, _repo, _seed = env
    c = build(_raw(access="restricted", world_mode="single", single_groups=["g1"]))
    out = await c.whereami("g1")
    assert "本群已授权：alpha" in out
    assert "当前活动" not in out  # active 是多模式概念
    assert "└ 未授权时把标识交给管理员即可开通查询" in out


async def test_whereami_restricted_single_unauthorized(env):
    build, _repo, _seed = env
    c = build(_raw(access="restricted", world_mode="single", single_groups=["g1"]))
    out = await c.whereami("g2")
    assert "本群尚未授权" in out
    assert "└ 未授权时把标识交给管理员即可开通查询" in out


async def test_whereami_open_mode_no_auth_needed(env):
    build, _repo, _seed = env
    c = build(_raw(access="open", world_mode="multi"))
    out = await c.whereami("g1")
    assert "当前为开放模式，无需授权即可查询" in out
    assert "把标识交给管理员" not in out  # open 模式无脚注引导


async def test_whereami_no_umo(env):
    build, _repo, _seed = env
    c = build(_raw())
    out = await c.whereami("")
    assert out == "⚠️ 当前场景无法识别群标识，请在群聊中使用"
