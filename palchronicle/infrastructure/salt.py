"""HMAC secret salt 的生成与持久化（spec §4.1）。

首次运行生成 32 字节随机 salt 写盘并复用；POSIX 收敛 0600。
永不写入日志/数据库/配置。
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

_SALT_FILENAME = "secret_salt"


def load_or_create_salt(data_dir: Path) -> bytes:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / _SALT_FILENAME
    if path.exists():
        return path.read_bytes()
    salt = secrets.token_bytes(32)
    # 先以 0600 打开再写，避免生成瞬间的宽权限窗口（POSIX）。
    # O_BINARY（Windows）避免文本模式把 salt 里的 0x0A 翻译成 0x0D0A 而损坏二进制。
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, salt)
    finally:
        os.close(fd)
    if os.name == "posix":
        os.chmod(path, 0o600)
    return salt
