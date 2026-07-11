"""status/overview 行组装：实名字段 + 白名单 + world=None 骨架。"""
from palchronicle.presentation.config_view import status_rows
from palchronicle.presentation.dtos import StatusDTO


def _dto():
    return StatusDTO(
        server_name="alpha", world_name="alpha", world_day=3, online=5,
        max_players=32, basecamp_count=2, fps=55.0, frame_time=18.0,
        smoothness_label="流畅", players=[], peak_online_today=7,
        updated_at=1000, degraded=False, last_ok=999,
    )


def test_ready_server_row_whitelisted_fields():
    rows = status_rows([("alpha", True, _dto())])
    assert rows == [{
        "name": "alpha", "ready": True, "online": 5,
        "smoothness_label": "流畅", "degraded": False, "last_ok": 999,
    }]


def test_no_world_yields_skeleton():
    rows = status_rows([("beta", False, None)])
    assert rows == [{"name": "beta", "ready": False}]


def test_no_leak_of_sensitive_keys():
    rows = status_rows([("alpha", True, _dto())])
    for row in rows:
        assert not {"base_url", "password", "umo", "players"} & set(row)
