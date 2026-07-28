"""FastAPI 后端入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from loguru import logger

from backend.config import settings
from backend.database import init_db


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

    yield

    # Shutdown
    logger.info("Shutting down")


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
from backend.routes import (
    backtest,
    data,
    experiment,
    explorer,
    factor,
    plugins,
    workflow,
)

app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])
app.include_router(plugins.router, prefix="/api/plugins", tags=["plugins"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(explorer.router, prefix="/api/explorer", tags=["explorer"])
app.include_router(factor.router, prefix="/api/factor", tags=["factor"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(experiment.router, prefix="/api/experiment", tags=["experiment"])


@app.get("/", include_in_schema=False)
async def root():
    """后端根路径跳转到 API 文档，避免访问 8000 端口时误以为服务未启动"""
    return RedirectResponse(url="/docs")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": settings.version}
