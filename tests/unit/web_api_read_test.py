"""config/get 与 status/overview 编排：脱敏下发、重启窗口、按服务器组装。"""
from palworld_terminal.presentation.dtos import StatusDTO
from palworld_terminal.presentation.web_api import handle_config_get, handle_status_overview


async def test_config_get_returns_redacted():
    raw = {"servers": [{"name": "a", "password": "secret", "password_env": "",
                        "base_url": "http://h", "username": "admin"}]}
    code, payload = await handle_config_get(lambda: raw)
    assert code == 200 and payload["ok"] is True
    import json
    assert "secret" not in json.dumps(payload)
    assert payload["config"]["servers"][0]["__row_id"] == "srv-0"
    assert payload["page_version"] == 1


class _Server:
    def __init__(self, name):
        self.name = name
        self.server_id = name
        self.ready = True


class _Repo:
    def __init__(self, worlds):
        self._worlds = worlds

    async def get_current_world(self, sid):
        return self._worlds.get(sid)


class _Query:
    def __init__(self, dto):
        self._dto = dto

    async def status(self, world):
        return self._dto


class _Cfg:
    def __init__(self, servers):
        self.servers = servers


class _Container:
    def __init__(self, servers, worlds, dto):
        self.config = _Cfg(servers)
        self.repo = _Repo(worlds)
        self.query = _Query(dto)


def _dto():
    return StatusDTO(server_name="a", world_name="a", world_day=1, online=4,
                     max_players=32, basecamp_count=0, fps=55.0, frame_time=18.0,
                     smoothness_label="流畅", players=[], peak_online_today=4,
                     updated_at=1, degraded=False, last_ok=9)


async def test_status_overview_restarting_returns_empty():
    code, payload = await handle_status_overview(None, restarting=True)
    assert code == 200 and payload["restarting"] is True and payload["servers"] == []


async def test_status_overview_none_container():
    code, payload = await handle_status_overview(None, restarting=False)
    assert payload["restarting"] is True and payload["servers"] == []


async def test_status_overview_assembles_rows():
    c = _Container([_Server("a")], {"a": object()}, _dto())
    code, payload = await handle_status_overview(c, restarting=False)
    assert code == 200 and payload["ok"] is True
    assert payload["servers"] == [{"name": "a", "ready": True, "online": 4,
                                   "max_players": 32, "fps": 55.0,
                                   "smoothness_label": "流畅", "world_day": 1,
                                   "peak_online_today": 4, "basecamp_count": 0,
                                   "updated_at": 1, "degraded": False,
                                   "last_ok": 9}]


async def test_status_overview_world_none_skeleton():
    c = _Container([_Server("a")], {}, _dto())  # 无 world
    code, payload = await handle_status_overview(c, restarting=False)
    # 规格 §3.3：world 为 None 时骨架行 ready=False（即便配置 s.ready 为 True）
    assert payload["servers"] == [{"name": "a", "ready": False}]
