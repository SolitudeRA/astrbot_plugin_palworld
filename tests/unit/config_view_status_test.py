"""status/overview 行组装：实名字段 + 白名单 + world=None 骨架 + detail 详细区。"""
from palworld_terminal.application.dtos import StatusDetailDTO, StatusDTO
from palworld_terminal.presentation.config_view import status_rows


def _dto(degraded=False, detail=None):
    return StatusDTO(
        server_name="alpha", world_name="alpha", world_day=3, online=5,
        max_players=32, basecamp_count=2, fps=55.0, frame_time=18.0,
        smoothness_label="流畅", players=[], peak_online_today=7,
        updated_at=1000, degraded=degraded, last_ok=999, detail=detail,
    )


def _detail():
    return StatusDetailDTO(
        version="v1.2.3", description="desc", uptime_seconds=100, frametime_ms=16.9,
        address="http://h:8212",
        rules={"difficulty": "普通", "pvp": "关闭",
               "death_penalty": "掉落物品", "exp_rate": "1.0×"},
    )


def test_ready_server_row_whitelisted_fields():
    rows = status_rows([("alpha", True, _dto())])
    assert rows == [{
        "name": "alpha", "ready": True, "online": 5, "max_players": 32,
        "fps": 55.0, "smoothness_label": "流畅", "world_day": 3,
        "peak_online_today": 7, "basecamp_count": 2, "updated_at": 1000,
        "degraded": False, "last_ok": 999,
    }]


def test_no_world_yields_skeleton():
    rows = status_rows([("beta", False, None)])
    assert rows == [{"name": "beta", "ready": False}]


def test_no_leak_of_sensitive_keys():
    rows = status_rows([("alpha", True, _dto())])
    for row in rows:
        assert not {"base_url", "password", "umo", "players"} & set(row)


def test_ready_nondegraded_emits_detail():
    rows = status_rows([("alpha", True, _dto(detail=_detail()))])
    assert rows[0]["detail"] == {
        "version": "v1.2.3", "description": "desc", "uptime_seconds": 100,
        "frametime_ms": 16.9, "address": "http://h:8212",
        "rules": {"difficulty": "普通", "pvp": "关闭",
                  "death_penalty": "掉落物品", "exp_rate": "1.0×"},
    }


def test_detail_absent_when_dto_has_no_detail():
    # 装配层未产出 detail（如 meta 缺失）：行不带 detail 键，前端静默容忍
    rows = status_rows([("alpha", True, _dto(detail=None))])
    assert "detail" not in rows[0]


def test_degraded_row_never_carries_detail():
    # degraded 行即便 dto.detail 有值也不下发（白名单只给可信实时数据）
    rows = status_rows([("alpha", True, _dto(degraded=True, detail=_detail()))])
    assert "detail" not in rows[0]


def test_not_ready_row_never_carries_detail():
    rows = status_rows([("alpha", False, _dto(detail=_detail()))])
    assert "detail" not in rows[0]
