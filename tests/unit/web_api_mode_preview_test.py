from palworld_terminal.presentation.web_api import handle_mode_transfer_preview


class _Srv:
    def __init__(self, name, ready=True):
        self.name = name
        self.server_id = name
        self.ready = ready


class _Entry:
    def __init__(self, umo, note=""):
        self.umo = umo
        self.note = note


class _Routing:
    def __init__(self, entries):
        self.single_allowed_groups = entries


class _Cfg:
    def __init__(self, servers, entries):
        self.servers = servers
        self.routing = _Routing(entries)


class _Repo:
    def __init__(self, pairs):
        self._pairs = pairs

    async def list_allowed_bindings(self):
        return self._pairs


class _Container:
    def __init__(self, servers, entries, pairs):
        self.config = _Cfg(servers, entries)
        self.repo = _Repo(pairs)


async def test_preview_restarting_empty():
    code, p = await handle_mode_transfer_preview(None, True, "single")
    assert code == 200 and p["restarting"] is True


async def test_preview_multi_to_single_aggregates_bindings():
    c = _Container([_Srv("a"), _Srv("b", ready=False)], [],
                   [("u1", "a"), ("u1", "b"), ("u2", "a")])
    code, p = await handle_mode_transfer_preview(c, False, "single")
    assert code == 200 and p["ok"] is True
    # 仅就绪台作保留台候选权威源
    assert p["ready_servers"] == [{"server_id": "a", "name": "a"}]
    agg = {b["umo"]: sorted(b["server_ids"]) for b in p["bindings"]}
    assert agg == {"u1": ["a", "b"], "u2": ["a"]}


async def test_preview_single_to_multi_returns_allowed_groups():
    c = _Container([_Srv("a")], [_Entry("u1", "note1"), _Entry("u2")], [])
    code, p = await handle_mode_transfer_preview(c, False, "multi")
    assert p["ok"] is True
    assert p["ready_servers"] == [{"server_id": "a", "name": "a"}]
    assert p["allowed_groups"] == [{"umo": "u1", "note": "note1"},
                                   {"umo": "u2", "note": ""}]


async def test_preview_invalid_target():
    c = _Container([_Srv("a")], [], [])
    code, p = await handle_mode_transfer_preview(c, False, "bogus")
    assert p["ok"] is False and p["error"] == "invalid_target"
