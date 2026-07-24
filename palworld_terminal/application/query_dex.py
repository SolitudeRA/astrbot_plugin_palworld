from __future__ import annotations

from typing import Any, ClassVar

from ..domain.enums import Element
from .dtos import DexElementBucket, DexProgressDTO
from .query_privacy import _PrivacyBase

# 元素分桶定序（spec §8）：domain.Element 九元素在前，末尾附出现过但未收录的元素（如 unknown）。
_ELEMENT_ORDER: tuple[str, ...] = tuple(e.value for e in Element)


class _DexQueries(_PrivacyBase):
    """服务器图鉴查询（dex_progress）。observed_species 为跨插件全局累积（无 world_id，
    spec §4.4）——故 dex_progress() 无 world 参数、口径「本插件已观测」（非本服/全服全部物种）。

    脊柱铁律（复核 A2）：继承 _PrivacyBase，声明所用属性注解（防 mypy attr-defined）。"""

    _meta: Any   # 保留供未来 roster/名解析扩展；隐式 Any，见 query_service 拆分契约

    # 完整物种 roster（species_class → (species_name, element)）：真实 paldex 源未权威确定
    # 完整物种表（metadata_version 0.x，best-effort）→ None → dex **降级**（SD5：分母与缺失
    # 清单绑同一前置一起降级——仅出「已观测 N 种」+ 按元素已点亮列表，不显分母、不出「缺失」）。
    # 未来回填权威完整 roster 后自然启用满态（N/总数 + 按元素缺失）。测试经子类 override 演示满态。
    _species_roster: ClassVar[dict[str, tuple[str, str]] | None] = None

    async def dex_progress(self) -> DexProgressDTO:
        """服务器图鉴进度（spec §8）：已观测**去重**物种数 + 按元素分桶（+ 分母已知时缺失）。

        observed_count = observed_species 行数（PK 去重，**非 observe_count 之和**）。
        分母/缺失同降级（SD5）：_species_roster is None → total=None、各桶 missing 恒空。"""
        observed = await self._repo.observed_species()
        observed_count = len(observed)   # 去重物种行数（非 observe_count 之和）

        lit: dict[str, list[str]] = {}       # 元素 → 已点亮物种名
        lit_classes: set[str] = set()
        for o in observed:
            lit.setdefault(o.element or "unknown", []).append(o.species_name)
            lit_classes.add(o.species_class)

        roster = self._species_roster
        total = len(roster) if roster is not None else None

        # 缺失（仅分母已知）：roster − 已点亮，按 species_class 身份比对（非按名），落各元素桶。
        missing: dict[str, list[str]] = {}
        if roster is not None:
            for cls, (name, elem) in roster.items():
                if cls not in lit_classes:
                    missing.setdefault(elem or "unknown", []).append(name)

        elements = list(_ELEMENT_ORDER)
        for e in sorted(set(lit) | set(missing)):
            if e not in elements:
                elements.append(e)

        buckets: list[DexElementBucket] = []
        for e in elements:
            obs = sorted(lit.get(e, []))
            miss = sorted(missing.get(e, []))
            if not obs and not miss:
                continue   # 空桶（既无点亮亦无缺失）不产出
            buckets.append(DexElementBucket(element=e, observed=obs, missing=miss))

        return DexProgressDTO(observed_count=observed_count, total=total, buckets=buckets)
