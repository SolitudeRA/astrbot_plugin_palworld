from __future__ import annotations

from ..domain.models import ObservedSpecies
from ..infrastructure.database import Database


class _DexRepo:
    """observed_species 表族：服务器图鉴地基——永久累积「曾被观测到」的帕鲁物种。

    不 prune、不随 purge_server_data 清（永久累积口径：曾观测过即永久点亮）。
    first_seen_name 由调用方（snapshot_service）钉死为明文名、严禁回退 id，本层
    仅忠实存取——首见时刻/明文名一经写入即钉死，二次观测仅自增 observe_count。"""

    _db: Database

    async def upsert_observed_species(
        self,
        species_class: str,
        species_name: str,
        element: str,
        now: int,
        first_seen_name: str | None,
    ) -> None:
        await self._db.execute_write(
            """
            INSERT INTO observed_species
                (species_class, species_name, element,
                 first_seen_at, first_seen_name, observe_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(species_class) DO UPDATE SET
                species_name = excluded.species_name,
                element = excluded.element,
                observe_count = observe_count + 1
            """,
            (species_class, species_name, element, now, first_seen_name),
        )

    async def observed_species(self) -> list[ObservedSpecies]:
        rows = await self._db.query(
            """
            SELECT species_class, species_name, element,
                   first_seen_at, first_seen_name, observe_count
            FROM observed_species ORDER BY species_class ASC
            """
        )
        return [
            ObservedSpecies(
                r["species_class"], r["species_name"], r["element"],
                r["first_seen_at"], r["first_seen_name"], r["observe_count"],
            )
            for r in rows
        ]
