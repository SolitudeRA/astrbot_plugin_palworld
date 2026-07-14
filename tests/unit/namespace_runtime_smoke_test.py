"""命名空间加载下的全命令运行时冒烟。

背景:astrbot_namespace_load_test 只覆盖模块导入;函数体内的惰性问题
(如曾在实机炸掉 /pal me 的函数内绝对自导入)导入时不触发。本测试在
同等命名空间条件下真正 initialize 插件、种入世界与玩家数据,把 11 分级 handler
带子动作参数走一遍(world/guild/player/server/link 5 组各子动作 + 6 扁平,calls
共 28 项;link 走 list/add/remove、server 走 7 写子动作;player bind 成功后再走
me/player unbind,复现当年实机 bug 的等价深分支;7 条服务器管控写命令
require_confirmation 默认关直执、kick/ban 经 _FakeRest 种在线玩家走到
execute_target)——任何仅在真实 AstrBot 加载形态下才暴露的运行时环境差异在此
转红。features 全开(含 server_admin_*)、access_mode=open,让各命令体尽量走深。
"""
import sys

from tests.unit._ns_loader import NS, namespaced_main


class _FakeContext:
    pass


class _FakeRestResp:
    def __init__(self, ok=True, status=200, data=None, error=None):
        self.ok = ok
        self.status = status
        self.data = data
        self.duration_ms = 0
        self.payload_bytes = 0
        self.error = error


class _FakeRest:
    async def close(self):
        pass

    async def fetch(self, endpoint):
        # AdminService.resolve_target 实时拉 /players 做名字→userid 解析;
        # 种一个在线 Alice 令 kick/ban 走到 execute_target 深分支。
        return _FakeRestResp(ok=True, data={"players": [
            {"name": "Alice", "userid": "steam_76561198000000001", "level": 1},
        ]})

    async def post(self, path, json_body):
        # 写端点:2xx 成功 stub,令 announce/save/kick/unban/ban/shutdown/stop
        # 走完 _execute→insert_audit 深分支。
        return _FakeRestResp(ok=True, status=200)


class _FakeSched:
    async def start(self):
        pass

    async def stop(self):
        pass


class _Ev:
    def __init__(self, msg: str = ""):
        self.message_str = msg

    unified_msg_origin = "test:GroupMessage:g1"
    role = "admin"

    def is_private_chat(self):
        return False

    def get_group_id(self):
        return "g1"

    def get_platform_name(self):
        return "test"

    def get_sender_id(self):
        return "u1"

    def plain_result(self, s):
        return s


def _raw_config() -> dict:
    return {
        "servers": [
            {"name": "alpha", "enabled": True, "base_url": "http://127.0.0.1:8212",
             "username": "admin", "password": "pw", "timeout": 10, "verify_tls": True,
             "timezone": ""},
        ],
        "group_bindings": [],
        "routing": {"access_mode": "open", "default_server": "alpha"},
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
        # 全组开启:关掉的组命令直接回「未开放」,不进函数体,冒烟就白跑
        "features": {"report": True, "events": True, "guilds_bases": True, "players": True,
                     "server_admin_basic": True, "server_admin_danger": True},
        # sender = get_platform_name():get_sender_id() = test:u1(见 _Ev),
        # 令 server add/remove 越过 is_admin 门,重新走进 routing.use/unbind 深分支
        "permission_admins": [{"id": "test:u1", "note": "冒烟管理员"}],
        "admin_only_commands": [],
    }


async def test_all_commands_run_under_namespaced_load(tmp_path, monkeypatch):
    with namespaced_main() as mod:
        container_mod = sys.modules[f"{NS}.palworld_terminal.container"]
        Container = container_mod.Container
        orig_init = Container.__init__

        def patched_init(self, config, data_dir, clock, **kw):
            kw.setdefault("rest_factory", lambda s, c: _FakeRest())
            kw.setdefault("scheduler_factory", lambda **k: _FakeSched())
            orig_init(self, config, data_dir, clock, **kw)

        monkeypatch.setattr(Container, "__init__", patched_init)
        monkeypatch.setattr(mod, "_resolve_data_dir", lambda: tmp_path)

        plugin = mod.PalWorldTerminal(_FakeContext(), _raw_config())
        await plugin.initialize()
        try:
            # 种入世界与玩家,让 bind/me/player 走到深分支
            # (实机 /pal me 崩溃发生在已绑定路径,浅冒烟到不了)
            models = sys.modules[f"{NS}.palworld_terminal.domain.models"]
            enums = sys.modules[f"{NS}.palworld_terminal.domain.enums"]
            repo = plugin._container.repo
            await repo.upsert_world(models.World(
                world_id="alpha:GUID:0", server_id="alpha", worldguid="GUID", epoch=0,
                server_name="alpha", version="1.0", first_seen_at=1, last_seen_at=1,
                current_day=1,
            ))
            await repo.upsert_player(models.PlayerIdentity(
                "pk1", "alpha:GUID:0", "Alice", 1, 1, 10, None,
                enums.IdConfidence.HIGH,
            ))

            calls = [
                (plugin.world, "world status"), (plugin.online, "online"),
                (plugin.world, "world overview"), (plugin.world, "world rules"),
                (plugin.world, "world today"), (plugin.world, "world events"),
                (plugin.guild, "guild list"), (plugin.guild, "guild info G"),
                (plugin.guild, "guild bases"), (plugin.guild, "guild base 1"),
                (plugin.rank, "rank"), (plugin.player, "player info Alice"),
                (plugin.player, "player bind Alice"),  # 先绑定……
                (plugin.me, "me"),                      # ……me 才会走到档案(DTO)深分支
                (plugin.player, "player unbind"),       # 绑定后解绑,走 delete_binding 深分支
                (plugin.link, "link list"), (plugin.whoami, "whoami"),
                (plugin.whereami, "whereami"), (plugin.help, "help"),
                (plugin.link, "link add alpha"), (plugin.link, "link remove alpha"),
                # 服务器管控写命令(require_confirmation 默认关 → 直执,不进 pending);
                # kick/ban 的 Alice 由 _FakeRest.fetch 种在线 → 走到 execute_target。
                (plugin.server, "server announce 服务器 5 分钟后维护"),
                (plugin.server, "server save"),
                (plugin.server, "server kick Alice 违规"),
                (plugin.server, "server unban steam_76561198000000002"),
                (plugin.server, "server ban Alice 破坏据点"),
                (plugin.server, "server shutdown 60 例行维护"),
                (plugin.server, "server stop"),
                (plugin.confirm, "confirm"),  # 无 pending → admin_no_pending(仍回文本)
            ]
            for handler, msg in calls:
                outputs = [out async for out in handler(_Ev(msg))]
                assert outputs, f"{handler.__name__} 无输出"
                assert all(isinstance(o, str) and o for o in outputs), (
                    f"{handler.__name__} 输出非文本: {outputs!r}"
                )
        finally:
            await plugin.terminate()
