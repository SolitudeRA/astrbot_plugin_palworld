from __future__ import annotations

import asyncio
import copy
import inspect
import logging
import os
from pathlib import Path

try:  # real AstrBot runtime
    from astrbot.api import AstrBotConfig
    from astrbot.api.event import filter
    from astrbot.api.star import Context, Star, StarTools, register
    _ASTRBOT = True
except Exception:  # test / standalone environment: lightweight stubs
    _ASTRBOT = False
    AstrBotConfig = dict  # type: ignore

    class Context:  # type: ignore
        pass

    class Star:  # type: ignore
        def __init__(self, context=None, config=None):
            pass

    class StarTools:  # type: ignore
        @staticmethod
        def get_data_dir() -> Path:
            return Path(os.getcwd())

    def register(*_a, **_k):  # type: ignore
        def deco(cls):
            return cls
        return deco

    class _PermissionType:
        ADMIN = "admin"

    class _Filter:  # minimal decorator stubs
        PermissionType = _PermissionType

        @staticmethod
        def command_group(_name):
            def deco(fn):
                fn.is_group = True
                fn.command = lambda *_a, **_k: (lambda f: f)
                return fn
            return deco

        @staticmethod
        def permission_type(_p):
            def deco(fn):
                return fn
            return deco

    filter = _Filter()  # type: ignore

try:  # AstrBot 以 data.plugins.<目录>.main 命名空间加载，插件目录不在 sys.path
    from .palworld_terminal.application.command_permissions import migrate_legacy_to_rows
    from .palworld_terminal.config import parse_config
    from .palworld_terminal.container import Container
    from .palworld_terminal.domain.enums import AccessMode
    from .palworld_terminal.infrastructure.clock import SystemClock
    from .palworld_terminal.presentation import web_api
    from .palworld_terminal.presentation.locale import L
except ImportError:  # 测试/独立环境从仓库根以顶级模块导入
    from palworld_terminal.application.command_permissions import migrate_legacy_to_rows
    from palworld_terminal.config import parse_config
    from palworld_terminal.container import Container
    from palworld_terminal.domain.enums import AccessMode
    from palworld_terminal.infrastructure.clock import SystemClock
    from palworld_terminal.presentation import web_api
    from palworld_terminal.presentation.locale import L


_log = logging.getLogger("palworld_terminal.main")

# 首次设置逗口集（放行首词）：未确认前仍可用的元命令。须 ⊆ FLAT_ACTIONS
# （setup_gate_test.test_setup_exempt_subset_of_flat_actions 锚定）。
_SETUP_EXEMPT = frozenset({"help", "whoami", "whereami"})


def _resolve_data_dir() -> Path:
    try:
        return Path(StarTools.get_data_dir())
    except Exception:
        return Path(os.getcwd())


def _migrate_permissions_config(config) -> None:
    """装载时一次性把 legacy 权限配置迁移成 command_permissions 行并落库（复核 F1/B2）。

    幂等：command_permissions 已在场 → 跳过；legacy 键（features/admin_only_commands）
    都缺席 → 跳过（全新装不动、不 save）。否则迁移写回 config 并删旧键、持久化。

    根治读路径失锁：老用户升级后 storage 仍是旧键，GET 下发的 raw 不含
    command_permissions，前端树从空初始化、一保存即把不含旧锁的配置落库使旧锁永久
    失效。此处把 legacy 迁成行写回存储并删旧键，使 存储/GET/运行时/保存 四者同源。
    """
    if "command_permissions" in config:
        return
    if "features" not in config and "admin_only_commands" not in config:
        return
    rows, invalid = migrate_legacy_to_rows(config)
    config["command_permissions"] = rows
    config.pop("features", None)
    config.pop("admin_only_commands", None)
    # 不可迁移的 legacy 锁（非 LOCKABLE）无法转成行、迁移后即消失；不得静默丢弃，
    # 装载时告警一次，让管理员知晓其锁未生效（承接 Phase 1 unknown_locks 安全可见性）。
    if invalid:
        _log.warning(
            "以下 legacy admin_only_commands 条目不是可锁命令、迁移无法保留，锁未生效：%s",
            "、".join(invalid),
        )
    # AstrBotConfig 落盘方法为 save_config()（与 _apply_and_restart 一致）；测试替身同名。
    save = getattr(config, "save_config", None)
    if callable(save):
        save()


