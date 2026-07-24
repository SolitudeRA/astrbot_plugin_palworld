"""/pal me 图片卡：主题解析（auto 两分支 + 服务器时区，非宿主 UTC）· is_me_card 分流 ·
handler 降级（异常/None/空串）· 多 token 帮助（不静默退化）。spec §5·CT4/CT6/M7·T9。"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from main import _me_reply
from palworld_terminal.adapters.sqlite_repository import Repository
from palworld_terminal.application.query_service import QueryService
from palworld_terminal.domain.models import World
from palworld_terminal.infrastructure.cache import TTLCache
from palworld_terminal.infrastructure.clock import FakeClock
from palworld_terminal.infrastructure.database import Database
from palworld_terminal.infrastructure.migrations import apply_migrations
from palworld_terminal.presentation.commands import Commands

_W = World(world_id="w1", server_id="w", worldguid="g", epoch=0,
           server_name="S", version="1", first_seen_at=0, last_seen_at=0, current_day=1)
_SALT = b"x" * 32


def _epoch_at(hour: int, tz: str = "UTC") -> int:
    """给定 tz 的某日 hour 整点 → UTC epoch int（用于注入固定 clock，免 CI 时区抖动）。"""
    from zoneinfo import ZoneInfo
    return int(datetime(2023, 6, 15, hour, 0, tzinfo=ZoneInfo(tz)).timestamp())


def _theme_cmds(theme, clock, *, tz="UTC"):
    cfg = SimpleNamespace(
        presentation=SimpleNamespace(me_card_theme=theme),
        world=SimpleNamespace(timezone=tz),
        servers=[SimpleNamespace(server_id="w", timezone="")],
        permissions=SimpleNamespace(command_overrides={}),
        privacy=SimpleNamespace(mode="balanced"),
        routing=SimpleNamespace(world_mode="multi"),
    )
    return Commands(routing=None, query=None, repo=None, cfg=cfg, clock=clock, salt=_SALT)


# ---- 主题解析：显式 light/dark 直通（不看时钟）----

def test_explicit_light_passes_through():
    c = _theme_cmds("light", FakeClock(_epoch_at(23)))   # 深夜但配置 light
    assert c._resolve_me_card_theme(SimpleNamespace(server_id="w")) == "light"


def test_explicit_dark_passes_through():
    c = _theme_cmds("dark", FakeClock(_epoch_at(9)))     # 白天但配置 dark
    assert c._resolve_me_card_theme(SimpleNamespace(server_id="w")) == "dark"


# ---- auto 两分支：6<=hour<18 → light 否则 dark（服务器本地小时）----

def test_auto_daytime_light():
    c = _theme_cmds("auto", FakeClock(_epoch_at(10)))    # UTC 10 时
    assert c._resolve_me_card_theme(SimpleNamespace(server_id="w")) == "light"


def test_auto_nighttime_dark():
    c = _theme_cmds("auto", FakeClock(_epoch_at(22)))    # UTC 22 时
    assert c._resolve_me_card_theme(SimpleNamespace(server_id="w")) == "dark"


@pytest.mark.parametrize("hour,expected", [
    (5, "dark"), (6, "light"), (17, "light"), (18, "dark"),
])
def test_auto_boundaries(hour, expected):
    c = _theme_cmds("auto", FakeClock(_epoch_at(hour)))
    assert c._resolve_me_card_theme(SimpleNamespace(server_id="w")) == expected


def test_auto_uses_server_tz_not_host_utc():
    # UTC 22 时（宿主 UTC 小时=22→若误用会判 dark）；东京本地 = 次日 07 时 → light。
    # 断言用服务器时区解析（禁用宿主墙钟/UTC 小时，spec §5·CT4）。
    c = _theme_cmds("auto", FakeClock(_epoch_at(22, "UTC")), tz="Asia/Tokyo")
    assert c._resolve_me_card_theme(SimpleNamespace(server_id="w")) == "light"


# ---- is_me_card：me 后单 token 互斥 ----

@pytest.mark.parametrize("msg,expected", [
    ("me", False), ("me card", True), ("me 卡", True), ("me 图", True),
    ("me CARD", True), ("me hide", False), ("me show", False),
    ("me hide card", False),   # 多 token → 非图片请求（落文字路帮助）
    ("me card extra", False),
    ("me card @srv", True),    # 尾随 @server 覆写不影响
])
def test_is_me_card_single_token(msg, expected):
    c = _theme_cmds("light", FakeClock(0))
    assert c.is_me_card(msg) is expected


# ---- handler 降级（_me_reply）：异常/None/空串/无 HTML/渲染不可用 → 文字卡 ----

class _FakeCommands:
    def __init__(self, *, is_card, html, text="TEXT_CARD"):
        self._is_card = is_card
        self._html = html
        self._text = text
        self.me_calls = 0
        self.card_calls = 0

    def is_me_card(self, msg):
        return self._is_card

    async def me_card_html(self, *a):
        self.card_calls += 1
        return self._html

    async def me(self, *a):
        self.me_calls += 1
        return self._text


async def _render_ok(html, data):
    assert data == {}          # 第二参恒 {}，绝不透传 raw
    return "http://img/card.png"


async def _render_raises(html, data):
    raise RuntimeError("render boom")


async def _render_none(html, data):
    return None


async def _render_empty(html, data):
    return ""


async def test_non_card_returns_text_without_touching_card():
    c = _FakeCommands(is_card=False, html="<div>x</div>")
    kind, payload = await _me_reply(c, _render_ok, "u", "me", True, "s")
    assert (kind, payload) == ("text", "TEXT_CARD")
    assert c.card_calls == 0    # 非 card 请求不产 HTML


async def test_card_success_returns_image():
    c = _FakeCommands(is_card=True, html="<div>card</div>")
    kind, payload = await _me_reply(c, _render_ok, "u", "me card", True, "s")
    assert (kind, payload) == ("image", "http://img/card.png")
    assert c.me_calls == 0      # 成功出图不降级


async def test_card_render_exception_downgrades_to_text():
    c = _FakeCommands(is_card=True, html="<div>card</div>")
    kind, payload = await _me_reply(c, _render_raises, "u", "me card", True, "s")
    assert (kind, payload) == ("text", "TEXT_CARD")
    assert c.me_calls == 1


async def test_card_render_none_downgrades_to_text():
    c = _FakeCommands(is_card=True, html="<div>card</div>")
    kind, payload = await _me_reply(c, _render_none, "u", "me card", True, "s")
    assert (kind, payload) == ("text", "TEXT_CARD")


async def test_card_render_empty_downgrades_to_text():
    c = _FakeCommands(is_card=True, html="<div>card</div>")
    kind, payload = await _me_reply(c, _render_empty, "u", "me card", True, "s")
    assert (kind, payload) == ("text", "TEXT_CARD")


async def test_card_no_html_downgrades_without_render():
    # me_card_html 返 None（未绑定/悬空/feature 关/world err）→ 文字卡，绝不调 html_render
    c = _FakeCommands(is_card=True, html=None)

    async def _boom(html, data):
        raise AssertionError("html_render 不应被调用")

    kind, payload = await _me_reply(c, _boom, "u", "me card", True, "s")
    assert (kind, payload) == ("text", "TEXT_CARD")


async def test_card_no_renderer_downgrades():
    # html_render 不可用（如独立/stub 环境）→ 文字卡降级
    c = _FakeCommands(is_card=True, html="<div>card</div>")
    kind, payload = await _me_reply(c, None, "u", "me card", True, "s")
    assert (kind, payload) == ("text", "TEXT_CARD")


# ---- 多 token / 未知 token → me_usage 帮助（不静默退化）；card 文字路出名片 ----

@pytest.fixture
async def cmds_env(tmp_path):
    db = Database(tmp_path / "c.db")
    await db.open()
    await apply_migrations(db)
    clock = FakeClock(1_700_000_000)
    repo = Repository(db, clock)
    from tests.unit._perm import all_on
    cfg = SimpleNamespace(
        permissions=SimpleNamespace(command_overrides=all_on()),
        privacy=SimpleNamespace(mode="balanced"),
        routing=SimpleNamespace(world_mode="multi"),
        players=SimpleNamespace(rank_top_n=5, exclude_names=[]),
        world=SimpleNamespace(timezone="Asia/Tokyo"),
        servers=[SimpleNamespace(server_id="w", timezone="")],
        presentation=SimpleNamespace(me_card_theme="light"),
    )
    query = QueryService(repo, TTLCache(clock), cfg, None, clock, {}, world_cache={}, report=None)
    c = Commands(routing=None, query=query, repo=repo, cfg=cfg, clock=clock, salt=_SALT)

    async def _rw(umo, msg, sub, is_group):
        from palworld_terminal.presentation.server_arg import parse_arg
        return _W, parse_arg(msg, sub), None, "主服"
    c._reads._resolve_world = _rw
    yield repo, c
    await db.close()


async def _bind_alice(repo, c):
    await repo._db.execute_write(
        "INSERT INTO players (player_key, world_id, latest_name, first_seen_at, "
        "last_seen_at, latest_level, latest_guild_key, id_confidence) "
        "VALUES ('k1', 'w1', 'Alice', 0, 100, 12, NULL, 'high')")
    await c.bind("u", "bind Alice", True, "aiocqhttp:1")


async def test_me_multi_token_shows_usage_not_silent(cmds_env):
    repo, c = cmds_env
    await _bind_alice(repo, c)
    out = await c.me("u", "me hide card", True, "aiocqhttp:1")
    assert "用法" in out and "card" in out
    # 不静默退化：既没执行隐藏也没渲染名片
    assert "已将你" not in out and "🎴 我的名片" not in out


async def test_me_unknown_token_shows_usage(cmds_env):
    repo, c = cmds_env
    await _bind_alice(repo, c)
    out = await c.me("u", "me bogus", True, "aiocqhttp:1")
    assert "用法" in out


async def test_me_card_token_text_path_renders_card(cmds_env):
    # 文字路遇 card 别名（图片降级落点）→ 名片文字（format_me），不出用法
    repo, c = cmds_env
    await _bind_alice(repo, c)
    out = await c.me("u", "me card", True, "aiocqhttp:1")
    assert "🎴 我的名片 · Alice" in out
    assert "用法" not in out


async def test_me_card_html_unbound_returns_none(cmds_env):
    repo, c = cmds_env   # 未绑定 sender
    html = await c.me_card_html("u", "me card", True, "aiocqhttp:9")
    assert html is None


async def test_me_card_html_produces_html_when_bound(cmds_env):
    repo, c = cmds_env
    await _bind_alice(repo, c)
    html = await c.me_card_html("u", "me card", True, "aiocqhttp:1")
    assert html is not None
    assert "🎴" not in html          # 图片卡不含文字卡标题 emoji
    assert 'data-theme="light"' in html
    assert "Alice" in html
    # 隐私：无 id/坐标/绝对时间戳/player_key
    for banned in ("instance_id", "player_key", "1700000000", "1970"):
        assert banned not in html


async def test_me_card_html_feature_off_returns_none(cmds_env):
    repo, c = cmds_env
    await _bind_alice(repo, c)
    from tests.unit._perm import overrides
    c._cfg.permissions.command_overrides = overrides(players=False)
    html = await c.me_card_html("u", "me card", True, "aiocqhttp:1")
    assert html is None          # feature 关 → None（文字路出 feature_disabled）
