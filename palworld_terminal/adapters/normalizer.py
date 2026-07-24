from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..adapters.metadata_repository import MetadataRepository
from ..domain.enums import UnitType
from ..domain.models import (
    CharacterActor,
    GameDataSnapshot,
    InfoSnapshot,
    MetricsSnapshot,
    PalBoxActor,
)

_TRUE_STRINGS = frozenset({"true", "1", "yes", "on"})


def ci_get(d: Mapping, *keys: str, default: Any = None) -> Any:
    lowered = {str(k).lower(): v for k, v in d.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return default


def str_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in _TRUE_STRINGS
    return False


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def normalize_info(raw: Mapping, now: int) -> InfoSnapshot:
    return InfoSnapshot(
        observed_at=now,
        version=str(ci_get(raw, "version", default="") or ""),
        server_name=str(ci_get(raw, "servername", "server_name", default="") or ""),
        description=str(ci_get(raw, "description", default="") or ""),
        worldguid=str(ci_get(raw, "worldguid", "world_guid", default="") or ""),
    )


def normalize_metrics(raw: Mapping, now: int) -> MetricsSnapshot:
    return MetricsSnapshot(
        observed_at=now,
        fps=_as_float(ci_get(raw, "serverfps", "fps")),
        frame_time=_as_float(ci_get(raw, "serverframetime", "frametime", "frame_time")),
        online=_as_int(ci_get(raw, "currentplayernum", "online", "currentplayers")),
        max_players=_as_int(ci_get(raw, "maxplayernum", "maxplayers", "max_players")),
        uptime=_as_int(ci_get(raw, "uptime")),
        basecamp_count=_as_int(ci_get(raw, "basecampnum", "basecamp_count")),
        days=_as_int(ci_get(raw, "days", "serversdaytime", "world_day")),
    )


def _player_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, Mapping):
        value = ci_get(raw, "players", default=[])
        if isinstance(value, list):
            return value
    return []


def _opt_float(v):
    if v is None or v == "":
        return None
    return _as_float(v)


def normalize_players(raw: Mapping, now: int) -> list[dict]:
    rows: list[dict] = []
    for item in _player_list(raw):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "userId": ci_get(item, "userid", "user_id", default=None),
                "playerId": ci_get(item, "playerid", "player_id", default=None),
                "name": str(ci_get(item, "name", default="") or ""),
                "level": _as_int(ci_get(item, "level", default=0)),
                "ping": _opt_float(ci_get(item, "ping", default=None)),
                "building_count": _as_int(
                    ci_get(item, "building_count", "buildingcount", default=0)
                ),
                "ip": ci_get(item, "ip", default=None),
                "accountName": ci_get(item, "accountname", "account_name", default=None),
            }
        )
    return rows


_UNIT_TYPE_BY_VALUE = {ut.value.lower(): ut for ut in UnitType}


def _parse_unit_type(raw_type) -> UnitType:
    if not raw_type:
        return UnitType.UNKNOWN
    return _UNIT_TYPE_BY_VALUE.get(str(raw_type).lower(), UnitType.UNKNOWN)


def _opt_int(v):
    if v is None or v == "":
        return None
    return _as_int(v)


def _opt_coord(v):
    if v is None or v == "":
        return None
    return _as_float(v)


def _actordata_list(raw: Mapping) -> list:
    """真实响应容器：单一扁平 ActorData 数组（按 item 的 Type 二分）。"""
    value = ci_get(raw, "actordata", "actor_data", default=[])
    return value if isinstance(value, list) else []


def _character_list(raw: Mapping) -> list:
    """防御回退：旧顶层 characters 键（真实响应无此键，保留以兼容旧样本）。"""
    value = ci_get(raw, "characters", "Characters", default=[])
    return value if isinstance(value, list) else []


def _palbox_list(raw: Mapping) -> list:
    """防御回退：旧顶层 palboxes 键（真实响应无此键，保留以兼容旧样本）。"""
    value = ci_get(raw, "palboxes", "PalBoxes", default=[])
    return value if isinstance(value, list) else []


def _register_class_if_unknown(pal_class, meta: MetadataRepository) -> None:
    if pal_class:
        # pal_name 内部对未知 class 登记入 unknown_classes
        meta.pal_name(str(pal_class))


