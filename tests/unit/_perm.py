"""测试用 command_overrides 构造助手（Task 7：门控落点改查命令生效值）。

旧测试基座用 features/_Features(**groups) 表达功能门开关；门控切到 command_overrides
后，用本助手把「功能组开关」翻译成等价的 CommandOverride 生效值（镜像旧默认全开）。
"""
from palworld_terminal.application.command_permissions import (
    COMMAND_META,
    CommandOverride,
    enable_configurable,
)


def overrides(**feat_flags: bool) -> dict[str, CommandOverride]:
    """按功能组开关生成 enable overrides（镜像旧 _Features(**groups)，默认全开）。

    每个可配置命令按其功能组取 feat_flags.get(feat_group, True)，逐路径落 enable——
    危险命令不从组键继承，逐路径写才能与旧「按组开关」等价。
    """
    return {
        path: CommandOverride(enabled=feat_flags.get(m.feat_group, True))
        for path, m in COMMAND_META.items()
        if enable_configurable(path)
    }


def all_on() -> dict[str, CommandOverride]:
    """所有可配置命令 enable=True（镜像旧 features 全开）。"""
    return overrides()
