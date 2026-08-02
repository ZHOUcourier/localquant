"""FastAPI 后端入口"""

from contextlib import asynccontextmanager

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from loguru import logger

from backend.config import settings
from backend.database import init_db


def _allowed_origins() -> list[str]:
    """本地默认来源；可用 env ALLOWED_ORIGINS（逗号分隔）覆盖以支持跨机器访问"""
    env = getattr(settings, "allowed_origins", "") or ""
    if env.strip():
        return [o.strip() for o in env.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {settings.project_name} v{settings.version}")
    await init_db()
    logger.info("Database initialized")

    # 加载插件
    from backend.plugins.loader import load_all_nodes

    load_all_nodes()
    logger.info("Plugins loaded")

    # 启动 ComfyUI 执行队列 worker（真队列语义）
    from backend.comfy.queue_manager import comfy_queue

    comfy_queue.start()
    logger.info("ComfyUI queue worker started")

    # 启动每日批处理调度协程（非阻塞）
    if getattr(settings, "scheduler_enabled", True):
        from backend.services.scheduler import scheduler_loop

        _scheduler_task = asyncio.create_task(scheduler_loop())
        logger.info("Daily scheduler started")

    yield

    # Shutdown
    logger.info("Shutting down")


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    lifespan=lifespan,
)

# CORS — 本工具面向本机单用户，仅放行本地前端来源；不用通配符，避免同源保护被禁用。
# 如需跨机器访问，请在启动前显式配置 ALLOWED_ORIGINS（逗号分隔）并自行承担鉴权缺失风险。
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
from backend.routes import (
    ai,
    backtest,
    data,
    experiment,
    explorer,
    factor,
    plugins,
    qube,
    strategy,
    system,
    workflow,
)
from backend.routes import (
    ops,
    risk,
)
from backend.routes import (
    settings as settings_routes,
)

app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])
app.include_router(plugins.router, prefix="/api/plugins", tags=["plugins"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(explorer.router, prefix="/api/explorer", tags=["explorer"])
app.include_router(factor.router, prefix="/api/factor", tags=["factor"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(experiment.router, prefix="/api/experiment", tags=["experiment"])
app.include_router(settings_routes.router, prefix="/api/config", tags=["config"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(qube.router, prefix="/api/qube", tags=["qube"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(ops.router, prefix="/api/ops", tags=["ops"])

# ComfyUI 协议适配层 + 官方前端托管（/comfy/api/* + /comfy/ws + /comfy/）
from backend.comfy.routes import mount_comfy

mount_comfy(app)


@app.get("/", include_in_schema=False)
async def root():
    """后端根路径跳转到 API 文档，避免访问 8000 端口时误以为服务未启动"""
    return RedirectResponse(url="/docs")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": settings.version}