def _is_palbox(item: Mapping) -> bool:
    return str(ci_get(item, "type", default="") or "").strip().lower() == "palbox"


def _build_character(item: Mapping, meta: MetadataRepository) -> CharacterActor:
    pal_class = ci_get(item, "class", "pal_class", default=None)
    _register_class_if_unknown(pal_class, meta)
    return CharacterActor(
        # 类别取 UnitType（真实契约）；type 仅作旧样本回退。ip 绝不读入模型。
        unit_type=_parse_unit_type(ci_get(item, "unittype", "unit_type", "type")),
        instance_id=ci_get(item, "instanceid", "instance_id", default=None),
        nickname=ci_get(item, "nickname", "nick_name", "name", default=None),
        trainer_instance_id=ci_get(
            item, "trainerinstanceid", "trainer_instance_id", default=None
        ),
        trainer_nickname=ci_get(
            item, "trainernickname", "trainer_nickname", default=None
        ),
        player_userid=ci_get(item, "userid", "user_id", default=None),
        level=_opt_int(ci_get(item, "level", default=None)),
        hp=_opt_int(ci_get(item, "hp", default=None)),
        max_hp=_opt_int(ci_get(item, "maxhp", "max_hp", default=None)),
        guild_id=ci_get(item, "guildid", "guild_id", default=None),
        guild_name=ci_get(item, "guildname", "guild_name", default=None),
        pal_class=str(pal_class) if pal_class else None,
        action=meta.action_category(ci_get(item, "action", default=None)),
        ai_action=meta.action_category(
            ci_get(item, "aiaction", "ai_action", default=None)
        ),
        x=_opt_coord(ci_get(item, "locationx", "x", default=None)),
        y=_opt_coord(ci_get(item, "locationy", "y", default=None)),
        z=_opt_coord(ci_get(item, "locationz", "z", default=None)),
        is_active=str_bool(ci_get(item, "isactive", "is_active", default=False)),
    )


def _build_palbox(item: Mapping, meta: MetadataRepository) -> PalBoxActor | None:
    pal_class = ci_get(item, "class", "pal_class", default=None)
    _register_class_if_unknown(pal_class, meta)
    x = ci_get(item, "locationx", "x", default=None)
    y = ci_get(item, "locationy", "y", default=None)
    z = ci_get(item, "locationz", "z", default=None)
    if x in (None, "") or y in (None, "") or z in (None, ""):
        return None
    return PalBoxActor(
        guild_id=ci_get(item, "guildid", "guild_id", default=None),
        guild_name=ci_get(item, "guildname", "guild_name", default=None),
        pal_class=str(pal_class) if pal_class else None,
        x=_as_float(x),
        y=_as_float(y),
        z=_as_float(z),
    )


def normalize_game_data(
    raw: Mapping, now: int, meta: MetadataRepository
) -> GameDataSnapshot:
    characters: list[CharacterActor] = []
    palboxes: list[PalBoxActor] = []

    # 真实容器：扁平 ActorData 数组，按 Type 二分（PalBox → PalBoxActor；否则 Character）。
    for item in _actordata_list(raw):
        if not isinstance(item, Mapping):
            continue
        if _is_palbox(item):
            pb = _build_palbox(item, meta)
            if pb is not None:
                palboxes.append(pb)
        else:
            characters.append(_build_character(item, meta))

    # 防御回退：旧顶层 characters/palboxes 样本（真实响应无此二键；追加不删）。
    for item in _character_list(raw):
        if isinstance(item, Mapping):
            characters.append(_build_character(item, meta))
    for item in _palbox_list(raw):
        if isinstance(item, Mapping):
            pb = _build_palbox(item, meta)
            if pb is not None:
                palboxes.append(pb)

    return GameDataSnapshot(
        observed_at=now,
        fps=_as_float(ci_get(raw, "serverfps", "fps")),
        average_fps=_as_float(ci_get(raw, "averagefps", "average_fps")),
        characters=characters,
        palboxes=palboxes,
        unknown_classes=meta.take_unknown_classes(),
        in_game_days=_as_int(ci_get(raw, "ingamedays", "in_game_days", default=0)),
        in_game_time=str(ci_get(raw, "ingametime", "in_game_time", default="") or ""),
    )
