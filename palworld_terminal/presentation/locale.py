from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger("palworld_terminal.locale")

_LOCALES_DIR = Path(__file__).parent / "locales"


def _load_json(locale: str) -> dict[str, str]:
    """按包位置解析 locales/{locale}.json（绝不走 data_dir/CWD）。"""
    path = _LOCALES_DIR / f"{locale}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# 基线：zh-CN 全部措辞在 import 时装载。公开名 MESSAGES 恒驻为 zh 基线，
# 永不随 load_locale 重绑/变异——既是对外契约（多个测试直接 import 断言其内容），
# 也兼作 fallback 层。
MESSAGES: dict[str, str] = _load_json("zh-CN")

# 私有活动语言表；load_locale 重绑此名，L() 优先读它。import 时等同 zh 基线。
_ACTIVE: dict[str, str] = MESSAGES


def load_locale(locale: str) -> None:
    """装载指定语言到 _ACTIVE。

    非法/未知 locale 或文件缺失/损坏 → 回落 zh-CN 基线 + warning
    （唯一校验/回落/告警点）。仅重绑私有 _ACTIVE；MESSAGES（zh 基线）永不变。
    """
    global _ACTIVE
    try:
        _ACTIVE = _load_json(locale)
    except (OSError, ValueError):
        _log.warning("未知或无法装载的 locale「%s」，回落 zh-CN", locale)
        _ACTIVE = MESSAGES


def L(key: str, **kwargs: object) -> str:
    """按 fallback 链取模板：_ACTIVE → MESSAGES(zh) → key 本身，永不抛。

    空串是合法值，故用 `is None` 判缺键而非 truthiness。
    """
    template = _ACTIVE.get(key)
    if template is None:
        template = MESSAGES.get(key)
    if template is None:
        template = key
    return template.format(**kwargs) if kwargs else template
