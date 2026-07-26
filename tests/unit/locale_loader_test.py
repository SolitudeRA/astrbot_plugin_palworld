"""locale 装载器 + fallback 链 + MESSAGES 恒驻契约（i18n Phase 1 · Task 1）。"""
import logging

from palworld_terminal.presentation import locale
from palworld_terminal.presentation.locale import MESSAGES, L, load_locale


def test_load_zh_cn_matches_pre_migration_verbatim():
    # zh-CN.json 逐字迁自旧 MESSAGES：装载后取值与迁移前一致。
    load_locale("zh-CN")
    assert L("busy") == "⚠️ 插件正在重载配置，请稍后重试"
    assert L("degraded", minutes=5) == "🔴 当前无法获取世界数据 · 最后成功于 5 分钟前"


def test_unknown_locale_falls_back_to_zh_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="palworld_terminal.locale"):
        load_locale("nonsense")
    # 回落 zh-CN：取值仍为中文基线。
    assert L("busy") == "⚠️ 插件正在重载配置，请稍后重试"
    # 唯一告警点触发一次 warning。
    assert any(
        r.levelno == logging.WARNING and "nonsense" in r.getMessage()
        for r in caplog.records
    )


def test_missing_key_returns_key_itself_without_raising():
    # 缺键 fallback 链末端返回 key 本身，永不抛。
    assert L("no_such_key") == "no_such_key"


def test_missing_key_empty_kwargs_still_no_raise():
    # 缺键即便带 kwargs 也不抛（key 本身无占位符，format 无副作用）。
    assert L("still_missing", foo="bar") == "still_missing"


def test_messages_stays_zh_baseline_after_load_other_locale():
    # MESSAGES 恒驻 zh 基线：load_locale 只重绑私有 _ACTIVE，MESSAGES 永不变。
    baseline = dict(MESSAGES)
    load_locale("en")  # en.json 尚未存在 → 回落，但无论如何 MESSAGES 不应变
    assert MESSAGES == baseline
    assert MESSAGES["busy"] == "⚠️ 插件正在重载配置，请稍后重试"
    # 公开名 MESSAGES 与模块属性同一对象（未被重绑）。
    assert locale.MESSAGES is MESSAGES


def test_active_prefers_current_locale_then_falls_to_messages(caplog):
    # _ACTIVE 缺键时经 MESSAGES(zh) 兜底：装载一个回落到 zh 的 locale 后，
    # 任何 zh 键仍可取到（此处 _ACTIVE 已是 zh 基线，直接命中）。
    load_locale("also_missing")
    assert L("no_server_configured") == MESSAGES["no_server_configured"]
