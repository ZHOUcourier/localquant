"""设置路由 — 读取/写入配置（密钥存 OS 凭据库，其余写 .env），供前端设置页持久化"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import Field, create_model

from backend.config import settings
from backend.config_registry import (
    EDITABLE_SPECS,
    SECRET_FIELDS,
)
from backend.env_file import secure_env_file, update_env_file
from backend.secrets import delete_secret, is_available, store_secret

router = APIRouter()

ENV_FILE = Path(".env")

# 可编辑字段由 config_registry 派生，避免 Settings / 路由 / 前端三处手写漂移
_update_fields: dict = {
    spec.attr: (spec.type | None, None) for spec in EDITABLE_SPECS
}
_update_fields["clear_secrets"] = (list[str], Field(default_factory=list))
ConfigUpdate = create_model("ConfigUpdate", **_update_fields)


@router.get("/")
async def get_config():
    """返回当前生效配置（永不回显密钥：只返回 *_set 布尔，不返回明文/掩码）"""
    data = {
        "secrets_backend": "os_keychain" if is_available() else "env_file",
        "data_dir": str(settings.data_dir),
        "cache_dir": str(settings.cache_dir),
        "database_url": settings.database_url,
        "version": settings.version,
    }
    for spec in EDITABLE_SPECS:
        if spec.secret:
            data[f"{spec.attr}_set"] = bool(getattr(settings, spec.attr))
        else:
            data[spec.attr] = getattr(settings, spec.attr)
    # 固定展示“当前实际生效值”，未在 registry 中登记的历史字段保持兼容
    data["ai_cli_effort"] = settings.ai_cli_effort or "default"
    return data


@router.put("/")
async def update_config(body: ConfigUpdate):
    """更新配置：密钥优先存 OS 凭据库（不可用回退 .env），其余写 .env；同步内存 settings"""
    clear_keys = list(getattr(body, "clear_secrets", []) or [])
    unknown = [k for k in clear_keys if k not in SECRET_FIELDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知密钥键: {', '.join(unknown)}")

    env_updates: dict[str, str] = {}
    memory_updates: dict[str, object] = {}
    secret_updates: dict[str, str] = {}

    for spec in EDITABLE_SPECS:
        if spec.env_key in clear_keys:
            continue
        value = getattr(body, spec.attr, None)
        if value is None:
            continue
        if spec.secret:
            if str(value).strip():
                secret_updates[spec.env_key] = str(value)
            continue
        try:
            coerced = spec.coerce(value)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"{spec.env_key} 配置值不合法: {e}"
            ) from e
        env_updates[spec.env_key] = spec.env_value(coerced)
        memory_updates[spec.attr] = coerced

    cleared: list[str] = []
    for env_key in clear_keys:
        attr = SECRET_FIELDS[env_key]
        delete_secret(env_key, ENV_FILE)
        setattr(settings, attr, "")
        cleared.append(env_key)

    for env_key, value in secret_updates.items():
        if not store_secret(env_key, value, ENV_FILE):
            # 凭据库不可用/写入失败 → 回退 .env 明文
            env_updates[env_key] = value
        else:
            setattr(settings, SECRET_FIELDS[env_key], value)

    if env_updates:
        update_env_file(env_updates, ENV_FILE)
    secure_env_file(ENV_FILE)

    for attr, value in memory_updates.items():
        setattr(settings, attr, value)

    if secret_updates:
        fallback = [k for k in secret_updates if k in env_updates]
        logger.info(
            f"密钥已更新: {', '.join(secret_updates.keys())}"
            + (f"；{', '.join(fallback)} 回退 .env" if fallback else "（存系统凭据库）")
        )
    if cleared:
        logger.info(f"密钥已清除: {', '.join(cleared)}")

    return {
        "ok": True,
        "updated": sorted(set(env_updates) | set(secret_updates) | set(cleared)),
        "cleared": cleared,
    }


def _write_env(updates: dict[str, str]) -> None:
    """兼容旧调用：QUBE 配置路由仍通过这里落 .env。"""
    update_env_file(updates, ENV_FILE)
    secure_env_file(ENV_FILE)
