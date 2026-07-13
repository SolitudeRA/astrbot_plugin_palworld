"""HMAC secret salt 的生成与持久化（spec §4.1）。

首次运行生成 32 字节随机 salt 写盘并复用；POSIX 收敛 0600。
永不写入日志/数据库/配置。写入走临时文件 + os.replace 原子落盘：
中途崩溃不会留下部分写入的盐文件（否则下次静默读回短盐，
全量 HMAC 弱化且玩家标识漂移）。
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

_SALT_FILENAME = "secret_salt"
_SALT_LEN = 32

_log = logging.getLogger("palworld_terminal.salt")


def load_or_create_salt(data_dir: Path) -> bytes:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / _SALT_FILENAME
    if path.exists():
        salt = path.read_bytes()
        if len(salt) == _SALT_LEN:
            return salt
        # 损坏（历史版本写入中途崩溃遗留）：保留现场并重建。
        # 重建意味着全部玩家 HMAC 标识更换、历史关联断裂——必须告警而非静默。
        _log.warning(
            "盐文件损坏（长度 %d ≠ %d），已重建。历史玩家标识将全部更换，"
            "旧数据不再与新标识关联。损坏文件保留为 %s.corrupt",
            len(salt), _SALT_LEN, _SALT_FILENAME,
        )
        os.replace(path, path.with_name(_SALT_FILENAME + ".corrupt"))
    salt = secrets.token_bytes(_SALT_LEN)
    tmp = path.with_name(_SALT_FILENAME + ".tmp")
    # 先以 0600 打开再写，避免生成瞬间的宽权限窗口（POSIX）。
    # O_BINARY（Windows）避免文本模式把 salt 里的 0x0A 翻译成 0x0D0A 而损坏二进制。
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        os.write(fd, salt)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)  # 原子可见：盐文件要么完整要么不存在
    if os.name == "posix":
        os.chmod(path, 0o600)
    return salt
