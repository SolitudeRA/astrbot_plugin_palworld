from palchronicle.application.query_service import RankBoardsDTO
from palchronicle.presentation.formatters import format_rank


def _dto():
    return RankBoardsDTO(time_rows=[("Alice", 4200), ("Bob", 1800)],
                         level_rows=[("Bob", 30), ("Alice", 25)])


def test_format_both_boards():
    out = format_rank(_dto(), which="both", strict=False)
    assert "今日在线时长榜" in out and "· Alice 1小时10分" in out
    assert "等级榜" in out and "· Bob Lv30" in out


def test_format_time_only():
    out = format_rank(_dto(), which="time", strict=False)
    assert "今日在线时长榜" in out and "等级榜" not in out


def test_strict_hides_time_board():
    out = format_rank(_dto(), which="both", strict=True)
    assert "今日在线时长榜" not in out and "等级榜" in out


def test_empty_boards_message():
    out = format_rank(RankBoardsDTO([], []), which="both", strict=False)
    assert out == "本服务器暂无玩家排行数据。"
