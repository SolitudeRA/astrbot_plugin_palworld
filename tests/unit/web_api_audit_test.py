"""audit/list 编排 + audit_rows DTO 整形：倒序限量、None→空、脱敏 target。"""
import json

from palworld_terminal.presentation.config_view import audit_rows
from palworld_terminal.presentation.web_api import handle_audit_list


class _Repo:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[int] = []

    async def list_audit(self, limit):
        # 仓库真实语义：已按 ts DESC 排好，仅取前 limit 条。
        self.calls.append(limit)
        return self._rows[:limit]


class _Container:
    def __init__(self, rows):
        self.repo = _Repo(rows)


def _row(ts, **kw):
    base = {"ts": ts, "admin_id": "qq:1", "action": "kick", "server_name": "alpha",
            "target_name": "Alice", "target_hash": "a" * 58 + "bcdef1",
            "detail": "", "success": 1, "error": None}
    base.update(kw)
    return base


# ---- handle_audit_list 编排 ----
async def test_none_container_returns_empty_restarting():
    code, payload = await handle_audit_list(None, 100)
    assert code == 200
    assert payload == {"ok": True, "audits": [], "restarting": True}


async def test_returns_rows_desc_limited():
    rows = [_row(300, action="stop"), _row(200), _row(100)]
    c = _Container(rows)
    code, payload = await handle_audit_list(c, 2)
    assert code == 200 and payload["ok"] is True
    assert c.repo.calls == [2]                          # limit 透传给仓库
    audits = payload["audits"]
    assert [a["ts"] for a in audits] == [300, 200]      # 倒序，限 2
    assert audits[0]["action"] == "stop"


# ---- audit_rows DTO 整形 ----
def test_audit_rows_shaping():
    rows = [_row(1_700_000_000, success=0, error="server_offline",
                 target_hash="0" * 58 + "abcdef")]
    out = audit_rows(rows)
    assert len(out) == 1
    a = out[0]
    assert a["ts"] == 1_700_000_000                     # 原始 epoch 透传（可排序）
    assert isinstance(a["time"], str) and a["time"]     # ts→可读
    assert a["success"] is False                        # success→bool
    assert a["action"] == "kick" and a["server"] == "alpha"
    assert a["admin"] == "qq:1"                         # 管理员透传
    assert a["error"] == "server_offline"               # 错误类别透传
    # target 组合：角色名 + hash 尾段辅助去歧义
    assert a["target"].startswith("Alice")
    assert "abcdef" in a["target"]                      # 仅尾段
    assert ("0" * 58) not in a["target"]                # 不泄漏完整 hash


def test_audit_rows_target_variants():
    # 仅 hash（如 unban by userid，无角色名）
    only_hash = audit_rows([_row(1, target_name=None,
                                 target_hash="x" * 58 + "778899")])[0]["target"]
    assert only_hash and "778899" in only_hash and "x" * 58 not in only_hash
    # 无目标（announce/save/shutdown/stop）
    no_target = audit_rows([_row(1, target_name=None, target_hash=None)])[0]["target"]
    assert no_target == ""


def test_audit_rows_no_full_hash_leak():
    full = "d" * 64
    out = audit_rows([_row(1, target_name="Bob", target_hash=full)])
    blob = json.dumps(out)
    assert full not in blob                             # 完整 hash 绝不出现
    assert out[0]["target"].startswith("Bob")


def test_audit_rows_empty():
    assert audit_rows([]) == []
