"""数据路由 — QMT 连接状态、本地缓存管理、数据下载与质量检查"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from backend.config import settings
from backend.services import market_data
from backend.services.duckdb_service import DuckDBService

router = APIRouter()

_duckdb = DuckDBService()


class QueryRequest(BaseModel):
    sql: str
    params: Optional[list] = None


class DownloadRequest(BaseModel):
    symbol: str
    period: str = "1d"
    start_date: str = ""
    end_date: str = ""


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.2f} GB"
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


@router.get("/status")
async def data_status():
    """QMT 连接状态 + 本地缓存统计（真实数据，无占位值）"""
    qmt_status = market_data._qmt.check_connection()
    cache_stats = market_data._cache.cache_status()

    total_records = 0
    try:
        import pyarrow.parquet as pq

        for period_dir in settings.cache_dir.iterdir():
            if not period_dir.is_dir():
                continue
            for f in period_dir.glob("*.parquet"):
                total_records += pq.ParquetFile(f).metadata.num_rows
    except Exception as e:
        logger.warning(f"统计缓存记录数失败: {e}")

    return {
        "qmt_connected": qmt_status["connected"],
        "qmt_message": qmt_status["message"],
        "qmt_path": settings.qmt_path,
        "qmt_data_dir": settings.qmt_data_dir,
        "cache_count": cache_stats["total_files"],
        "cache_size": _format_size(cache_stats["total_size_bytes"]),
        "total_records": total_records,
        "by_period": cache_stats["by_period"],
    }


@router.post("/download")
async def download_data(req: DownloadRequest):
    """从 QMT 下载行情数据并写入本地缓存；QMT 未连接时返回明确错误"""
    qmt = market_data._qmt
    if not qmt.connected:
        raise HTTPException(
            status_code=503,
            detail="QMT 未连接，无法下载数据 — xtquant 仅 Windows 可用，"
            "请在安装了 QMT 客户端的环境中运行后端",
        )

    start = req.start_date.replace("-", "")
    end = req.end_date.replace("-", "")
    try:
        qmt.download_history(
            [req.symbol], period=req.period, start_time=start, end_time=end
        )
        data = qmt.get_kline(
            [req.symbol], period=req.period, start_time=start, end_time=end
        )
        df = data.get(req.symbol)
        if df is None or df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"QMT 未返回 {req.symbol} 的数据，请检查代码与日期区间",
            )
        merged = market_data._cache.get_or_append(req.symbol, req.period, df)
        return {
            "status": "ok",
            "symbol": req.symbol,
            "period": req.period,
            "rows": len(merged),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"数据下载失败: {e}")
        raise HTTPException(status_code=500, detail=f"数据下载失败: {e}")


@router.get("/sectors")
async def get_sectors():
    qmt = market_data._qmt
    if not qmt.connected:
        return []
    return qmt.get_sector_list()


@router.get("/stocks")
async def get_stocks():
    """返回本地已缓存的股票代码列表"""
    return market_data.list_cached_codes()


@router.post("/quality-check")
async def quality_check():
    """检查本地缓存数据完整性：空文件、缺失值、重复索引"""
    import pandas as pd

    issues: list[str] = []
    checked = 0

    if not settings.cache_dir.exists():
        return {"passed": True, "issues": [], "summary": "本地无缓存数据，无可检查项"}

    for period_dir in sorted(settings.cache_dir.iterdir()):
        if not period_dir.is_dir():
            continue
        for f in sorted(period_dir.glob("*.parquet")):
            checked += 1
            name = f"{period_dir.name}/{f.stem}"
            try:
                df = pd.read_parquet(f)
            except Exception as e:
                issues.append(f"{name}: 文件损坏，无法读取 ({e})")
                continue
            if df.empty:
                issues.append(f"{name}: 数据为空")
                continue
            dup = int(df.index.duplicated().sum())
            if dup > 0:
                issues.append(f"{name}: 存在 {dup} 条重复索引")
            if "close" in df.columns:
                na = int(df["close"].isna().sum())
                if na > 0:
                    issues.append(f"{name}: close 列存在 {na} 个缺失值")

    if checked == 0:
        return {"passed": True, "issues": [], "summary": "本地无缓存数据，无可检查项"}

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "summary": f"已检查 {checked} 个缓存文件，发现 {len(issues)} 个问题",
    }


@router.post("/query-local")
async def query_local(req: QueryRequest):
    """使用 DuckDB 执行 SQL 查询本地 Parquet 数据"""
    return _duckdb.query_local(req.sql, req.params)
