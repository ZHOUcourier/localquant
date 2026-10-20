"""`.env` 文件的安全读写：原子替换、0600 权限、值转义、进程内互斥。

配置写入统一走这里，避免各路由直接 write_text 造成半截文件或明文权限过宽。
注意：锁是进程内锁，适用于当前单进程本地服务；多 worker 部署需换成文件锁。
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path

_LOCK = threading.Lock()
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_./:@+\-=]*$")
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _clean_value(value) -> str:
    return "".join(ch for ch in str(value) if ch not in "\r\n\x00")


def format_env_value(value) -> str:
    cleaned = _clean_value(value)
    if _SAFE_VALUE.fullmatch(cleaned):
        return cleaned
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def ensure_key(key: str) -> str:
    if not _KEY.fullmatch(key or ""):
        raise ValueError(f"非法配置键: {key!r}")
    return key


def secure_env_file(path: Path) -> None:
    """把配置文件权限收敛到仅当前用户可读写（POSIX；Windows 尽力而为）。"""
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except OSError:
        pass


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def write_env_text(path: Path, text: str) -> None:
    """整文件原子写入并收紧权限（仅供迁移等需要保留原始行的场景）。"""
    with _LOCK:
        _atomic_write(path, text)


def update_env_file(updates: dict[str, str], path: Path) -> None:
    """就地更新键值，保留注释与其他行；原子写并收紧权限。"""
    if not updates:
        return
    sanitized = {ensure_key(k): format_env_value(v) for k, v in updates.items()}
    with _LOCK:
        lines: list[str] = []
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
        remaining = dict(sanitized)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                lines[i] = f"{key}={remaining.pop(key)}"
        for key, value in remaining.items():
            lines.append(f"{key}={value}")
        _atomic_write(path, "\n".join(lines) + "\n")


def delete_env_keys(keys: list[str] | set[str] | tuple[str, ...], path: Path) -> bool:
    """删除指定键的所有行；返回是否发生了删除。"""
    wanted = {ensure_key(k) for k in keys}
    if not wanted:
        return False
    with _LOCK:
        if not path.exists():
            return False
        lines = path.read_text(encoding="utf-8").splitlines()
        kept: list[str] = []
        removed = False
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                kept.append(line)
                continue
            if stripped.split("=", 1)[0].strip() in wanted:
                removed = True
                continue
            kept.append(line)
        if removed:
            _atomic_write(path, "\n".join(kept) + "\n")
        return removed
