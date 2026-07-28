"""数据路由"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from backend.services.duckdb_service import DuckDBService

router = APIRouter()

_duckdb = DuckDBService()


class QueryRequest(BaseModel):
    sql: str
    params: Optional[list] = None


@router.get("/status")
async def data_status():
    return {}


@router.post("/download")
async def download_data():
    pass


@router.get("/sectors")
async def get_sectors():
    return []


@router.get("/stocks")
async def get_stocks():
    return []


@router.post("/quality-check")
async def quality_check():
    pass


@router.post("/query-local")
async def query_local(req: QueryRequest):
    """使用 DuckDB 执行 SQL 查询本地 Parquet 数据"""
    return _duckdb.query_local(req.sql, req.params)
