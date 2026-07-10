import os

from palchronicle.infrastructure.salt import load_or_create_salt


def test_creates_32_byte_salt_file(tmp_path):
    salt = load_or_create_salt(tmp_path)
    assert isinstance(salt, bytes)
    assert len(salt) == 32
    assert (tmp_path / "secret_salt").exists()
    assert (tmp_path / "secret_salt").read_bytes() == salt


def test_reuses_existing_salt(tmp_path):
    first = load_or_create_salt(tmp_path)
    second = load_or_create_salt(tmp_path)
    assert first == second


def test_creates_parent_dir_if_missing(tmp_path):
    nested = tmp_path / "a" / "b"
    salt = load_or_create_salt(nested)
    assert len(salt) == 32
    assert (nested / "secret_salt").exists()


def test_posix_permissions_are_0600(tmp_path):
    if os.name != "posix":
        import pytest

        pytest.skip("POSIX-only permission check")
    load_or_create_salt(tmp_path)
    mode = (tmp_path / "secret_salt").stat().st_mode & 0o777
    assert mode == 0o600
