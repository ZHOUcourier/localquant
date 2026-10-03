"""设置路由 — 读取/写入配置（密钥存 OS 凭据库，其余写 .env），供前端设置页持久化"""

from pathlib import Path

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from backend.config import settings
from backend.secrets import SECRET_FIELDS, is_available, store_secret

router = APIRouter()

ENV_FILE = Path(".env")

# 允许通过设置页修改的配置项（.env 键名 → Settings 属性名）
EDITABLE_KEYS = {
    "QMT_PATH": "qmt_path",
    "QMT_DATA_DIR": "qmt_data_dir",
    "OPENAI_API_KEY": "openai_api_key",
    "OPENAI_BASE_URL": "openai_base_url",
    "AI_PROVIDER": "ai_provider",
    "AI_MODEL": "ai_model",
    "AI_EFFORT": "ai_effort",
    "AI_ENGINE": "ai_engine",
    "AI_CLI": "ai_cli",
    "AI_CLI_MODEL": "ai_cli_model",
    "AI_CLI_EFFORT": "ai_cli_effort",
    "QZ_ACCESS_KEY": "qz_access_key",
    "QZ_SIGN_SECRET": "qz_sign_secret",
    "BACKEND_PORT": "backend_port",
    "FRONTEND_PORT": "frontend_port",
}


class ConfigUpdate(BaseModel):
    qmt_path: str | None = None
    qmt_data_dir: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_effort: str | None = None
    ai_engine: str | None = None
    ai_cli: str | None = None
    ai_cli_model: str | None = None
    ai_cli_effort: str | None = None
    qz_access_key: str | None = None
    qz_sign_secret: str | None = None
    backend_port: int | None = None
    frontend_port: int | None = None


@router.get("/")
async def get_config():
    """返回当前生效配置（永不回显密钥：只返回 *_set 布尔，不返回明文/掩码）"""
    return {
        "qmt_path": settings.qmt_path,
        "qmt_data_dir": settings.qmt_data_dir,
        "openai_api_key_set": bool(settings.openai_api_key),
        "openai_base_url": settings.openai_base_url,
        "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model,
        "ai_effort": settings.ai_effort,
        "ai_engine": settings.ai_engine,
        "ai_cli": settings.ai_cli,
        "ai_cli_model": settings.ai_cli_model,
        "ai_cli_effort": settings.ai_cli_effort or "default",
        "qz_access_key_set": bool(settings.qz_access_key),
        "qz_sign_secret_set": bool(settings.qz_sign_secret),
        # 密钥存储后端：os_keychain=系统凭据库 / env_file=回退 .env
        "secrets_backend": "os_keychain" if is_available() else "env_file",
        "backend_port": settings.backend_port,
        "frontend_port": settings.frontend_port,
        "data_dir": str(settings.data_dir),
        "cache_dir": str(settings.cache_dir),
        "database_url": settings.database_url,
        "version": settings.version,
    }


@router.put("/")
async def update_config(body: ConfigUpdate):
    """更新配置：密钥优先存 OS 凭据库（不可用回退 .env），其余写 .env；同步内存 settings"""
    updates: dict[str, str] = {}
    secret_updates: dict[str, str] = {}
    for env_key, attr in EDITABLE_KEYS.items():
        value = getattr(body, attr)
        if value is None:
            continue
        if env_key in SECRET_FIELDS:
            # 密钥：空串视为不修改（凭据库无法表达空值），其余存凭据库不落盘
            if str(value).strip():
                secret_updates[env_key] = str(value)
                setattr(settings, attr, str(value))
            continue
        updates[env_key] = str(value)
        # 同步内存配置，路径/AI 类配置即时生效
        setattr(settings, attr, type(getattr(settings, attr))(value))

    for env_key, value in secret_updates.items():
        if not store_secret(env_key, value, ENV_FILE):
            # 凭据库不可用/写入失败 → 回退 .env 明文（与既有行为一致）
            updates[env_key] = value

    if updates:
        _write_env(updates)
    if secret_updates:
        fallback = [k for k in secret_updates if k in updates]
        logger.info(
            f"密钥已更新: {', '.join(secret_updates.keys())}"
            + (f"；{', '.join(fallback)} 回退 .env" if fallback else "（存系统凭据库）")
        )

    return {"ok": True, "updated": sorted(set(updates) | set(secret_updates))}


def _write_env(updates: dict[str, str]) -> None:
    """就地更新 .env 中的键值，保留未涉及的行与注释；不存在的键追加到末尾"""
    sanitized: dict[str, str] = {}
    for key, value in updates.items():
        # 清洗换行/回车/空字节等，防止通过配置值注入新的 env 键或控制字符
        cleaned = "".join(ch for ch in str(value) if ch not in "\r\n\x00")
        sanitized[key] = cleaned

    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

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

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
