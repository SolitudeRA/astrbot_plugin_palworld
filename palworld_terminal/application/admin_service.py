from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..adapters.normalizer import normalize_players
from ..adapters.palworld_rest import _ADMIN_PATH, RestResponse
from ..adapters.privacy_filter import hash_user_id
from ..domain.enums import EndpointName

_NETWORK_ERROR = "network error"

# 可被直接识别为原始 userid 的前缀（钉死；冲突边界：真名恰以此开头者需改用 userid 精确指定）。
_USERID_PREFIXES = ("steam_",)

FetchFn = Callable[[str, EndpointName], Awaitable[RestResponse]]
PostFn = Callable[[str, str, "dict[str, Any] | None"], Awaitable[RestResponse]]


@dataclass(slots=True)
class AdminResult:
    ok: bool
    message_key: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TargetResult:
    kind: str  # "userid" | "unique" | "multi" | "none" | "unreachable"
    userid: str | None = None
    name: str | None = None
    candidates: list[dict[str, str]] = field(default_factory=list)


class AdminService:
    """无目标写命令（announce/save/shutdown/stop）+ 审计落库。

    目标类命令（kick/ban/unban）在 T5 补齐，届时复用 ``_execute`` 的
    ``target_name``/``target_userid`` 通道（target_hash 用 world_id 命名空间）。
    """

    def __init__(self, routing, fetch: FetchFn, post: PostFn, repo, salt: bytes, clock):
        self._routing = routing
        self._fetch = fetch
        self._post = post
        self._repo = repo
        self._salt = salt
        self._clock = clock

    async def _execute(
        self,
        admin_id: str,
        umo: str,
        is_group: bool,
        *,
        action: str,
        path: str,
        json_body: dict[str, Any] | None,
        target_name: str | None = None,
        target_userid: str | None = None,
        detail: str = "",
        initiated_ok_on_disconnect: bool = False,
    ) -> AdminResult:
        # path 必须是已知写端点：消费 _ADMIN_PATH，杜绝拼错端点静默打偏。
        if path not in _ADMIN_PATH:
            raise ValueError(f"unknown admin path: {path!r}")

        resolution = await self._routing.resolve(umo, None, is_group)
        if resolution.server is None:
            return AdminResult(
                ok=False,
                message_key="admin_resolve_failed",
                params={"reason": resolution.error or ""},
            )
        server = resolution.server

        world = await self._repo.get_current_world(server.server_id)
        world_id = world.world_id if world is not None else ""

        resp = await self._post(server.server_id, path, json_body)
        initiated = (
            initiated_ok_on_disconnect
            and not resp.ok
            and resp.error == _NETWORK_ERROR
        )
        ok = resp.ok or initiated

        target_hash = (
            hash_user_id(self._salt, world_id, target_userid) if target_userid else None
        )

        await self._repo.insert_audit(
            ts=self._clock.now(),
            admin_id=admin_id,
            action=action,
            server_name=server.name,
            target_name=target_name,
            target_hash=target_hash,
            detail=detail or None,
            success=1 if ok else 0,
            error=None if ok else resp.error,
        )

        if not ok:
            message_key = "admin_failed"
        elif initiated:
            message_key = "admin_shutdown_initiated"
        else:
            message_key = "admin_ok"

        return AdminResult(
            ok=ok,
            message_key=message_key,
            params={
                "server": server.name,
                "action": action,
                "target": target_name or "",
                "error": resp.error or "",
            },
        )

    async def announce(
        self, admin_id: str, umo: str, is_group: bool, message: str
    ) -> AdminResult:
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="announce",
            path="announce",
            json_body={"message": message},
            detail=message,
        )

    async def save(self, admin_id: str, umo: str, is_group: bool) -> AdminResult:
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="save",
            path="save",
            json_body=None,
        )

    async def shutdown(
        self, admin_id: str, umo: str, is_group: bool, seconds: int, message: str
    ) -> AdminResult:
        # REST body {"waittime": <秒int>, "message": <公告str>} → 倒计时关服。
        detail = f"{seconds}s: {message}" if message else f"{seconds}s"
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="shutdown",
            path="shutdown",
            json_body={"waittime": seconds, "message": message},
            detail=detail,
            initiated_ok_on_disconnect=True,
        )

    async def stop(self, admin_id: str, umo: str, is_group: bool) -> AdminResult:
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="stop",
            path="stop",
            json_body=None,
            initiated_ok_on_disconnect=True,
        )

    async def resolve_target(self, server_id: str, token: str) -> TargetResult:
        """把用户输入的目标 token 解析成可用于写操作的原始 userid。

        以 ``steam_`` 前缀开头 → 直接当 userid（不拉取）；否则视作角色名，
        **实时** 拉 /players 原始响应按 ``name`` 精确匹配求 ``userId``。
        0/1/多 命中 → ``none``/``unique``/``multi``。明文 userid 用完即弃。
        拉取失败（服务器不可达/网络错误）→ ``unreachable``，与真·无此玩家（``none``）区分。
        """
        if token.startswith(_USERID_PREFIXES):
            return TargetResult(kind="userid", userid=token)

        resp = await self._fetch(server_id, EndpointName.PLAYERS)
        if not resp.ok:
            # 拉取在线列表失败：无法判定玩家是否存在，绝不落到 none（会误报「无此玩家」）。
            return TargetResult(kind="unreachable", name=token)
        rows = (
            normalize_players(resp.data, self._clock.now())
            if resp.data is not None
            else []
        )
        matches = [
            r for r in rows if r.get("name") == token and r.get("userId")
        ]
        if not matches:
            return TargetResult(kind="none", name=token)
        if len(matches) == 1:
            return TargetResult(
                kind="unique", userid=str(matches[0]["userId"]), name=token
            )
        candidates = [
            {"name": str(r.get("name") or ""), "userid": str(r["userId"])}
            for r in matches
        ]
        return TargetResult(kind="multi", name=token, candidates=candidates)

    async def _target_write(
        self,
        admin_id: str,
        umo: str,
        is_group: bool,
        *,
        action: str,
        path: str,
        token: str,
        reason: str,
    ) -> AdminResult:
        resolution = await self._routing.resolve(umo, None, is_group)
        if resolution.server is None:
            return AdminResult(
                ok=False,
                message_key="admin_resolve_failed",
                params={"reason": resolution.error or ""},
            )
        target = await self.resolve_target(resolution.server.server_id, token)
        if target.kind == "unreachable":
            # 拉取在线列表失败：未实际发起，不 post、不审计（区别于「无此玩家」）。
            return AdminResult(
                ok=False, message_key="target_unreachable", params={"target": token}
            )
        if target.kind == "none":
            # 未命中：未实际发起，不 post、不审计。
            return AdminResult(
                ok=False, message_key="target_none", params={"target": token}
            )
        if target.kind == "multi":
            # 重名歧义：未实际发起，不 post、不审计。
            return AdminResult(
                ok=False,
                message_key="target_multi",
                params={
                    "target": token,
                    "candidates": [c["name"] for c in target.candidates],
                },
            )
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action=action,
            path=path,
            json_body={"userid": target.userid, "message": reason},
            target_name=target.name,  # userid 直传时为 None：不落明文 id 到 name
            target_userid=target.userid,
            detail=reason,
        )

    async def execute_target(
        self,
        admin_id: str,
        umo: str,
        is_group: bool,
        *,
        action: str,
        path: str,
        userid: str,
        name: str | None,
        reason: str,
    ) -> AdminResult:
        """执行一次「目标已解析」的写操作（供 Commands 中央编排 / confirm 复用）。

        与 ``_target_write`` 的差别：**不**再调 ``resolve_target``。confirm 场景下
        目标玩家可能已离线，重解析会失败或错位；此处直传首发解析到的 ``userid``/
        ``name``——审计 ``target_name`` 仍是角色名、``target_hash`` 仍是该 userid 的
        world_id 命名空间 hash（绝不把 userid 当名字）。目标服务器仍由 ``_execute``
        内 ``routing.resolve`` 实时定位（confirm 复检已重跑授权）。
        """
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action=action,
            path=path,
            json_body={"userid": userid, "message": reason},
            target_name=name,
            target_userid=userid,
            detail=reason,
        )

    async def kick(
        self, admin_id: str, umo: str, is_group: bool, token: str, reason: str
    ) -> AdminResult:
        return await self._target_write(
            admin_id, umo, is_group, action="kick", path="kick", token=token,
            reason=reason,
        )

    async def ban(
        self, admin_id: str, umo: str, is_group: bool, token: str, reason: str
    ) -> AdminResult:
        return await self._target_write(
            admin_id, umo, is_group, action="ban", path="ban", token=token,
            reason=reason,
        )

    async def unban(
        self, admin_id: str, umo: str, is_group: bool, userid: str
    ) -> AdminResult:
        # 解封无名字解析：直接用 userid（审计 hash，不落明文）。
        return await self._execute(
            admin_id,
            umo,
            is_group,
            action="unban",
            path="unban",
            json_body={"userid": userid},
            target_userid=userid,
        )
