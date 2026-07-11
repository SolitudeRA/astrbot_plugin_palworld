def test_all_phase1_public_symbols_importable():
    from palchronicle import __version__
    from palchronicle.adapters.palworld_rest import PalworldRestClient, RestResponse
    from palchronicle.adapters.sqlite_repository import Repository
    from palchronicle.config import AppConfig, parse_config
    from palchronicle.domain.enums import AccessMode, EndpointName
    from palchronicle.domain.models import World
    from palchronicle.infrastructure.cache import TTLCache
    from palchronicle.infrastructure.clock import Clock, FakeClock, SystemClock
    from palchronicle.infrastructure.database import Database
    from palchronicle.infrastructure.locks import EndpointLocks
    from palchronicle.infrastructure.migrations import (
        MIGRATIONS,
        MigrationError,
        apply_migrations,
    )
    from palchronicle.infrastructure.salt import load_or_create_salt

    assert __version__ == "0.1.0"
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
