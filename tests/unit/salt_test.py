import os

from palworld_terminal.infrastructure import salt as salt_module
from palworld_terminal.infrastructure.salt import load_or_create_salt


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


def test_write_path_preserves_0x0a_0x0d_bytes(tmp_path, monkeypatch):
    """写路径确定性回归：含 0x0A/0x0D 的 salt 必须原样写盘（依赖 O_BINARY）。

    移除 salt.py 的 O_BINARY 后，Windows 文本模式会把 0x0A 翻成 0x0D0A，
    导致文件 >32 字节且内容不符——该测试在 Windows 上会确定性失败。
    """
    planted = bytes([0x0A, 0x0D, 0x0A, 0x0D]) + bytes(range(28))
    assert len(planted) == 32
    assert 0x0A in planted and 0x0D in planted
    monkeypatch.setattr(salt_module.secrets, "token_bytes", lambda n: planted)

    salt = load_or_create_salt(tmp_path)

    assert salt == planted
    assert (tmp_path / "secret_salt").stat().st_size == 32
    assert (tmp_path / "secret_salt").read_bytes() == planted


def test_read_path_returns_poisoned_bytes_unchanged(tmp_path):
    """读路径确定性回归：预植含 0x0A/0x0D 的文件必须原样读回。"""
    poison = bytes([0x0A, 0x0D, 0x0A]) + b"\x00" * 29
    assert len(poison) == 32
    assert 0x0A in poison and 0x0D in poison
    (tmp_path / "secret_salt").write_bytes(poison)

    salt = load_or_create_salt(tmp_path)

    assert salt == poison
    assert (tmp_path / "secret_salt").read_bytes() == poison
