"""API 密钥存取 — OS 凭据库（keyring）优先，.env 回退

密钥类配置（OPENAI_API_KEY / QUBE_API_KEY / QZ_* / PANDA_TOKEN）优先存入 OS 凭据库
（macOS Keychain / Windows 凭据管理器 / Linux Secret Service），不落 .env 明文：

- 启动时 ``migrate_env_secrets()`` 把 .env 里的明文密钥一次性迁入凭据库并从 .env
  删除对应行（幂等；先写凭据库成功、后才改 .env）
- 运行时读取：config.py 在 Settings 实例化后用 ``overlay_settings()`` 从凭据库
  回填空缺的密钥字段
- 设置页写入走 ``store_secret()``：凭据库可用则存凭据库并清除 .env 明文；不可用
  （无桌面 Linux / CI / 容器）则由调用方回退为原 .env 写入，行为与从前一致

界面永不回显密钥：配置 GET 接口只返回 ``*_set`` 布尔，不返回明文或掩码。
"""

from pathlib import Path

from loguru import logger

SERVICE = "LocalQuant"

# env 键名 → Settings 属性名（config.Settings 中对应的密钥字段）
SECRET_FIELDS: dict[str, str] = {
    "OPENAI_API_KEY": "openai_api_key",
    "QUBE_API_KEY": "qube_api_key",
    "QZ_ACCESS_KEY": "qz_access_key",
    "QZ_SIGN_SECRET": "qz_sign_secret",
    "PANDA_TOKEN": "panda_token",
}


def is_available() -> bool:
    """OS 凭据库后端是否可用（排除 keyring 的 fail 占位后端）"""
    try:
        import keyring
        from keyring.backends import fail

        return not isinstance(keyring.get_keyring(), fail.Keyring)
    except Exception:
        return False


def get_secret(env_key: str) -> str:
    if not is_available():
        return ""
    try:
        import keyring

        return keyring.get_password(SERVICE, env_key) or ""
    except Exception as e:
        logger.debug(f"读取凭据库 {env_key} 失败: {e}")
        return ""


def set_secret(env_key: str, value: str) -> bool:
    if not is_available():
        return False
    try:
        import keyring

        keyring.set_password(SERVICE, env_key, value)
        return True
    except Exception as e:
        logger.warning(f"写入凭据库 {env_key} 失败: {e}")
        return False


def overlay_settings(settings_obj) -> None:
    """把凭据库中的密钥回填到 Settings 的空缺字段（幂等，可重复调用）"""
    for env_key, attr in SECRET_FIELDS.items():
        if getattr(settings_obj, attr, ""):
            continue
        value = get_secret(env_key)
        if value:
            setattr(settings_obj, attr, value)


def _strip_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def delete_env_key(env_key: str, env_file: Path | None = None) -> bool:
    """从 .env 删除单个键的行（保留其余行与注释）；行不存在返回 False"""
    path = env_file or Path(".env")
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
        if stripped.split("=", 1)[0].strip() == env_key:
            removed = True
            continue
        kept.append(line)
    if removed:
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return removed


def store_secret(env_key: str, value: str, env_file: Path | None = None) -> bool:
    """写入单个密钥：存凭据库并确保 .env 无明文。返回 False 表示凭据库不可用/写入失败，
    调用方应回退为写 .env。空值不写入（清空请直接删凭据库条目）。"""
    if not value or not set_secret(env_key, value):
        return False
    delete_env_key(env_key, env_file)
    return True


def migrate_env_secrets(env_file: Path | None = None) -> list[str]:
    """把 .env 中的明文密钥迁入 OS 凭据库并从 .env 删除（幂等，启动时调用一次）

    返回成功迁移的 env 键名。凭据库不可用或 .env 无密钥时不做任何事；
    单个写入失败时该键保留在 .env，其余已成功的照常清除。
    """
    path = env_file or Path(".env")
    if not is_available() or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    found: dict[int, str] = {}  # 行号 → env 键名（值非空的密钥行）
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        if key in SECRET_FIELDS and _strip_env_value(raw):
            found[i] = key
    if not found:
        return []

    values: dict[str, str] = {}
    for i in found:
        key, _, raw = lines[i].partition("=")
        values[key.strip()] = _strip_env_value(raw)
    migrated: list[str] = []
    for key in dict.fromkeys(found.values()):
        if set_secret(key, values[key]):
            migrated.append(key)
        else:
            logger.warning(f"密钥 {key} 写入 OS 凭据库失败，保留在 .env")
    if not migrated:
        return []

    migrated_set = set(migrated)
    kept = [ln for i, ln in enumerate(lines) if found.get(i) not in migrated_set]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    logger.info(f"已将 {len(migrated)} 个密钥迁入系统凭据库: {', '.join(migrated)}")
    return migrated
