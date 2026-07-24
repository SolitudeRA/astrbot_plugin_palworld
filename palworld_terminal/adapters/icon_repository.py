"""元素图标加载器：启动 load() 按 Element 枚举名 allowlist 读元素 SVG。

放 adapters（文件 I/O 归属钉死；import-linter 抓不到文件读写，故层归属靠约定 +
container 装配保证）。container 按包位置解析目录（assets/element-icons），load() 后把
dict[element→SVG串] 注入 Commands，presentation 只消费注入好的 dict → presentation↛adapters
天然闭合。

红线：按 `Element` 枚举名精确取 9 个 `<element>.svg`，**绝不 glob 目录**——目录含
`elements-preview.html`/`elements-preview.png`，glob 会把它们读进来污染/破版。缺文件 →
降级（该元素无图标），供渲染层 fallback emoji。
"""
from __future__ import annotations

from pathlib import Path

from ..domain.enums import Element


class IconRepository:
    def __init__(self, icon_dir: Path) -> None:
        self._dir = Path(icon_dir)
        self._icons: dict[str, str] = {}

    def load(self) -> None:
        """按 Element 枚举 allowlist 逐个读 <element>.svg；缺文件静默降级。"""
        icons: dict[str, str] = {}
        for element in Element:
            key = element.value  # fire/water/.../neutral
            path = self._dir / f"{key}.svg"
            try:
                icons[key] = path.read_text(encoding="utf-8")
            except OSError:
                continue  # 缺文件/不可读 → 降级缺席（渲染层 fallback emoji）
        self._icons = icons

    def icons(self) -> dict[str, str]:
        """element → SVG 串（仅含成功读到的元素）。"""
        return self._icons

    def get(self, element: str | None) -> str | None:
        if not element:
            return None
        return self._icons.get(element)
