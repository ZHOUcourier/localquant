"""数据探索路由"""
from fastapi import APIRouter
router = APIRouter()


@router.post("/query")
async def sql_query():
    pass


@router.post("/scan")
async def market_scan():
    pass


@router.post("/cross-section")
async def cross_section():
    pass


@router.post("/anomaly")
async def anomaly_detection():
    pass
