"""aiosqlite 连接封装：单写连接(写锁) + 只读连接，WAL 使多读单写生效。"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: Path) -> None:
        self._path = str(path)
        self._write_conn: aiosqlite.Connection | None = None
        self._read_conn: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()

    async def open(self) -> None:
        self._write_conn = await aiosqlite.connect(self._path)
        self._write_conn.row_factory = aiosqlite.Row
        # WAL 须在建立读连接前设定，供后续多读单写；foreign_keys 须按连接设定。
        await self._write_conn.execute("PRAGMA journal_mode=WAL")
        await self._write_conn.execute("PRAGMA foreign_keys=ON")
        await self._write_conn.commit()
        self._read_conn = await aiosqlite.connect(self._path)
        self._read_conn.row_factory = aiosqlite.Row
        await self._read_conn.execute("PRAGMA foreign_keys=ON")
        await self._read_conn.commit()

    async def close(self) -> None:
        if self._read_conn is not None:
            await self._read_conn.close()
            self._read_conn = None
        if self._write_conn is not None:
            await self._write_conn.close()
            self._write_conn = None

    @property
    def _wc(self) -> aiosqlite.Connection:
        if self._write_conn is None:
            raise RuntimeError("Database not opened")
        return self._write_conn

    @property
    def _rc(self) -> aiosqlite.Connection:
        if self._read_conn is None:
            raise RuntimeError("Database not opened")
        return self._read_conn

    async def execute_write(self, sql: str, params: Sequence[Any] = ()) -> None:
        async with self.write_lock:
            await self._wc.execute(sql, params)
            await self._wc.commit()

    async def executemany_write(
        self, sql: str, seq: Iterable[Sequence[Any]]
    ) -> None:
        async with self.write_lock:
            await self._wc.executemany(sql, list(seq))
            await self._wc.commit()

    @asynccontextmanager
    async def write_tx(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self.write_lock:
            try:
                yield self._wc
            except BaseException:
                await self._wc.rollback()
                raise
            else:
                await self._wc.commit()

    async def query(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[aiosqlite.Row]:
        cursor = await self._rc.execute(sql, params)
        try:
            return list(await cursor.fetchall())
        finally:
            await cursor.close()
