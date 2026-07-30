"""数据路由 — QMT 连接状态、本地缓存管理、数据下载与质量检查"""

import time
from typing import Optional

import httpx
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


# ── 底部状态栏：指数行情 ─────────────────────────────────────

# 状态栏展示的指数（QMT 代码）
_TICKER_INDICES: list[tuple[str, str]] = [
    ("上证", "000001.SH"),
    ("深证", "399001.SZ"),
    ("沪深300", "000300.SH"),
    ("中证500", "000905.SH"),
    ("创业", "399006.SZ"),
    ("科创50", "000688.SH"),
]


def _quote_from_qmt(code: str) -> Optional[dict]:
    """从 QMT 实时 tick 快照提取指数报价"""
    qmt = market_data._qmt
    if not qmt.connected:
        return None
    try:
        tick = qmt.get_full_tick([code]).get(code)
        if not tick:
            return None
        last = float(tick.get("lastPrice") or 0)
        prev = float(tick.get("lastClose") or 0)
        if last <= 0 or prev <= 0:
            return None
        return {
            "price": round(last, 2),
            "change": round(last - prev, 2),
            "pct": round((last - prev) / prev * 100, 2),
            "amount": float(tick.get("amount") or 0),
            "source": "qmt",
        }
    except Exception as e:
        logger.warning(f"QMT tick 获取失败 {code}: {e}")
        return None


def _quote_from_cache(code: str) -> Optional[dict]:
    """QMT 不可用时，从本地日线缓存取最近两日收盘价计算涨跌（非实时）"""
    df = market_data._cache.get(code, "1d")
    if df is None or df.empty or "close" not in df.columns or len(df) < 2:
        return None
    closes = df["close"].astype(float).dropna()
    if len(closes) < 2:
        return None
    last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
    amount = 0.0
    if "amount" in df.columns:
        try:
            amount = float(df["amount"].iloc[-1])
        except Exception:
            amount = 0.0
    return {
        "price": round(last, 2),
        "change": round(last - prev, 2),
        "pct": round((last - prev) / prev * 100, 2) if prev else 0.0,
        "amount": amount,
        "date": str(df.index[-1])[:10],
        "source": "cache",
    }


@router.get("/ticker")
async def ticker():
    """底部状态栏行情：QMT 实时优先，未连接时回退本地缓存收盘价；都没有则标记无数据"""
    qmt_connected = market_data._qmt.connected
    quotes = []
    for name, code in _TICKER_INDICES:
        q = _quote_from_qmt(code) or _quote_from_cache(code)
        quotes.append({"name": name, "code": code, **(q or {"source": "none"})})
    return {"qmt_connected": qmt_connected, "quotes": quotes}


# ── 底部状态栏：资讯（真实接口，禁止任何模拟数据） ─────────────────
#
# QMT/xtquant 无资讯接口，改接公开的 7×24 快讯真实源：
#   1. 东方财富快讯 np-listapi.eastmoney.com（优先）
#   2. 新浪财经 7×24 zhibo.sina.com.cn（备选）
# 全部失败时返回明确错误，绝不伪造内容。结果内存缓存 60s，避免频繁外部请求。

_NEWS_CACHE: dict = {"ts": 0.0, "source": "", "items": []}
_NEWS_TTL = 60.0
_NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}


async def _news_from_eastmoney(client: httpx.AsyncClient) -> list[str]:
    """东方财富 7×24 快讯"""
    url = (
        "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
        "?client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize=20&req_trace=lq"
    )
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for it in (data.get("data") or {}).get("fastNewsList") or []:
        title = (it.get("title") or "").strip()
        show_time = (it.get("showTime") or "")[11:16]  # HH:MM
        if title:
            items.append(f"{show_time} {title}" if show_time else title)
    return items


async def _news_from_sina(client: httpx.AsyncClient) -> list[str]:
    """新浪财经 7×24 直播快讯"""
    url = (
        "https://zhibo.sina.com.cn/api/zhibo/feed"
        "?page=1&page_size=20&zhibo_id=152&tag_id=0"
    )
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()
    feed = ((data.get("result") or {}).get("data") or {}).get("feed") or {}
    items = []
    for it in feed.get("list") or []:
        text = (it.get("rich_text") or "").strip().replace("\n", " ")
        create_time = (it.get("create_time") or "")[11:16]  # HH:MM
        if text:
            items.append(f"{create_time} {text}" if create_time else text)
    return items


@router.get("/news")
async def news():
    """状态栏资讯流：真实快讯源，不可用时返回错误（无任何伪造内容）"""
    now = time.time()
    if _NEWS_CACHE["items"] and now - _NEWS_CACHE["ts"] < _NEWS_TTL:
        return {"source": _NEWS_CACHE["source"], "items": _NEWS_CACHE["items"]}

    sources = [
        ("eastmoney", _news_from_eastmoney),
        ("sina", _news_from_sina),
    ]
    async with httpx.AsyncClient(timeout=8.0, headers=_NEWS_HEADERS) as client:
        for source, fetcher in sources:
            try:
                items = await fetcher(client)
            except Exception as e:
                logger.warning(f"资讯源 {source} 获取失败: {e}")
                continue
            if items:
                _NEWS_CACHE.update({"ts": now, "source": source, "items": items})
                return {"source": source, "items": items}

    # 全部失败：若有旧缓存则降级返回（仍是真实数据），否则明确报错
    if _NEWS_CACHE["items"]:
        return {
            "source": _NEWS_CACHE["source"],
            "items": _NEWS_CACHE["items"],
            "stale": True,
        }
    return {
        "source": "",
        "items": [],
        "error": "资讯源不可用（网络受限或接口变更）",
    }
