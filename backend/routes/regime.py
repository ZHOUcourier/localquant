"""市场环境路由 — 宽基状态 / 风格轮动 / 市场综合判定"""

from fastapi import APIRouter

from backend.services import regime

router = APIRouter()


@router.get("/overview")
async def regime_overview():
    """市场环境总览：宽基趋势状态 + 风格轮动 + 市场综合判定（15 分钟缓存）"""
    return regime.market_regime()


@router.get("/freshness")
async def regime_freshness():
    """指数缓存时效"""
    return regime.regime_freshness()
