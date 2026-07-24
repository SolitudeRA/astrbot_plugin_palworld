import inspect
import pathlib

from palworld_terminal.adapters.sqlite_repository import Repository

ADAPTERS_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "palworld_terminal" / "adapters"
)

# §4 全表 59 方法完整清单（唯一真相源；含单下划线 _row_to_session）
EXPECTED_METHODS = {
    # routing (12)
    "sync_servers", "seed_bindings", "cleanup_orphan_bindings",
    "list_allowed_bindings", "list_orphan_server_ids", "bind_umos_to_server",
    "clear_all_group_servers", "get_binding_active", "get_allowed",
    "list_group_servers", "set_active", "revoke",
    # player_binding (6)
    "upsert_binding", "get_binding", "set_hidden", "unset_hidden",
    "delete_binding", "get_hidden_keys",
    # world (8)
    "upsert_world", "get_current_world", "list_worlds_with_open_sessions",
    "insert_metric", "latest_metric", "world_day_bounds", "peak_online",
    "upsert_unknown_classes",
    # player_profile (14)
    "upsert_player", "get_player", "get_player_by_name", "list_players_by_name",
    "list_players_by_level", "_row_to_session", "insert_session",
    "update_session", "get_open_session", "list_open_sessions",
    "sessions_in_day", "total_durations", "insert_observation",
    "latest_observation",
    # guild_base (8)
    "upsert_guild", "list_guilds", "upsert_palbox", "list_palboxes",
    "upsert_base", "list_bases", "insert_base_observation",
    "latest_base_observation",
    # event (4)
    "insert_event", "list_events", "upsert_daily_aggregate",
    "get_daily_aggregate",
    # audit (3)
    "insert_audit", "list_audit", "prune_audit",
    # dex (2)
    "upsert_observed_species", "observed_species",
    # 主体跨表 (2)
    "purge_server_data", "prune",
}


def test_repository_exposes_exactly_59_methods():
    # 类级内省：实例属性 _db/_clock/_PURGE_WORLD_TABLES 不在其中；
    # staticmethod _row_to_session 是 isfunction → 正确纳入。不可用 startswith("_") 过滤。
    actual = {
        n for n, _ in inspect.getmembers(Repository, inspect.isfunction)
        if not n.startswith("__")
    }
    assert actual == EXPECTED_METHODS
    assert len(EXPECTED_METHODS) == 59


def test_mixins_do_not_import_each_other():
    for py in sorted(ADAPTERS_DIR.glob("repo_*.py")):  # 天然排除 sqlite_repository.py
        src = py.read_text(encoding="utf-8")
        assert "from .repo_" not in src, f"{py.name} 跨 mixin import"
        assert "import palworld_terminal.adapters.repo_" not in src, f"{py.name} 跨 mixin import"


def test_repository_satisfies_all_port_methods():
    # 硬编码各端口方法名（不 introspect Protocol 私有 API）。端口分组 ≠ mixin 分组：
    # 如 AuditPort.get_current_world 落 _WorldMetricRepo、insert_audit 落 _AuditRepo，
    # 两者经继承都在 Repository 上。
    port_methods = {
        # ReadRepositoryPort (18)
        "get_hidden_keys", "get_open_session", "get_player", "get_player_by_name",
        "latest_base_observation", "latest_metric", "latest_observation",
        "list_bases", "list_events", "list_guilds", "list_open_sessions",
        "list_players_by_level", "list_players_by_name", "observed_species",
        "peak_online", "sessions_in_day", "total_durations", "world_day_bounds",
        # WriteRepositoryPort (3) — peak_online 与 Read 重合
        "insert_event", "upsert_observed_species",
        # RoutingRepositoryPort (5)
        "get_allowed", "get_binding_active", "list_group_servers", "revoke",
        "set_active",
        # AuditRepositoryPort (2)
        "get_current_world", "insert_audit",
    }
    for m in port_methods:
        assert hasattr(Repository, m), f"Repository 缺端口方法 {m}"
