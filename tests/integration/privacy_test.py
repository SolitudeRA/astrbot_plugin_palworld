import logging
import re

from palchronicle.adapters.palworld_rest import RestResponse
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


async def test_strict_mode_persists_no_bases_no_palboxes(harness_strict):
    container, server, clock, snap = harness_strict
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    # 即便 game-data 含 PalBox 与据点帕鲁，strict 下也连续多帧不落 base/palbox
    for _ in range(4):
        clock.advance(30)
        await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))

    assert await container.repo.list_palboxes(world.world_id) == []
    assert await container.repo.list_bases(world.world_id, include_low=True, include_hidden=True) == []
    baseobs = await container.db.query("SELECT COUNT(*) AS c FROM base_observations")
    assert baseobs[0]["c"] == 0


async def test_strict_mode_position_cell_all_null(harness_strict):
    container, server, clock, snap = harness_strict
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))
    clock.advance(30)
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))

    rows = await container.db.query("SELECT position_cell FROM player_observations")
    assert rows, "应有观察记录"
    assert all(r["position_cell"] is None for r in rows)


async def test_logs_never_leak_raw_on_degradation_paths(harness, caplog):
    container, server, clock, snap = harness
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))

    with caplog.at_level(logging.DEBUG, logger="palchronicle"):
        # 401 认证失败路径（error 内绝不含凭证/URL 明文）
        await snap.ingest_players(world, RestResponse(
            ok=False, status=401, data=None, duration_ms=3, payload_bytes=0, error="auth failed"))
        # 端点失败 → uncertain 降级路径
        await snap.ingest_players(world, RestResponse(
            ok=False, status=None, data=None, duration_ms=3, payload_bytes=0, error="timeout"))
        # 数据不一致：metrics 人数 5，但 players 明细 2 → 记诊断日志（spec §14），仍不泄原文
        m = {**load_fixture("normal_world", "metrics"), "currentplayernum": 5}
        await snap.ingest_metrics(world, ok(m))
        await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
        # game-data 含坐标/原始 userid 的原文，触发正常处理路径的日志
        await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert caplog.records, "降级/诊断路径应产出日志"
    assert not IPV4.search(text), "日志泄露 IPv4"
    assert not IPV6.search(text), "日志泄露 IPv6"
    for rid in RAW_IDS:
        assert rid not in text, f"日志泄露原始 ID {rid}"
    for coord in ("100.0", "200.0", "3000.0", "3200.0"):
        assert coord not in text, f"日志泄露坐标 {coord}"
    assert "Basic " not in text and "Authorization" not in text
    assert "pw" not in text.split()  # 明文密码不出现为独立 token
