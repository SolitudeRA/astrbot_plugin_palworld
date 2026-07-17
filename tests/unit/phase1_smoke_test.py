def test_all_phase1_public_symbols_importable():
    from palworld_terminal import __version__
    from palworld_terminal.adapters.palworld_rest import PalworldRestClient, RestResponse
    from palworld_terminal.adapters.sqlite_repository import Repository
    from palworld_terminal.config import AppConfig, parse_config
    from palworld_terminal.domain.enums import AccessMode, EndpointName
    from palworld_terminal.domain.models import World
    from palworld_terminal.infrastructure.cache import TTLCache
    from palworld_terminal.infrastructure.clock import Clock, FakeClock, SystemClock
    from palworld_terminal.infrastructure.database import Database
    from palworld_terminal.infrastructure.locks import EndpointLocks
    from palworld_terminal.infrastructure.migrations import (
        MIGRATIONS,
        MigrationError,
        apply_migrations,
    )
    from palworld_terminal.infrastructure.salt import load_or_create_salt

    assert __version__ == "0.9.9"
    assert callable(parse_config)
    assert callable(apply_migrations)
    assert callable(load_or_create_salt)
    assert len(MIGRATIONS) >= 1
    # 引用各符号避免未使用告警
    assert all(
        s is not None
        for s in (
            PalworldRestClient, RestResponse, Repository, AppConfig,
            AccessMode, EndpointName, World, TTLCache, Clock, FakeClock,
            SystemClock, Database, EndpointLocks, MigrationError,
        )
    )
