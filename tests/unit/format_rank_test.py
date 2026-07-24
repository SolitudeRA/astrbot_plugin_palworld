from palworld_terminal.application.dtos import RankClimbDTO, RankClimbEntry
from palworld_terminal.application.query_service import RankBoardsDTO
from palworld_terminal.presentation.formatters import format_rank, format_rank_climb


def _dto():
    return RankBoardsDTO(
        time_rows=[("Alice", 4200), ("Bob", 1800)],
        level_rows=[("Bob", 30), ("Alice", 25)],
        total_rows=[("Alice", 75900), ("Bob", 3900)],
    )


def test_today_board_title_anchor_and_ranks():
    # spec §4.23：标题锚点 `🏆 今日在线时长榜 · {srv}`；名次序号纯渲染；时长走 fmt_duration。
    out = format_rank(_dto(), which="today", server_name="Palpagos")
    assert out.splitlines()[0] == "🏆 今日在线时长榜 · Palpagos"
    assert "1. Alice 1时10分" in out and "2. Bob 30分" in out
    assert "等级榜" not in out


def test_time_alias_renders_today_board():
    out = format_rank(_dto(), which="time", server_name="Palpagos")
    assert out.splitlines()[0] == "🏆 今日在线时长榜 · Palpagos"


def test_level_board_title_and_rows():
    # spec §4.23 level 变体：`🏆 等级榜 · {srv}`，行 `1. Morpheus Lv30`。
    out = format_rank(_dto(), which="level", server_name="Palpagos")
    assert out.splitlines()[0] == "🏆 等级榜 · Palpagos"
    assert "1. Bob Lv30" in out and "2. Alice Lv25" in out


def test_total_board_title_and_footnote():
    # spec §4.23 total 变体：`🏆 累计在线时长榜 · {srv}` + 脚注 `└ 统计范围为数据留存期`。
    out = format_rank(_dto(), which="total", server_name="Palpagos")
    assert out.splitlines()[0] == "🏆 累计在线时长榜 · Palpagos"
    assert "1. Alice 21时05分" in out
    assert out.splitlines()[-1] == "└ 统计范围为数据留存期"


def test_empty_board_plain_state():
    # spec §4.23 空榜：标题锚点 + 素文「暂无排行数据」（无脚注）。
    out = format_rank(RankBoardsDTO([], []), which="today", server_name="Palpagos")
    assert out == "🏆 今日在线时长榜 · Palpagos\n暂无排行数据"


def test_empty_total_board_no_footnote():
    out = format_rank(RankBoardsDTO([], []), which="total", server_name="Palpagos")
    assert out == "🏆 累计在线时长榜 · Palpagos\n暂无排行数据"


# ---- climb 飞升榜（spec §7）----

def _climb(**kw):
    kw.setdefault("rows", [RankClimbEntry("Alice", 15), RankClimbEntry("Bob", 8)])
    kw.setdefault("shallow", False)
    return RankClimbDTO(**kw)


def test_climb_board_title_rows_and_scope():
    out = format_rank_climb(_climb(), server_name="Palpagos")
    assert out.splitlines()[0] == "🚀 飞升榜 · Palpagos"
    assert "1. Alice +15 级" in out and "2. Bob +8 级" in out
    assert "近 7 天" in out


def test_climb_shallow_scope_wording():
    out = format_rank_climb(_climb(rows=[RankClimbEntry("Eve", 7)], shallow=True),
                            server_name="P")
    assert "记录以来" in out and "近 7 天" not in out


def test_climb_viewer_footer_with_gap():
    out = format_rank_climb(_climb(viewer_rank=2, viewer_gain=8, viewer_gap=7),
                            server_name="P")
    assert "你第 2" in out and "差 7" in out


def test_climb_viewer_footer_top_no_gap():
    out = format_rank_climb(_climb(viewer_rank=1, viewer_gain=15, viewer_gap=None),
                            server_name="P")
    assert "你第 1" in out and "差" not in out.splitlines()[-1]


def test_climb_empty_board():
    out = format_rank_climb(_climb(rows=[]), server_name="P")
    assert out.splitlines()[0] == "🚀 飞升榜 · P"
    assert "你第" not in out and "近 7 天" not in out
