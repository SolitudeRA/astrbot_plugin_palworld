"""命名空间加载下的全命令运行时冒烟。

背景:astrbot_namespace_load_test 只覆盖模块导入;函数体内的惰性问题
(如曾在实机炸掉 /pal me 的函数内绝对自导入)导入时不触发。本测试在
同等命名空间条件下真正 initialize 插件、种入世界与玩家数据,把全部
17 条命令带参数走一遍(server 走裸/add/remove 三种参数,calls 共 19 项;
bind 成功后再走 unbind/me,复现当年实机 bug 的等价深分支)——任何仅在真实
AstrBot 加载形态下才暴露的运行时环境差异
在此转红。features 全开、access_mode=open,让各命令体尽量走深。
"""
import sys

from tests.unit._ns_loader import NS, namespaced_main


class _FakeContext:
    pass


class _FakeRest:
    async def close(self):
        pass


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
        "features": {"report": True, "events": True, "guilds_bases": True, "players": True},
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
                (plugin.status, ""), (plugin.online, ""), (plugin.world, ""),
                (plugin.rules, ""), (plugin.today, ""), (plugin.events, ""),
                (plugin.guilds, ""), (plugin.guild, "guild G"),
                (plugin.bases, ""), (plugin.base, "base 1"),
                (plugin.rank, ""), (plugin.player, "player Alice"),
                (plugin.bind, "bind Alice"),  # 先绑定……
                (plugin.me, "me"),            # ……me 才会走到档案(DTO)深分支
                (plugin.unbind, "unbind"),    # 绑定后解绑,走 delete_binding 深分支
                (plugin.server, "server"), (plugin.help, ""),
                (plugin.server, "server add alpha"), (plugin.server, "server remove alpha"),
            ]
            for handler, msg in calls:
                outputs = [out async for out in handler(_Ev(msg))]
                assert outputs, f"{handler.__name__} 无输出"
                assert all(isinstance(o, str) and o for o in outputs), (
                    f"{handler.__name__} 输出非文本: {outputs!r}"
                )
        finally:
            await plugin.terminate()
