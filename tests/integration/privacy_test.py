import re

from tests.fixtures.loader import load_fixture
from tests.integration.conftest import ok

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b")
RAW_IDS = ("steam_00001", "steam_00002", "PID-1", "PID-2", "acct_akari", "acct_borel")
RAW_PING_CELLS = {"44", "130", "44.0", "130.0"}
RAW_PLAYER_IPS = ("10.0.0.11", "10.0.0.12")

# 仅 IPv4/IPv6 正则扫描排除以下列（其余断言仍全表全列扫描）：
# - servers.host 是运营者配置的 REST 端点(规格允许持久化), 非玩家数据; 其余列照扫
# - position_cell / palbox_key 存 privacy_filter.quantize_cell 的粗化网格键 "x:y:z"
#   （及内嵌该键的复合键），十进制冒号分隔结构性误触 IPv6 正则；非 IP 数据
_IP_SCAN_EXCLUDE = {
    "servers": {"host"},
    "player_observations": {"position_cell"},
    "palboxes": {"position_cell", "palbox_key"},
    "bases": {"palbox_key"},
}


async def _all_table_names(container):
    rows = await container.db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return [r[0] for r in rows]


async def _dump_all_cells(container, exclude=None) -> list[str]:
    exclude = exclude or {}
    cells: list[str] = []
    for table in await _all_table_names(container):
        excluded = exclude.get(table, set())
        rows = await container.db.query(f"SELECT * FROM {table}")
        for row in rows:
            for col in row.keys():
                if col in excluded:
                    continue
                value = row[col]
                if value is not None:
                    cells.append(str(value))
    return cells


async def _run_normal_sequence(container, server, clock, snap):
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    await snap.ingest_metrics(world, ok(load_fixture("normal_world", "metrics")))
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))
    clock.advance(30)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))
    return world


async def test_db_has_no_ip_no_raw_id_no_password_no_raw_ping(harness):
    container, server, clock, snap = harness
    await _run_normal_sequence(container, server, clock, snap)

    cells = await _dump_all_cells(container)
    blob = "\n".join(cells)

    # 玩家 IP 红线：全表全列（不受任何排除影响），玩家侧原始 IP 绝不允许出现
    for raw_ip in RAW_PLAYER_IPS:
        assert raw_ip not in blob, f"DB 含玩家 IP {raw_ip}"

    # 通用 IP 正则兜底扫描：排除运营者端点与网格键列（见 _IP_SCAN_EXCLUDE 注释）
    ip_blob = "\n".join(await _dump_all_cells(container, exclude=_IP_SCAN_EXCLUDE))
    assert not IPV4.search(ip_blob), "DB 含 IPv4"
    assert not IPV6.search(ip_blob), "DB 含 IPv6"

    for rid in RAW_IDS:
        assert rid not in blob, f"DB 含原始 ID {rid}"
    assert "pw" not in set(cells), "DB 含明文密码"

    # ping 仅以 bucket 存在，无原始 ping 数值列
    obs_cols = await container.db.query("SELECT * FROM player_observations LIMIT 1")
    col_names = obs_cols[0].keys() if obs_cols else []
    assert "ping_bucket" in col_names
    assert "ping" not in col_names
    # 单元格精确匹配：避免 HMAC 十六进制串误伤子串扫描（controller 裁定 1）
    assert not any(c in RAW_PING_CELLS for c in cells), "DB 含原始 ping 值"
