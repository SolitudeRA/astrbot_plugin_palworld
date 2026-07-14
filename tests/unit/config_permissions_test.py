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


def test_admin_only_commands_normalized():
    cfg = _base(admin_only_commands=[
        "player info", " rank ", "player info", "server kick", "whoami", "help", 123])
    # 去空白/去重/剔除不可锁集(完整路径 server kick/whoami/help)/丢非 str
    assert sorted(cfg.permissions.admin_only_commands) == ["player info", "rank"]


def test_admin_only_commands_non_list_degrades_empty():
    cfg = _base(admin_only_commands="oops")
    assert cfg.permissions.admin_only_commands == []


def test_permissions_default_empty():
    cfg = _base()
    assert cfg.permissions.admins == []
    assert cfg.permissions.admin_only_commands == []
