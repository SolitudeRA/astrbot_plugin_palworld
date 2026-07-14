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
    from .palworld_terminal.config import parse_config
    from .palworld_terminal.container import Container
    from .palworld_terminal.infrastructure.clock import SystemClock
    from .palworld_terminal.presentation import web_api
except ImportError:  # 测试/独立环境从仓库根以顶级模块导入
    from palworld_terminal.config import parse_config
    from palworld_terminal.container import Container
    from palworld_terminal.infrastructure.clock import SystemClock
    from palworld_terminal.presentation import web_api


_log = logging.getLogger("palworld_terminal.main")


def _resolve_data_dir() -> Path:
    try:
        return Path(StarTools.get_data_dir())
    except Exception:
        return Path(os.getcwd())


@register("astrbot_plugin_palworld", "SolitudeRA",
          "监测 Palworld 专用服务器,提供群内状态查询、日报与玩家档案(只读)", "v0.8.7",
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
        cfg = parse_config(self._raw_config, os.environ)
        data_dir = _resolve_data_dir()
        self._container = Container(cfg, data_dir, SystemClock())
        await self._container.start()
        self._maybe_register_web_api()

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

    def _busy_msg(self) -> str | None:
        if self._restarting or self._container is None:
            return "插件正在重载配置，请稍后重试"
        return None

    def _build_container(self, cfg):
        return Container(cfg, _resolve_data_dir(), SystemClock())

    async def _guarded(self, call):
        """在途门闩内执行一次只读操作;重载中一律回 busy 文案。

        计数先于 busy 判定(flag+counter 握手):若重载已置 _restarting,
        这里拒绝;若重载在计数之后才开始,_wait_quiescent 会等本操作退出。
        """
        self._inflight += 1
        self._idle.clear()
        try:
            if (m := self._busy_msg()):
                return m
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

    async def _guarded_admin(self, event, command_str, call):
        """服务器管控写命令的门:仅 busy+inflight 包裹,不做 admin_denied。

        admin 硬门与 feature 门在 Commands.admin_write 内(门序铁律:admin 先于
        feature),此处不重复;命令串亦在 config._NON_LOCKABLE,永不进 admin_only。
        """
        self._inflight += 1
        self._idle.clear()
        try:
            if (m := self._busy_msg()):
                return m
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

    @pal.command("status")
    async def status(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "status", lambda c: c.commands.status(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("online")
    async def online(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "online", lambda c: c.commands.online(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("world")
    async def world(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "world", lambda c: c.commands.world(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("rules")
    async def rules(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "rules", lambda c: c.commands.rules(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("guilds")
    async def guilds(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "guilds", lambda c: c.commands.guilds(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("guild")
    async def guild(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "guild", lambda c: c.commands.guild(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("bases")
    async def bases(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "bases", lambda c: c.commands.bases(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("base")
    async def base(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "base", lambda c: c.commands.base(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("events")
    async def events(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "events", lambda c: c.commands.events(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("today")
    async def today(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "today", lambda c: c.commands.today(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("rank")
    async def rank(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "rank", lambda c: c.commands.rank(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("player")
    async def player(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "player", lambda c: c.commands.player(
                self._umo(event), self._msg(event), self._is_group(event)))
        )

    @pal.command("me")
    async def me(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "me", lambda c: c.commands.me(
                self._umo(event), self._msg(event), self._is_group(event), self._sender_id(event)))
        )

    @pal.command("bind")
    async def bind(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "bind", lambda c: c.commands.bind(
                self._umo(event), self._msg(event), self._is_group(event), self._sender_id(event)))
        )

    @pal.command("unbind")
    async def unbind(self, event):
        yield event.plain_result(
            await self._guarded_cmd(event, "unbind", lambda c: c.commands.unbind_self(
                self._umo(event), self._msg(event), self._is_group(event), self._sender_id(event)))
        )

    @pal.command("server")
    async def server(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.server(
                self._umo(event), self._msg(event), self._is_group(event),
                c.commands.is_plugin_admin(self._sender_id(event))))
        )

    @pal.command("whoami")
    async def whoami(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.whoami(self._sender_id(event)))
        )

    @pal.command("help")
    async def help(self, event):
        yield event.plain_result(
            await self._guarded(lambda c: c.commands.help(self._msg(event), self._is_admin(event)))
        )

    # ---- 服务器管控写命令（门在 admin_write 内：admin 硬门先于 feature；
    # arg_str 传完整 message_str，Commands 内 parse_arg 自剥命令词）----
    @pal.command("announce")
    async def announce(self, event):
        yield event.plain_result(await self._guarded_admin(
            event, "announce", lambda c: c.commands.admin_write(
                "announce", "server_admin_basic", self._sender_id(event), self._umo(event),
                self._is_group(event), self._msg(event),
                c.commands.is_plugin_admin(self._sender_id(event)))))

    @pal.command("save")
    async def save(self, event):
        yield event.plain_result(await self._guarded_admin(
            event, "save", lambda c: c.commands.admin_write(
                "save", "server_admin_basic", self._sender_id(event), self._umo(event),
                self._is_group(event), self._msg(event),
                c.commands.is_plugin_admin(self._sender_id(event)))))

    @pal.command("kick")
    async def kick(self, event):
        yield event.plain_result(await self._guarded_admin(
            event, "kick", lambda c: c.commands.admin_write(
                "kick", "server_admin_basic", self._sender_id(event), self._umo(event),
                self._is_group(event), self._msg(event),
                c.commands.is_plugin_admin(self._sender_id(event)))))

    @pal.command("unban")
    async def unban(self, event):
        yield event.plain_result(await self._guarded_admin(
            event, "unban", lambda c: c.commands.admin_write(
                "unban", "server_admin_basic", self._sender_id(event), self._umo(event),
                self._is_group(event), self._msg(event),
                c.commands.is_plugin_admin(self._sender_id(event)))))

    @pal.command("ban")
    async def ban(self, event):
        yield event.plain_result(await self._guarded_admin(
            event, "ban", lambda c: c.commands.admin_write(
                "ban", "server_admin_danger", self._sender_id(event), self._umo(event),
                self._is_group(event), self._msg(event),
                c.commands.is_plugin_admin(self._sender_id(event)))))

    @pal.command("shutdown")
    async def shutdown(self, event):
        yield event.plain_result(await self._guarded_admin(
            event, "shutdown", lambda c: c.commands.admin_write(
                "shutdown", "server_admin_danger", self._sender_id(event), self._umo(event),
                self._is_group(event), self._msg(event),
                c.commands.is_plugin_admin(self._sender_id(event)))))

    @pal.command("stop")
    async def stop(self, event):
        yield event.plain_result(await self._guarded_admin(
            event, "stop", lambda c: c.commands.admin_write(
                "stop", "server_admin_danger", self._sender_id(event), self._umo(event),
                self._is_group(event), self._msg(event),
                c.commands.is_plugin_admin(self._sender_id(event)))))

    @pal.command("confirm")
    async def confirm(self, event):
        # confirm 走 _guarded（core）；admin 硬门在 Commands.confirm 内自判。
        yield event.plain_result(await self._guarded(lambda c: c.commands.confirm(
            self._sender_id(event), self._umo(event), self._is_group(event),
            c.commands.is_plugin_admin(self._sender_id(event)))))
