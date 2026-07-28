import pathlib

from palworld_terminal.adapters.sqlite_repository import Repository

ADAPTERS_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "palworld_terminal" / "adapters"
)

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
        # ReadRepositoryPort (19)
        "get_hidden_keys", "get_open_session", "get_player", "get_player_by_name",
        "latest_base_observation", "latest_metric", "latest_observation",
        "list_bases", "list_events", "list_guilds", "list_open_sessions",
        "list_players_by_level", "list_players_by_name", "observed_species",
        "peak_online", "sessions_in_day", "total_durations", "world_day_bounds",
        "climb_levels",
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
