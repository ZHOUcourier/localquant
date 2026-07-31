"""设置路由 — 读取/写入 .env 配置，供前端设置页持久化"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from backend.config import settings

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
    "FACTOR_SERVICE_URL": "factor_service_url",
    "BACKEND_PORT": "backend_port",
    "FRONTEND_PORT": "frontend_port",
}


class ConfigUpdate(BaseModel):
    qmt_path: Optional[str] = None
    qmt_data_dir: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    ai_effort: Optional[str] = None
    ai_engine: Optional[str] = None
    ai_cli: Optional[str] = None
    factor_service_url: Optional[str] = None
    backend_port: Optional[int] = None
    frontend_port: Optional[int] = None


def _mask_key(key: str) -> str:
    """API Key 脱敏显示"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


@router.get("/")
async def get_config():
    """返回当前生效配置（API Key 脱敏）"""
    return {
        "qmt_path": settings.qmt_path,
        "qmt_data_dir": settings.qmt_data_dir,
        "openai_api_key_masked": _mask_key(settings.openai_api_key),
        "openai_api_key_set": bool(settings.openai_api_key),
        "openai_base_url": settings.openai_base_url,
        "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model,
        "ai_effort": settings.ai_effort,
        "ai_engine": settings.ai_engine,
        "ai_cli": settings.ai_cli,
        "factor_service_url": settings.factor_service_url,
        "backend_port": settings.backend_port,
        "frontend_port": settings.frontend_port,
        "data_dir": str(settings.data_dir),
        "cache_dir": str(settings.cache_dir),
        "database_url": settings.database_url,
        "version": settings.version,
    }


@router.put("/")
async def update_config(body: ConfigUpdate):
    """更新配置：写入 .env 并同步内存中的 settings（端口类修改需重启后端生效）"""
    updates: dict[str, str] = {}
    for env_key, attr in EDITABLE_KEYS.items():
        value = getattr(body, attr)
        if value is None:
            continue
        updates[env_key] = str(value)
        # 同步内存配置，路径/AI 类配置即时生效
        setattr(settings, attr, type(getattr(settings, attr))(value))

    if updates:
        _write_env(updates)
        logger.info(f"配置已更新: {', '.join(updates.keys())}")

    return {"ok": True, "updated": list(updates.keys())}


def _write_env(updates: dict[str, str]) -> None:
    """就地更新 .env 中的键值，保留未涉及的行与注释；不存在的键追加到末尾"""
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
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
