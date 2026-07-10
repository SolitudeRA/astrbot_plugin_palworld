from __future__ import annotations

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

from palchronicle.config import parse_config
from palchronicle.container import Container
from palchronicle.infrastructure.clock import SystemClock


def _resolve_data_dir() -> Path:
    try:
        return Path(StarTools.get_data_dir())
    except Exception:
        return Path(os.getcwd())


@register("astrbot_plugin_palword", "SolitudeRA",
          "只读的 Palworld 世界纪事插件", "0.1.0",
          "https://github.com/SolitudeRA/astrbot_plugin_palword")
class PalChronicle(Star):
    def __init__(self, context, config):
        super().__init__(context, config)
        self._context = context
        self._raw_config = config
        self._container: Container | None = None

    async def initialize(self) -> None:
        cfg = parse_config(self._raw_config, os.environ)
        data_dir = _resolve_data_dir()
        self._container = Container(cfg, data_dir, SystemClock())
        await self._container.start()

    async def terminate(self) -> None:
        if self._container is not None:
            await self._container.stop()
            self._container = None

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

    @staticmethod
    def _is_admin(event) -> bool:
        role = getattr(event, "role", "")
        return role == "admin" or bool(getattr(event, "is_admin", False))

    @filter.command_group("pal")
    def pal(self):
        pass

    @pal.command("status")
    async def status(self, event):
        yield event.plain_result(
            await self._container.commands.status(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("online")
    async def online(self, event):
        yield event.plain_result(
            await self._container.commands.online(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("world")
    async def world(self, event):
        yield event.plain_result(
            await self._container.commands.world(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("rules")
    async def rules(self, event):
        yield event.plain_result(
            await self._container.commands.rules(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("guilds")
    async def guilds(self, event):
        yield event.plain_result(
            await self._container.commands.guilds(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("guild")
    async def guild(self, event):
        yield event.plain_result(
            await self._container.commands.guild(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("bases")
    async def bases(self, event):
        yield event.plain_result(
            await self._container.commands.bases(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("base")
    async def base(self, event):
        yield event.plain_result(
            await self._container.commands.base(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("events")
    async def events(self, event):
        yield event.plain_result(
            await self._container.commands.events(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("today")
    async def today(self, event):
        yield event.plain_result(
            await self._container.commands.today(self._umo(event), self._msg(event), self._is_group(event))
        )

    @pal.command("servers")
    async def servers(self, event):
        yield event.plain_result(
            await self._container.commands.servers(self._umo(event), self._is_group(event), self._is_admin(event))
        )

    @pal.command("help")
    async def help(self, event):
        yield event.plain_result(
            self._container.commands.help(self._msg(event), self._is_admin(event))
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @pal.command("use")
    async def use(self, event):
        yield event.plain_result(
            await self._container.commands.use(
                self._umo(event), self._msg(event), self._is_group(event), self._is_admin(event)
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @pal.command("unbind")
    async def unbind(self, event):
        yield event.plain_result(
            await self._container.commands.unbind(
                self._umo(event), self._msg(event), self._is_group(event), self._is_admin(event)
            )
        )
