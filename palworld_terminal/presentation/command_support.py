from __future__ import annotations

import functools

from ..application.routing_service import RoutingError
from ..presentation.locale import L
from ..shared.command_permissions import effective_enabled, upstream_unavailable
from ..shared.command_registry import METHOD_PATH


def feature_disabled_text(path: str) -> str:
    """feature_disabled 回执（spec §3 横切决策表）：主句恒戴 ⚠️（配置停用类）。

    普通 enable off 追加「设置页开启」引导脚注；upstream_unavailable(path) 时省略脚注
    ——设置页开不了该上游不可用功能，脚注是假承诺。当前 UPSTREAM_UNAVAILABLE_FEATURES
    为空集（game-data 已解禁），该分支休眠恒不触发；若未来再锁某 feature 即自动恢复
    省略。全部 feature_disabled 落点（_gated / _dispatch_read / link / admin_write）经此
    渲染，条件脚注收于单一真相源。
    """
    if upstream_unavailable(path):
        return L("feature_disabled")
    return f"{L('feature_disabled')}\n{L('feature_disabled_hint')}"


def _render_routing_error(err: RoutingError | None, params: dict | None) -> str:
    """RoutingError → 本地化串（presentation 边界；err=None → 空串）。

    逐字复现原 routing 内联 L(key, **params) 输出：枚举值即 locale key，
    error_params 即模板填充参数。
    """
    return L(err.value, **(params or {})) if err is not None else ""


def _gated(fn):
    """命令 gating：按方法名查 METHOD_PATH 得完整路径，查该路径生效值（组键/叶子/默认
    三级继承），未启用则回 feature_disabled、不触达底层（spec §5）。
    METHOD_PATH 须覆盖全部 @_gated 方法，否则此处 KeyError（meta 测试防回归）。
    """
    @functools.wraps(fn)
    async def wrapper(self, *args, **kwargs):
        path = METHOD_PATH[fn.__name__]
        if not effective_enabled(self._cfg.permissions.command_overrides, path):
            return feature_disabled_text(path)
        return await fn(self, *args, **kwargs)
    return wrapper


# 分发到需 sender_id 的实现方法（组内仅 player 用 bind/unbind_self）——分发器据此
# 决定传参形态。其余读实现签名为 (umo, message_str, is_group)。
_SENDER_METHODS = frozenset({"bind", "me", "unbind_self"})


def _world_mode(cfg) -> str:
    """真实 AppConfig 恒有 routing.world_mode；默认 multi 兼容不完整测试替身。"""
    return getattr(getattr(cfg, "routing", None), "world_mode", "multi")


def _fold_limit(cfg) -> int:
    """列表折叠上限（spec §2.7）：全部列表 formatter 共用 cfg.players.list_fold_limit
    单一真相源；测试替身缺 cfg/players 时回默认 7。"""
    if cfg is None:
        return 7
    return getattr(getattr(cfg, "players", None), "list_fold_limit", 7)
