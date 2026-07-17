import re

from palworld_terminal.presentation.formatters import format_status
from tests.fixtures.loader import load_fixture
from tests.integration.conftest import ok

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


async def test_smoke_status_after_one_collection(harness):
    container, server, clock, snap = harness

    # 对 mock 服务器跑一轮完整采集
    world = await snap.ingest_info(server, ok(load_fixture("normal_world", "info")))
    await snap.ingest_metrics(world, ok(load_fixture("normal_world", "metrics")))
    await snap.ingest_players(world, ok(load_fixture("normal_world", "players")))
    await snap.ingest_game_data(world, ok(load_fixture("normal_world", "game-data")))

    dto = await container.query.status(world)
    # server_name = 配置名（spec §2.1 锚点供数；直调 formatter 用 dto.server_name 替 commands 层供数）
    text = format_status(dto, dto.server_name)

    # 合理文本（新式样 spec §4.1）：标题锚点、天数 42、在线 2/32、官方据点数 3（metrics.basecampnum）
    assert "🌍 世界状态" in text
    assert "42" in text            # 世界天数
    assert "2" in text and "32" in text  # 在线 N/M（分子=收敛后名单数）
    assert "3" in text             # 官方 basecampnum（show_bases 默认 True）

    # 隐私：status 文本绝不含原始 ID / IP / 明文密码
    assert not IPV4.search(text)
    for leak in ("steam_00001", "steam_00002", "acct_akari", "PID-1", "pw"):
        assert leak not in text
