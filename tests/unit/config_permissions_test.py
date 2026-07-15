from palworld_terminal.config import parse_config


def _base(**over):
    raw = {"servers": [], "routing": {}, "polling": {}, "world": {}, "bases": {},
           "privacy": {}, "history": {}, "features": {}, "players": {}}
    raw.update(over)
    return parse_config(raw, {})


def test_permission_admins_parsed_and_filtered():
    cfg = _base(permission_admins=[
        {"id": "aiocqhttp:12345", "note": "群主"},
        {"id": "", "note": "空 id 跳过"},
        {"id": "aiocqhttp:", "note": "空账号段跳过"},
        {"id": "aiocqhttp:12345", "note": "重复去掉"},
    ])
    ids = [a.id for a in cfg.permissions.admins]
    assert ids == ["aiocqhttp:12345"]
    assert cfg.permissions.admins[0].note == "群主"


def test_permissions_default_empty():
    cfg = _base()
    assert cfg.permissions.admins == []
    assert cfg.permissions.command_overrides == {}


def test_single_allowed_groups_parsed_and_deduped():
    raw = {"single_allowed_groups": [
        {"umo": "aiocqhttp:GroupMessage:1", "note": "主群"},
        {"umo": "  aiocqhttp:GroupMessage:2  ", "note": ""},
        {"umo": "aiocqhttp:GroupMessage:1", "note": "重复"},  # 去重
        {"umo": "", "note": "空"},                              # 去空
    ]}
    cfg = parse_config(raw, {})
    umos = [e.umo for e in cfg.routing.single_allowed_groups]
    assert umos == ["aiocqhttp:GroupMessage:1", "aiocqhttp:GroupMessage:2"]


def test_single_allowed_groups_default_empty():
    cfg = parse_config({}, {})
    assert cfg.routing.single_allowed_groups == []
