"""数据路由 — QMT 连接状态、本地缓存管理、数据下载与质量检查"""

import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from backend.config import settings
from backend.services import data_download, market_data, reference_data
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


class BatchDownloadRequest(BaseModel):
    """批量下载：sector 与 symbols 二选一（sector 优先，展开成分股）"""

    sector: str = ""
    symbols: list[str] = []
    period: str = "1d"
    start_date: str = ""
    end_date: str = ""


class FundamentalSnapshotRequest(BaseModel):
    """财务数据快照（公告日点位，防前视）"""

    codes: list[str] = []  # 空=自动取已缓存品种


@router.post("/snapshot-fundamental")
async def snapshot_fundamental(req: FundamentalSnapshotRequest):
    """拉取财务数据（Pershareindex/Income/Balance/CostCapital，报告公告时点）并落盘.

    供 fund_* 因子使用；无 QMT 时返回明确跳过信息。
    """
    from backend.data.qmt_client import QMTClient
    from backend.services import fundamental

    qmt = QMTClient()
    if not qmt.connected:
        raise HTTPException(status_code=400, detail="QMT 未连接，无法下载财务数据")
    codes = req.codes or market_data.list_cached_codes("1d")
    if not codes:
        raise HTTPException(status_code=400, detail="无待快照品种，请指定 codes 或先下载行情")
    try:
        records = await run_in_threadpool(fundamental.snapshot_fundamental, qmt, codes)
    except Exception as e:  # noqa: BLE001
        logger.error(f"财务快照失败: {e}")
        raise HTTPException(status_code=500, detail=f"财务快照失败: {e}")
    return {"status": "ok", "codes": len(codes), "records": records}


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


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/download-batch")
async def download_batch(req: BatchDownloadRequest):
    """批量下载行情（SSE 逐只进度）：板块/指数展开或代码列表

    SSE 事件：batch_start / symbol_complete / symbol_failed /
            reference_saved / batch_complete / batch_failed
    """
    if req.sector:
        try:
            codes = data_download.expand_sector(req.sector)
        except (ConnectionError, ValueError) as e:
            raise HTTPException(status_code=503, detail=str(e))
    else:
        codes = [s.strip() for s in req.symbols if s.strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="未指定板块或代码列表")

    return StreamingResponse(
        data_download.batch_download_stream(
            codes,
            period=req.period,
            start_date=req.start_date,
            end_date=req.end_date,
            sector=req.sector,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/update-cached")
async def update_cached(period: str = "1d"):
    """一键补齐：已缓存品种按各自末日期增量下载至最新（SSE）"""
    codes, per_code_start = data_download.build_update_plan(period)
    if not codes:
        raise HTTPException(status_code=404, detail="本地无缓存品种，无可补齐")

    return StreamingResponse(
        data_download.batch_download_stream(
            codes, period=period, per_code_start=per_code_start
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/coverage")
async def coverage(period: str = "1d"):
    """缓存覆盖度：每只股票的起止日期与条数"""
    entries = market_data.cache_coverage(period)
    return {"period": period, "count": len(entries), "entries": entries}


@router.get("/freshness")
async def data_freshness_endpoint():
    """数据时效检查：最新交易日、滞后天数与显著滞后的标的清单"""
    return market_data.data_freshness()


@router.get("/reference-status")
async def reference_status():
    """参考数据快照现状（成分/行业/股本/合约详情）"""
    return {
        "reference": reference_data.reference_status(),
        "snapshot_indices": reference_data.list_snapshot_indices(),
    }


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

_NEWS_CACHE: dict = {"ts": 0.0, "source": "", "entries": []}
_NEWS_TTL = 60.0
_NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}

# 重大事项关键词（无官方重要标记时的补充信号，如新浪）
_IMPORTANT_KEYWORDS = (
    "涨停",
    "跌停",
    "停牌",
    "复牌",
    "重组",
    "并购",
    "收购",
    "回购",
    "减持",
    "增持",
    "业绩预",
    "中标",
    "分红",
    "解禁",
    "退市",
    "立案",
    "处罚",
    "举牌",
    "重大资产",
)

# 与证券无关的题材（无关联个股且命中时过滤，降低“乱七八糟”噪声）
_IRRELEVANT_KEYWORDS = (
    "地震",
    "台风",
    "暴雨",
    "洪水",
    "山火",
    "车祸",
    "交通事故",
    "坑难",
    "坠机",
    "足球",
    "篮球",
    "比赛",
    "奥运",
    "娱乐",
    "明星",
    "演唱会",
    "电影票房",
    "天气",
    "伤亡",
    "遇难",
    "疫情",
    "地震台",
)


def _is_relevant(title: str, has_stock: bool, important: bool) -> bool:
    """证券相关性：关联个股或官方标重要的一律保留；否则命中无关题材则丢弃"""
    if has_stock or important:
        return True
    return not any(k in title for k in _IRRELEVANT_KEYWORDS)


async def _news_from_eastmoney(client: httpx.AsyncClient) -> list[dict]:
    """东方财富 7×24 快讯

    重要度用官方 titleColor（!=0 为红色重要）——权威信号，避免关键词误红；
    丢弃与证券无关的快讯；附详情 url（finance.eastmoney.com/a/{code}.html）。
    """
    url = (
        "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
        "?client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize=40&req_trace=lq"
    )
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()
    entries = []
    for it in (data.get("data") or {}).get("fastNewsList") or []:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        has_stock = bool(it.get("stockList"))
        # titleColor 为官方红色重要标记（多为 "0"，"3" 等非 0 = 重要）
        color = str(it.get("titleColor") or "0")
        important = color not in ("", "0")
        if not _is_relevant(title, has_stock, important):
            continue
        code = str(it.get("code") or "")
        entries.append(
            {
                "time": (it.get("showTime") or "")[11:16],
                "text": title,
                "important": important,
                "url": f"https://finance.eastmoney.com/a/{code}.html" if code else "",
            }
        )
    return entries


async def _news_from_sina(client: httpx.AsyncClient) -> list[dict]:
    """新浪财经 7×24 直播快讯（无官方重要标记，用关键词补充）"""
    url = (
        "https://zhibo.sina.com.cn/api/zhibo/feed"
        "?page=1&page_size=40&zhibo_id=152&tag_id=0"
    )
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()
    feed = ((data.get("result") or {}).get("data") or {}).get("feed") or {}
    entries = []
    for it in feed.get("list") or []:
        text = (it.get("rich_text") or "").strip().replace("\n", " ")
        if not text:
            continue
        important = any(k in text for k in _IMPORTANT_KEYWORDS)
        if not _is_relevant(text, False, important):
            continue
        entries.append(
            {
                "time": (it.get("create_time") or "")[11:16],
                "text": text,
                "important": important,
                "url": (it.get("docurl") or ""),
            }
        )
    return entries


def _rank_and_dedupe(entries: list[dict]) -> list[dict]:
    """去重 + 优先级分层：重要（个股/重大）置顶，各层内保持原时间倒序"""
    seen: set[str] = set()
    uniq: list[dict] = []
    for e in entries:
        if e["text"] in seen:
            continue
        seen.add(e["text"])
        uniq.append(e)
    return [e for e in uniq if e["important"]] + [e for e in uniq if not e["important"]]


def _news_payload(source: str, entries: list[dict]) -> dict:
    """统一输出：entries（结构化，带重要度）+ items（向后兼容的纯文本）"""
    items = [f"{e['time']} {e['text']}".strip() for e in entries]
    return {"source": source, "entries": entries, "items": items}


@router.get("/news")
async def news():
    """状态栏资讯流：真实快讯源（不可用时返回错误，无任何伪造内容）

    entries: [{time, text, important}] — 重要项置顶，供前端高亮与优先排序；
    items:   ["HH:MM text", ...]       — 向后兼容的纯文本。
    """
    now = time.time()
    if _NEWS_CACHE["entries"] and now - _NEWS_CACHE["ts"] < _NEWS_TTL:
        return _news_payload(_NEWS_CACHE["source"], _NEWS_CACHE["entries"])

    sources = [
        ("eastmoney", _news_from_eastmoney),
        ("sina", _news_from_sina),
    ]
    async with httpx.AsyncClient(timeout=8.0, headers=_NEWS_HEADERS) as client:
        for source, fetcher in sources:
            try:
                entries = _rank_and_dedupe(await fetcher(client))
            except Exception as e:
                logger.warning(f"资讯源 {source} 获取失败: {e}")
                continue
            if entries:
                _NEWS_CACHE.update({"ts": now, "source": source, "entries": entries})
                return _news_payload(source, entries)

    # 全部失败：若有旧缓存则降级返回（仍是真实数据），否则明确报错
    if _NEWS_CACHE["entries"]:
        payload = _news_payload(_NEWS_CACHE["source"], _NEWS_CACHE["entries"])
        payload["stale"] = True
        return payload
    return {
        "source": "",
        "entries": [],
        "items": [],
        "error": "资讯源不可用（网络受限或接口变更）",
    }