@register("astrbot_plugin_palworld", "SolitudeRA",
          "监测 Palworld 专用服务器,分级指令提供状态查询、日报、玩家档案与受控服务器管控", "v0.9.9",
          "https://github.com/SolitudeRA/astrbot_plugin_palworld")
class PalWorldTerminal(Star):
    def __init__(self, context, config):
        super().__init__(context, config)
        self._context = context
        self._raw_config = config
        self._container: Container | None = None
        self._restarting = False
        self._save_lock = asyncio.Lock()
        self._last_save_ts: float | None = None
        # 在途只读操作计数(命令/状态查询):重载 stop 旧容器前等待归零,
        # 防止在途 await 里的 DB 连接/HTTP session 被脚下抽走(审查 E1)
        self._inflight = 0
        self._idle = asyncio.Event()
        self._idle.set()

    async def initialize(self) -> None:
        # 读取配置 / 建容器之前，先一次性迁移 legacy 权限配置并落库（复核 F1/B2）。
        _migrate_permissions_config(self._raw_config)
        cfg = parse_config(self._raw_config, os.environ)
        data_dir = _resolve_data_dir()
        self._container = Container(cfg, data_dir, SystemClock())
        await self._container.start()
        self._maybe_register_web_api()
        self._log_startup_warnings()

    def _log_startup_warnings(self) -> None:
        """装配后暴露安全相关启动告警（spec §5/§7）：单模式 restricted 授权名单为空
        （所有会话都无法查询）、非法命令权限配置项（command_permissions 未知命令 / 轴违规，
        均未生效 = 配置失效）。"""
        c = self._container
        if c is None:
            return
        r = c.config.routing
        if (r.world_mode == "single" and r.access_mode is AccessMode.RESTRICTED
                and not r.single_allowed_groups):
            _log.warning(
                "单世界模式 + restricted 但授权群名单为空：当前所有群/私聊都无法查询。"
                "请在群里发 /pal whereami 获取群标识，在设置页「连接」章的授权群名单中添加。"
            )
        invalid = c.config.permissions.invalid_command_keys
        if invalid:
            _log.warning(
                "以下 command_permissions 配置项非法（未知命令或轴违规）、未生效：%s",
                "、".join(invalid),
            )
        upstream_ineffective = c.config.permissions.upstream_ineffective_keys
        if upstream_ineffective:
            _log.warning(
                "以下命令依赖的 game-data 接口上游未开放，配置的启用未生效：%s",
                "、".join(upstream_ineffective),
            )

    async def terminate(self) -> None:
        if self._container is not None:
            await self._container.stop()
            self._container = None

    def _maybe_register_web_api(self) -> None:
        # hasattr 仅作测试 stub 护栏，不是版本判断（真实 AstrBot 恒有此方法）
        if hasattr(self._context, "register_web_api"):
            self._register_web_api()

    def _register_web_api(self) -> None:
        p = "/astrbot_plugin_palworld"
        self._context.register_web_api(
            f"{p}/config/get", self._web_config_get, ["GET"], "读取插件配置(脱敏)")
        self._context.register_web_api(
            f"{p}/config/save", self._web_config_save, ["POST"], "保存插件配置并重启")
        self._context.register_web_api(
            f"{p}/status/overview", self._web_status, ["GET"], "服务器状态概览")
        self._context.register_web_api(
            f"{p}/audit/list", self._web_audit, ["GET"], "管理审计日志(只读)")
        self._context.register_web_api(
            f"{p}/mode/transfer/preview", self._web_mode_transfer_preview, ["GET"],
            "模式转移预览(只读)")
        self._context.register_web_api(
            f"{p}/mode/transfer", self._web_mode_transfer, ["POST"], "模式转移(原子编排)")
        self._context.register_web_api(
            f"{p}/mode/orphans", self._web_orphans_list, ["GET"], "孤儿服务器数据列表(只读)")
        self._context.register_web_api(
            f"{p}/mode/orphans/purge", self._web_orphans_purge, ["POST"],
            "清理孤儿服务器数据")

    def _busy_msg(self) -> str | None:
        if self._restarting or self._container is None:
            return L("busy")
        return None

    def _build_container(self, cfg):
        return Container(cfg, _resolve_data_dir(), SystemClock())

    def _setup_gate(self, command_str: str) -> str | None:
        """首次设置闸：未确认前，非逗口命令一律回引导语。读 live 配置。
        调用点已在 _busy_msg() 之后 → self._container 必非 None。"""
        if command_str in _SETUP_EXEMPT:
            return None
        if self._container.config.routing.setup_confirmed:
            return None
        return L("setup_required")

    async def _guarded(self, call, command_str):
        """在途门闩内执行一次只读操作;重载中一律回 busy 文案。

        计数先于 busy 判定(flag+counter 握手):若重载已置 _restarting,
        这里拒绝;若重载在计数之后才开始,_wait_quiescent 会等本操作退出。
        """
        self._inflight += 1
        self._idle.clear()
        try:
            if (m := self._busy_msg()):
                return m
            if (g := self._setup_gate(command_str)):
                return g
            res = call(self._container)
            if inspect.isawaitable(res):
                res = await res
            return res
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()

    async def _guarded_cmd(self, event, command_str, call):
        """可锁命令的门:先判 admin_only_commands 再走 _guarded。"""
        self._inflight += 1
        self._idle.clear()
        try:
            if (m := self._busy_msg()):
                return m
            if (g := self._setup_gate(command_str)):
                return g
            denied = self._container.commands.admin_denied(command_str, self._sender_id(event))
            if denied is not None:
                return denied
            res = call(self._container)
            if inspect.isawaitable(res):
                res = await res
            return res
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()

    async def _wait_quiescent(self, timeout: float = 5.0) -> None:
        # 新操作已被 _restarting 挡在门外;等在途的退完再关旧容器。
        # 超时兜底:个别慢查询不至于永久卡死重载(此时回到修复前的竞态概率)
        try:
            await asyncio.wait_for(self._idle.wait(), timeout)
        except TimeoutError:
            _log.warning("等待在途操作超时(%ss),继续重载——个别在途查询可能失败", timeout)

    async def _apply_and_restart(self, candidate: dict) -> dict:
        old_raw = copy.deepcopy(dict(self._raw_config))
        self._restarting = True
        try:
            for k, v in candidate.items():
                self._raw_config[k] = v
            if hasattr(self._raw_config, "save_config"):
                self._raw_config.save_config()
            new_cfg = parse_config(self._raw_config, os.environ)
            await self._wait_quiescent()
            if self._container is not None:
                await self._container.stop()
                self._container = None
            new_container = self._build_container(new_cfg)
            try:
                await new_container.start()
            except Exception:
                # 半启动的新容器先回收，避免 DB 连接/HTTP session 泄漏（规格 §3.2 步骤 8）
                try:
                    await new_container.stop()
                except Exception:  # noqa: BLE001
                    pass
                raise
            self._container = new_container
            # config 热重载:清空所有 pending 确认,避免旧上下文被误确认(spec §4.4)
            self._container.commands.clear_pending()
            return {"ok": True, "warnings": {
                "skipped_servers": [{"raw_name": s.raw_name, "reason": s.reason}
                                    for s in new_cfg.skipped],
                "skipped_headers": [{"raw_name": h.raw_name, "reason": h.reason}
                                    for h in new_cfg.skipped_headers],
            }}
        except Exception:  # noqa: BLE001 — 脱敏：不外传异常文本
            return await self._rollback(old_raw)
        finally:
            self._restarting = False

    async def _rollback(self, old_raw: dict) -> dict:
        try:
            # 先回收可能半启动的新容器
            if self._container is not None:
                try:
                    await self._container.stop()
                except Exception:  # noqa: BLE001
                    pass
            for k in list(self._raw_config.keys()):
                self._raw_config[k] = old_raw.get(k)
            if hasattr(self._raw_config, "save_config"):
                self._raw_config.save_config()
            old_cfg = parse_config(self._raw_config, os.environ)
            restored = self._build_container(old_cfg)
            await restored.start()
            self._container = restored
            return {"ok": False, "error": "restart_failed_rolled_back", "detail": {}}
        except Exception:  # noqa: BLE001
            self._container = None
            return {"ok": False, "error": "restart_failed", "detail": {}}

    # ---- Quart 薄壳：解包 request → web_api → jsonify（业务成败恒 HTTP 200）----
    @staticmethod
    def _current_username() -> str | None:
        # 用户名只绑在 Quart g 上（跨 v4.24.x 纯 Quart ~ v4.26.x 兼容层全区间），
        # 从不在 request 上（根因 A）。下沉为单点便于单测注入。
        from quart import g
        try:
            return getattr(g, "username", None)
        except RuntimeError:  # 无 app context（正常 register_web_api 链路不可达）
            return None

    @staticmethod
    def _has_identity() -> bool:
        # 身份兜底（规格 §5.3c）：网关鉴权之外的最后防线。禁用/卸载后端点仍可达，
        # 拿不到 Dashboard 登录用户即拒。在读取任何配置/secret 之前判定，
        # 绝不记录、绝不 str(exc)、绝不回显 request 内容。
        return bool(PalWorldTerminal._current_username())

    @staticmethod
    def _deny_unauthorized():
        from quart import jsonify
        return jsonify({"ok": False, "error": "unauthorized", "detail": {}})

    async def _web_config_get(self):
        from quart import jsonify
        if not self._has_identity():
            return self._deny_unauthorized()
        _code, payload = await web_api.handle_config_get(lambda: self._raw_config)
        return jsonify(payload)

    async def _web_status(self):
        from quart import jsonify
        if not self._has_identity():
            return self._deny_unauthorized()
        # 与命令同一在途门闩:重载 stop 前等待本次查询退出
        self._inflight += 1
        self._idle.clear()
        try:
            _code, payload = await web_api.handle_status_overview(
                self._container, self._restarting)
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
        return jsonify(payload)

    async def _web_audit(self):
        from quart import jsonify, request
        if not self._has_identity():
            return self._deny_unauthorized()
        try:
            limit = int(request.args.get("limit", 100))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(500, limit))  # clamp：防超大查询打穿 DB
        # 与命令/状态同一在途门闩:重载 stop 前等待本次查询退出
        self._inflight += 1
        self._idle.clear()
        try:
            # 重载窗口折叠为 None:handler 回空列表 + restarting
            container = None if self._restarting else self._container
            _code, payload = await web_api.handle_audit_list(container, limit)
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
        return jsonify(payload)

    async def _web_config_save(self):
        import time

        from quart import jsonify, request
        if not self._has_identity():
            return self._deny_unauthorized()
        body = await request.get_json(silent=True)
        _code, payload = await web_api.handle_config_save(
            body, old_raw=self._raw_config, env=os.environ,
            lock=self._save_lock, now=time.monotonic(),
            last_save_ts=self._last_save_ts,
            apply_and_restart=self._apply_and_restart)
        if payload.get("ok") and "saved_ts" in payload:
            self._last_save_ts = payload.pop("saved_ts")
        return jsonify(payload)

    async def _web_mode_transfer_preview(self):
        from quart import jsonify, request
        if not self._has_identity():
            return self._deny_unauthorized()
        target = request.args.get("target", "single")
        self._inflight += 1   # 只读端点走在途门闩（镜像 _web_status/_web_audit）
        self._idle.clear()
        try:
            container = None if self._restarting else self._container
            _code, payload = await web_api.handle_mode_transfer_preview(
                container, self._restarting, target)
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
        return jsonify(payload)

    async def _web_orphans_list(self):
        from quart import jsonify
        if not self._has_identity():
            return self._deny_unauthorized()
        self._inflight += 1
        self._idle.clear()
        try:
            container = None if self._restarting else self._container
            _code, payload = await web_api.handle_orphans_list(container, self._restarting)
        finally:
            self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
        return jsonify(payload)

    async def _web_mode_transfer(self):
        import time

        from quart import jsonify, request
        if not self._has_identity():
            return self._deny_unauthorized()
        body = await request.get_json(silent=True)
        # 写端点：只持 _save_lock、绝不自增 _inflight（否则 _wait_quiescent 等自己白等）
        _code, payload = await web_api.handle_mode_transfer(
            body, get_raw=lambda: self._raw_config,
            get_container=lambda: self._container, busy_msg=self._busy_msg,
            lock=self._save_lock, now=int(time.time()),
            apply_and_restart=self._apply_and_restart,
            current_username=self._current_username)
        return jsonify(payload)

    async def _web_orphans_purge(self):
        import time

        from quart import jsonify, request
        if not self._has_identity():
            return self._deny_unauthorized()
        body = await request.get_json(silent=True)
        _code, payload = await web_api.handle_orphans_purge(
            body, get_container=lambda: self._container, busy_msg=self._busy_msg,
            lock=self._save_lock, now=int(time.time()),
            current_username=self._current_username)
        return jsonify(payload)

    # ---- context helpers ----
    @staticmethod
    def _umo(event) -> str:
        return getattr(event, "unified_msg_origin", "")

    @staticmethod
    def _msg(event) -> str:
        return getattr(event, "message_str", "")

    @staticmethod
    def _is_group(event) -> bool:
        fn = getattr(event, "is_private_chat", None)
        if callable(fn):
            return not fn()
        gid = getattr(event, "get_group_id", lambda: "")()
        return bool(gid)

    def _is_admin(self, event) -> bool:
        c = self._container
        if c is None:
            return False
        return c.commands.is_plugin_admin(self._sender_id(event))

    @staticmethod
    def _sender_id(event) -> str:
        # 平台复合身份：单平台 sender id 跨平台会碰撞（QQ 12345 与 Telegram 12345），
        # 故与平台名组合成全局唯一。用作绑定主键的原始输入（落库前再 HMAC）。
        platform = getattr(event, "get_platform_name", lambda: "")() or ""
        sender = getattr(event, "get_sender_id", lambda: "")() or ""
        return f"{platform}:{sender}"

    @filter.command_group("pal")
    def pal(self):
        pass

    # ---- 分级命令：5 组 handler（world/guild/player/server/link）+ 7 扁平
    # （rank/online/me/whoami/whereami/help/confirm）= 12 注册。AstrBot 只认首词,子动作
    # (world status …) 由 Commands 层分发器自解析。门控下沉进分发（功能门 per-子动作、
    # admin_denied 完整路径、server 写走 admin_write）;main 层只施 busy/inflight 门闩。----

    @pal.command("world")
    async def world(self, event):
        yield event.plain_result(await self._guarded(lambda c: c.commands.world_grp(
            self._umo(event), self._msg(event), self._is_group(event),
            self._sender_id(event), c.commands.is_plugin_admin(self._sender_id(event))), "world"))

    @pal.command("guild")
    async def guild(self, event):
        yield event.plain_result(await self._guarded(lambda c: c.commands.guild_grp(
            self._umo(event), self._msg(event), self._is_group(event),
            self._sender_id(event), c.commands.is_plugin_admin(self._sender_id(event))), "guild"))

    @pal.command("player")
    async def player(self, event):
        yield event.plain_result(await self._guarded(lambda c: c.commands.player_grp(
            self._umo(event), self._msg(event), self._is_group(event),
            self._sender_id(event), c.commands.is_plugin_admin(self._sender_id(event))), "player"))

    @pal.command("server")
    async def server(self, event):
        # server 组含写命令：走 _guarded 门闩即可,admin 硬门 + feature 门在
        # Commands.server_grp→admin_write 内（门序 admin 先于 feature 不变）。
        yield event.plain_result(await self._guarded(lambda c: c.commands.server_grp(
            self._umo(event), self._msg(event), self._is_group(event),
            self._sender_id(event), c.commands.is_plugin_admin(self._sender_id(event))), "server"))

    @pal.command("link")
    async def link(self, event):
        # link add/remove 需 is_admin（门在 Commands.link 内）；单模式守卫见 _link_dispatch。
        yield event.plain_result(await self._guarded(lambda c: self._link_dispatch(c, event), "link"))

    def _link_dispatch(self, c, event):
        # 单世界模式守卫（唯一防线，先于任何 routing.use/unbind = DB 写）：单模式无需选择
        # 服务器，直接回提示，绝不触达 Commands.link（help 省略 link 组只是视觉，此处才是拦截）。
        if c.config.routing.world_mode == "single":
            return L("link_single_mode")
        return c.commands.link(
            self._umo(event), self._msg(event), self._is_group(event),
            self._sender_id(event), c.commands.is_plugin_admin(self._sender_id(event)))

    @pal.command("rank")
    async def rank(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "rank", lambda c: c.commands.rank(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("online")
    async def online(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "online", lambda c: c.commands.online(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("me")
    async def me(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "me", lambda c: c.commands.me(
                self._umo(event), self._msg(event), self._is_group(event), self._sender_id(event)))
        )

    @pal.command("whoami")
    async def whoami(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.whoami(self._sender_id(event)), "whoami")
        )

    @pal.command("whereami")
    async def whereami(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.whereami(self._umo(event)), "whereami")
        )

    @pal.command("help")
    async def help(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.help(self._msg(event), self._is_admin(event)), "help")
        )

    @pal.command("confirm")
    async def confirm(self, event):
        # confirm 走 _guarded（core）；admin 硬门在 Commands.confirm 内自判。
        yield event.plain_result(await self._guarded(lambda c: c.commands.confirm(
            self._sender_id(event), self._umo(event), self._is_group(event),
            c.commands.is_plugin_admin(self._sender_id(event))), "confirm"))
