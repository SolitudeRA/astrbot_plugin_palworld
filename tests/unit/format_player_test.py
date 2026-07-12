from palchronicle.application.query_service import PlayerProfileDTO
from palchronicle.presentation.formatters import format_player


def test_online_shows_level_status_duration():
    out = format_player(PlayerProfileDTO("Alice", 12, True, 3600), strict=False)
    assert "Alice" in out and "Lv12" in out and "在线" in out and "1小时0分" in out


def test_offline_hides_duration():
    out = format_player(PlayerProfileDTO("Alice", 12, False, 0), strict=False)
    assert "离线" in out and "小时" not in out and "分" not in out


def test_strict_hides_duration_even_online():
    out = format_player(PlayerProfileDTO("Alice", 12, True, 3600), strict=True)
    assert "Lv12" in out and "在线" in out and "小时" not in out
