"""插件页面 HTTP 端点的 async 编排：副作用（save/stop/start/锁）经参数注入，
返回 (status_code, payload)。业务成败一律 HTTP 200，用 payload['ok'] 区分。"""
from __future__ import annotations

import copy
import json
import logging
from collections.abc import Callable, Mapping

from .config_view import _MAX_LIST, audit_rows, redact_config, status_rows, validate_and_backfill

_log = logging.getLogger("palworld_terminal.web_api")
_TRANSFER_ACTION = "mode_transfer"


async def handle_config_get(get_raw: Callable[[], Mapping]) -> tuple[int, dict]:
    return 200, {"ok": True, "config": redact_config(get_raw()), "page_version": 1}


async def handle_status_overview(container, restarting: bool) -> tuple[int, dict]:
    if restarting or container is None:
        return 200, {"ok": True, "servers": [], "restarting": True}
    entries = []
    for s in container.config.servers:
        world = await container.repo.get_current_world(s.server_id)
        dto = await container.query.status(world) if world is not None else None
        # world 为 None（未 ready / 从未成功轮询）→ 骨架行 ready=False（规格 §3.3），
        # 避免前端对 ready=True 但无 dto 的行渲染出 "在线 undefined"
        ready = s.ready if dto is not None else False
        entries.append((s.name, ready, dto))
    return 200, {"ok": True, "servers": status_rows(entries)}


async def handle_audit_list(container, limit: int) -> tuple[int, dict]:
    # 只读范式（照 handle_status_overview）：重载窗口下 main 传 container=None，
    # 与真 None 一并折叠为 restarting，客户端拿空列表而非陈旧/半态数据。
    if container is None:
        return 200, {"ok": True, "audits": [], "restarting": True}
    rows = await container.repo.list_audit(limit)  # 仓库已 ts DESC + LIMIT
    return 200, {"ok": True, "audits": audit_rows(rows)}


async def handle_config_save(
    body, *, old_raw, env, lock, now, last_save_ts,
    apply_and_restart, min_interval: float = 5,
) -> tuple[int, dict]:
    if lock.locked():
        return 200, {"ok": False, "error": "save_in_progress", "detail": {}}
    if last_save_ts is not None and now - last_save_ts < min_interval:
        return 200, {"ok": False, "error": "too_frequent", "detail": {}}
    async with lock:
        ok, result = validate_and_backfill(body, old_raw, env)
        if not ok:
            return 200, {"ok": False, **result}
        outcome = await apply_and_restart(result)
        if not outcome.get("ok"):
            return 200, outcome
        # 回传落库后的脱敏配置:前端用它刷新 state——新行拿到服务端
        # __row_id 与 password_set,否则该行再次编辑时留空密码会被当
        # 「新行空密码」提交,静默清掉已存密码(审查 F1)
        return 200, {"ok": True, "warnings": outcome.get("warnings", {}),
                     "config": redact_config(old_raw), "saved_ts": now}


async def handle_mode_transfer_preview(container, restarting, target) -> tuple[int, dict]:
    """转移前只读预览：回传服务端权威源（不信客户端凭空构造）。"""
    if restarting or container is None:
        return 200, {"ok": True, "restarting": True}
    ready = [{"server_id": s.server_id, "name": s.name}
             for s in container.config.servers if s.ready]
    if target == "single":
        pairs = await container.repo.list_allowed_bindings()
        agg: dict[str, list[str]] = {}
        for umo, sid in pairs:
            agg.setdefault(umo, []).append(sid)
        bindings = [{"umo": umo, "server_ids": sids} for umo, sids in agg.items()]
        return 200, {"ok": True, "ready_servers": ready, "bindings": bindings}
    if target == "multi":
        allowed_groups = [{"umo": e.umo, "note": e.note}
                          for e in container.config.routing.single_allowed_groups]
        return 200, {"ok": True, "ready_servers": ready, "allowed_groups": allowed_groups}
    return 200, {"ok": False, "error": "invalid_target", "detail": {}}


