from pathlib import Path

from palworld_terminal.container import migrate_legacy_db


def test_legacy_db_renamed_in_place(tmp_path: Path):
    (tmp_path / "palchronicle.sqlite3").write_bytes(b"legacy-data")
    migrate_legacy_db(tmp_path)
    assert not (tmp_path / "palchronicle.sqlite3").exists()
    assert (tmp_path / "palworld_terminal.sqlite3").read_bytes() == b"legacy-data"


def test_wal_shm_companions_migrated_together(tmp_path: Path):
    for suffix in ("", "-wal", "-shm"):
        (tmp_path / f"palchronicle.sqlite3{suffix}").write_bytes(b"x")
    migrate_legacy_db(tmp_path)
    for suffix in ("", "-wal", "-shm"):
        assert not (tmp_path / f"palchronicle.sqlite3{suffix}").exists()
        assert (tmp_path / f"palworld_terminal.sqlite3{suffix}").exists()


def test_existing_new_db_never_overwritten(tmp_path: Path):
    (tmp_path / "palchronicle.sqlite3").write_bytes(b"old")
    (tmp_path / "palworld_terminal.sqlite3").write_bytes(b"new")
    migrate_legacy_db(tmp_path)
    # 新库优先,旧库原样保留(不覆盖、不删除)
    assert (tmp_path / "palworld_terminal.sqlite3").read_bytes() == b"new"
    assert (tmp_path / "palchronicle.sqlite3").read_bytes() == b"old"


def test_noop_when_no_legacy(tmp_path: Path):
    migrate_legacy_db(tmp_path)  # 不抛错
    assert not (tmp_path / "palworld_terminal.sqlite3").exists()


def test_orphan_new_wal_does_not_block_migration(tmp_path: Path):
    # 病态边界:新主库不存在但新 -wal 孤儿已存在(如手工删主库留 WAL)。
    # os.replace 静默覆盖孤儿,迁移不得抛 FileExistsError(Windows rename 会)。
    (tmp_path / "palchronicle.sqlite3").write_bytes(b"old")
    (tmp_path / "palchronicle.sqlite3-wal").write_bytes(b"old-wal")
    (tmp_path / "palworld_terminal.sqlite3-wal").write_bytes(b"orphan")
    migrate_legacy_db(tmp_path)
    assert (tmp_path / "palworld_terminal.sqlite3").read_bytes() == b"old"
    assert (tmp_path / "palworld_terminal.sqlite3-wal").read_bytes() == b"old-wal"
    assert not (tmp_path / "palchronicle.sqlite3").exists()
