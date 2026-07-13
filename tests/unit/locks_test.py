import asyncio

from palworld_terminal.domain.enums import EndpointName
from palworld_terminal.infrastructure.locks import EndpointLocks


async def test_inflight_acquires_when_free():
    locks = EndpointLocks(max_concurrency=6)
    async with locks.inflight("s1", EndpointName.METRICS) as acquired:
        assert acquired is True


async def test_inflight_skips_when_same_endpoint_busy():
    locks = EndpointLocks(max_concurrency=6)
    order = []

    async def first():
        async with locks.inflight("s1", EndpointName.METRICS) as acquired:
            order.append(("first", acquired))
            await asyncio.sleep(0.05)

    async def second():
        await asyncio.sleep(0.01)  # 确保 first 已占用
        async with locks.inflight("s1", EndpointName.METRICS) as acquired:
            order.append(("second", acquired))

    await asyncio.gather(first(), second())
    assert ("first", True) in order
    assert ("second", False) in order


async def test_inflight_independent_per_server_and_endpoint():
    locks = EndpointLocks(max_concurrency=6)

    async def hold(server, endpoint, results):
        async with locks.inflight(server, endpoint) as acquired:
            results.append(acquired)
            await asyncio.sleep(0.02)

    results = []
    await asyncio.gather(
        hold("s1", EndpointName.METRICS, results),
        hold("s1", EndpointName.PLAYERS, results),
        hold("s2", EndpointName.METRICS, results),
    )
    assert results == [True, True, True]


async def test_lock_released_after_context():
    locks = EndpointLocks(max_concurrency=6)
    async with locks.inflight("s1", EndpointName.INFO) as a1:
        assert a1 is True
    async with locks.inflight("s1", EndpointName.INFO) as a2:
        assert a2 is True


async def test_semaphore_uses_max_concurrency():
    locks = EndpointLocks(max_concurrency=3)
    assert isinstance(locks.semaphore, asyncio.Semaphore)
    assert locks.semaphore._value == 3