async def handle_mode_transfer(
    body,
    *,
    get_raw,
    get_container,
    busy_msg,
    lock,
    now,
    apply_and_restart,
    current_username,
) -> tuple[int, dict]:
    """single↔multi 原子转移编排：全程持 lock、迁移读先于 reload、
    single→multi 目标预绑先于清源、reload 失败即中止、post-reload move 清源、
    最外层审计（写异常独立隔离）。业务成败恒 200。"""
    # ---- 步0：入口串行门（transfer_in_progress / busy / no_change 三类早退不审计）----
    if lock.locked():
        return 200, {"ok": False, "error": "transfer_in_progress", "detail": {}}
    async with lock:
        if busy_msg() is not None:
            return 200, {"ok": False, "error": "busy", "detail": {}}
        container = get_container()
        if container is None:
            return 200, {"ok": False, "error": "busy", "detail": {}}

        # ---- 步1：载荷 + 当前模式 ----
        target_mode = body.get("target_mode") if isinstance(body, Mapping) else None
        if target_mode not in ("single", "multi"):
            return 200, {"ok": False, "error": "invalid_target", "detail": {}}
        current_mode = container.config.routing.world_mode
        if target_mode == current_mode:
            return 200, {"ok": False, "error": "no_change", "detail": {}}

        migrate_raw = body.get("migrate_umos") if isinstance(body, Mapping) else None
        migrate_umos = [str(u) for u in migrate_raw] if isinstance(migrate_raw, list) else []
        surviving_server_id = (body.get("surviving_server_id")
                               if isinstance(body, Mapping) else None)

        # ---- 审计累加状态（步7 最外层写一条）----
        state: dict = {
            "from": current_mode, "to": target_mode,
            "surviving": surviving_server_id, "migrated": 0,
            "purged": {}, "failed_server_ids": [],
            "cleared_group_servers": None, "cleared_single_allowed": None,
        }
        server_name_hint = _TRANSFER_ACTION
        target_server_id: str | None = None

        async def _finalize(payload, *, success, error, server_name):
            # 审计写异常隔离（M-e）：独立 try/except 吞异常、绝不改动已算好的 200 回执
            try:
                c = get_container()
                if c is not None:
                    await c.repo.insert_audit(
                        ts=now, admin_id=str(current_username() or ""),
                        action=_TRANSFER_ACTION,
                        server_name=server_name or _TRANSFER_ACTION,
                        target_name=None, target_hash=None,
                        detail=json.dumps(state, ensure_ascii=False),
                        success=success, error=error,
                    )
            except Exception:  # noqa: BLE001
                _log.warning("mode_transfer 审计写入失败（已忽略）")
            return 200, payload

        # ---- 步2/3：校验 + 迁移读 + 目标预绑（全部先于 reload）----
        if target_mode == "single":
            ready = container.routing._ready_servers()
            if not ready:
                return await _finalize(
                    {"ok": False, "error": "no_ready_server", "detail": {}},
                    success=0, error="no_ready_server", server_name=server_name_hint)
            survivor = container.routing._ready_by_name(str(surviving_server_id or ""))
            if survivor is None:
                return await _finalize(
                    {"ok": False, "error": "invalid_surviving", "detail": {}},
                    success=0, error="invalid_surviving", server_name=server_name_hint)
            server_name_hint = survivor.name
            pairs = await container.repo.list_allowed_bindings()
            source_umos = {umo for umo, _ in pairs}
            if not set(migrate_umos).issubset(source_umos):
                return await _finalize(
                    {"ok": False, "error": "invalid_migrate_umos", "detail": {}},
                    success=0, error="invalid_migrate_umos", server_name=server_name_hint)
        else:  # single → multi
            source_umos = {e.umo for e in container.config.routing.single_allowed_groups}
            if not set(migrate_umos).issubset(source_umos):
                return await _finalize(
                    {"ok": False, "error": "invalid_migrate_umos", "detail": {}},
                    success=0, error="invalid_migrate_umos", server_name=server_name_hint)
            if migrate_umos:
                ready = container.routing._ready_servers()
                if not ready:
                    return await _finalize(
                        {"ok": False, "error": "no_ready_target", "detail": {}},
                        success=0, error="no_ready_target", server_name=server_name_hint)
                target_server_id = ready[0].server_id
                server_name_hint = ready[0].name
                try:  # reload 前用旧容器预绑（目标先于清源，M-a）
                    await container.repo.bind_umos_to_server(migrate_umos, target_server_id)
                except Exception:  # noqa: BLE001
                    for umo in migrate_umos:
                        try:
                            await container.repo.revoke(umo, target_server_id)
                        except Exception:  # noqa: BLE001
                            pass
                    return await _finalize(
                        {"ok": False, "error": "migrate_bind_failed", "detail": {}},
                        success=0, error="migrate_bind_failed", server_name=server_name_hint)

        # ---- 步4：候选构造（深拷贝完整 raw 原地改，绝不预改 self._raw_config）----
        candidate = copy.deepcopy(dict(get_raw()))
        routing_node = candidate.setdefault("routing", {})
        if not isinstance(routing_node, dict):
            routing_node = {}
            candidate["routing"] = routing_node
        routing_node["world_mode"] = target_mode

        if target_mode == "single":
            servers = candidate.get("servers")
            if isinstance(servers, list):
                idx = next(
                    (i for i, s in enumerate(servers)
                     if isinstance(s, dict) and s.get("name") == surviving_server_id),
                    None,
                )
                if idx is not None and idx != 0:
                    servers.insert(0, servers.pop(idx))
            sag = candidate.setdefault("single_allowed_groups", [])
            if not isinstance(sag, list):
                sag = []
                candidate["single_allowed_groups"] = sag
            existing = {str(e.get("umo")) for e in sag if isinstance(e, dict)}
            for umo in migrate_umos:
                if umo not in existing:
                    sag.append({"umo": umo, "note": "从多世界绑定迁移"})
                    existing.add(umo)
            if len(sag) > _MAX_LIST:   # 并入越限 fail-closed（M-b）；此刻尚未 reload、DB 未动
                return await _finalize(
                    {"ok": False, "error": "too_many_groups", "detail": {}},
                    success=0, error="too_many_groups", server_name=server_name_hint)
            state["migrated"] = len(migrate_umos)
            candidate["group_bindings"] = []   # 清 config 种子（M-d 彻底 move）
        else:  # single → multi
            candidate["single_allowed_groups"] = []   # move 清源（目标已在步3预绑）
            state["migrated"] = len(migrate_umos)
            state["cleared_single_allowed"] = True

        # ---- 步5：落库 + reload ----
        outcome = await apply_and_restart(candidate)
        if not outcome.get("ok"):   # reload 失败即中止（M5）：不做 post-reload DB 写
            if target_mode == "multi" and migrate_umos and target_server_id is not None:
                c = get_container()   # single→multi 预绑残留 best-effort 撤销（单模式无害）
                if c is not None:
                    for umo in migrate_umos:
                        try:
                            await c.repo.revoke(umo, target_server_id)
                        except Exception:  # noqa: BLE001
                            pass
            err = outcome.get("error", "restart_failed")
            return await _finalize(
                {"ok": False, "error": err, "detail": {}},
                success=0, error=err, server_name=server_name_hint)

        # ---- 步6：post-reload DB 写（用新容器 repo）----
        new_repo = get_container().repo
        clear_ok = True
        if target_mode == "single":
            try:   # multi→single move 清源（清空全表；M-f 失败处理）
                cleared = await new_repo.clear_all_group_servers()
                state["cleared_group_servers"] = True
                state["cleared_count"] = cleared
            except Exception:  # noqa: BLE001
                clear_ok = False
                state["cleared_group_servers"] = False
            # （purge 循环在 Task 7 追加于此）

        # ---- 步7/8：审计 + 返回 ----
        warnings: dict = {}
        if state["cleared_group_servers"] is False:
            warnings["cleared_group_servers"] = False
        if state["failed_server_ids"]:
            warnings["purge_failed"] = state["failed_server_ids"]
        payload = {
            "ok": True, "config": redact_config(get_raw()), "warnings": warnings,
            "summary": {"from": current_mode, "to": target_mode,
                        "surviving": surviving_server_id, "migrated": state["migrated"],
                        "purged": state["purged"],
                        "failed_server_ids": state["failed_server_ids"]},
        }
        success = 1 if clear_ok else 0
        error = (None if clear_ok
                 else "源介质（DB 群绑定）清理未尽，切回多世界前请人工核查残留")
        return await _finalize(payload, success=success, error=error,
                               server_name=server_name_hint)
