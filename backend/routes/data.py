"""数据路由 — QMT 连接状态、本地缓存管理、数据下载与质量检查"""

import time

import httpx
import pandas as pd
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
    params: list | None = None


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


class DelistedCodesRequest(BaseModel):
    """退市/历史代码清单（保存即覆盖）"""

    codes: list[str] = []


class ReferenceImportRequest(BaseModel):
    """历史参考快照导入（as-of 指定日期，追加去重）

    QMT 只能提供「当前」成分/行业/名称/两融池，历史 as-of 状态（2015 年
    沪深300 成分、历史上曾 ST 的名称等）无法从行情源回溯。研究员可从已核验
    来源整理历史快照后导入，使 as-of 研究链路覆盖历史区间。

    csv 列约定（含列头）:
      constituents: index_name, code
      industry:     code, industry
      instrument:   code, name(, list_date)
      margin:       code(, pool)
    """

    kind: str
    date: str
    csv: str


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
    except Exception as e:
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
        raw = qmt.get_kline(
            [req.symbol],
            period=req.period,
            start_time=start,
            end_time=end,
            dividend_type="none",
        ).get(req.symbol)
        if raw is None or raw.empty:
            raise HTTPException(
                status_code=404,
                detail=f"QMT 未返回 {req.symbol} 的数据，请检查代码与日期区间",
            )
        df = market_data.normalize_kline_fields(raw)
        back = qmt.get_kline(
            [req.symbol],
            period=req.period,
            start_time=start,
            end_time=end,
            dividend_type="back",
        ).get(req.symbol)
        if back is None or back.empty:
            logger.warning(f"{req.symbol} 后复权数据缺失，adjust_factor 置 1")
            df = df.copy()
            df["adjust_factor"] = 1.0
        else:
            df = market_data._merge_with_factor(
                df, market_data.normalize_kline_fields(back)
            )
        existing = market_data._cache.get(req.symbol, req.period)
        if existing is not None and "adjust_factor" not in existing.columns:
            # 旧版前复权缓存口径不可逆，整体重建（不复权 + adjust_factor 存储）
            market_data._cache.invalidate(req.symbol, req.period)
            merged = df.copy()
        else:
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
    """QMT 板块列表；未连接时返回结构化错误而非静默空列表"""
    qmt = market_data._qmt
    if not qmt.connected:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "qmt_not_connected",
                "message": "QMT 未连接，无法获取板块列表",
                "hint": "xtquant 仅 Windows 可用，请在安装了 QMT 客户端的环境中运行后端",
            },
        )
    return qmt.get_sector_list()


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("/download-batch")
async def download_batch(req: BatchDownloadRequest):
    """批量下载行情（SSE 逐只进度）：板块/指数展开或代码列表

    若目标为全市场板块（如「沪深A股」），自动并入本地「退市/历史代码清单」
    （QMT 板块只含当前在册成分，退市股需手工维护清单才进得了缓存，
    否则全市场研究存在系统性幸存者偏差）。

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

    merged = market_data.merge_delisted_codes(codes)
    if len(merged) > len(codes):
        logger.info(
            f"批量下载并入退市/历史代码清单：{len(merged) - len(codes)} 只"
            f"（{', '.join(merged[len(codes):][:5])}{'…' if len(merged) > len(codes) + 5 else ''}）"
        )

    return StreamingResponse(
        data_download.batch_download_stream(
            merged,
            period=req.period,
            start_date=req.start_date,
            end_date=req.end_date,
            sector=req.sector,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/delisted")
async def get_delisted():
    """读取本地「退市/历史代码清单」（供研究员维护，全市场下载自动并入）"""
    codes = market_data.load_delisted_codes()
    return {"codes": codes, "count": len(codes)}


@router.post("/delisted")
async def set_delisted(req: DelistedCodesRequest):
    """保存「退市/历史代码清单」（整体覆盖）；批量下载全市场板块时自动并入"""
    cleaned = market_data.save_delisted_codes(req.codes)
    return {"codes": cleaned, "count": len(cleaned)}


@router.post("/import-reference")
async def import_reference(req: ReferenceImportRequest):
    """导入历史参考快照（as-of 日期），供指数成分重建/ST 逐日过滤/两融池逐日掩码

    参考数据是「管理性元数据」（成分归属/名称/行业/两融池），非行情来源：
    行情数据仍只来自 QMT。返回本次落盘行数。
    """
    import io

    try:
        df = pd.read_csv(io.StringIO(req.csv), dtype=str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV 解析失败: {e}")
    if df.empty:
        raise HTTPException(status_code=400, detail="CSV 内容为空")
    try:
        rows = await run_in_threadpool(
            reference_data.import_reference_snapshot, req.kind, req.date, df
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"参考快照导入失败: {e}")
        raise HTTPException(status_code=500, detail=f"参考快照导入失败: {e}")
    return {"ok": True, "kind": req.kind, "date": req.date, "rows": rows}


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


@router.get("/dividend-events")
async def dividend_events(
    period: str = "1d",
    days: int = 90,
    limit: int = 50,
):
    """最近除权除息事件清单（adjust_factor 跳变检测）

    研究员据此判断缓存区间是否跨除权事件、复权价口径是否受影响。
    空缓存时返回统一结构化错误。
    """
    codes = market_data.list_cached_codes(period)
    if not codes:
        raise HTTPException(status_code=404, detail=market_data.no_cache_error_detail())
    events = market_data.dividend_events(period=period, days=days, limit=limit)
    return {
        "period": period,
        "count": len(events),
        "events": events,
    }


@router.get("/reference-status")
async def reference_status():
    """参考数据快照现状（成分/行业/股本/合约详情）"""
    return {
        "reference": reference_data.reference_status(),
        "snapshot_indices": reference_data.list_snapshot_indices(),
    }


@router.get("/stocks")
async def get_stocks():
    """返回本地已缓存的股票代码列表

    缓存为空时返回 404 结构化错误（code=no_cached_data + 指引），
    与 load_price_panels 等「数据缺失」语义对齐，避免静默空列表。
    """
    codes = market_data.list_cached_codes()
    if not codes:
        raise HTTPException(status_code=404, detail=market_data.no_cache_error_detail())
    return codes


@router.post("/quality-check")
async def quality_check():
    """检查本地缓存数据完整性：文件、索引、OHLC 自洽、复权因子、停牌/退市、交易日历。

    QMT 连接时用 QMT 交易日历校验缓存中的非交易日 bar；未连接时不做虚假的
    节假日校验，但会基于「全缓存最晚日期」用工作日近似标记长期停牌/退市标的。
    """
    import pandas as pd

    issues: list[str] = []
    checked = 0
    reference_files = 0
    suspended: list[str] = []  # 最新数据远超最新交易日（疑似停牌/退市）
    price_anomalies = 0
    vol_anomalies = 0
    calendar_issues = 0
    calendar_mode = "unavailable"
    global_latest = None

    if not settings.cache_dir.exists():
        return {
            "passed": True,
            "checked_files": 0,
            "reference_files": 0,
            "suspended_count": 0,
            "suspended": [],
            "price_anomalies": 0,
            "vol_anomalies": 0,
            "calendar_issues": 0,
            "calendar_mode": "unavailable",
            "issues": [],
            "summary": "本地无缓存数据，无可检查项",
        }

    try:
        latest_trade = market_data._trading_calendar()
        calendar_mode = market_data.trading_calendar_source() if latest_trade else "unavailable"
        calendar_set = {pd.Timestamp(d) for d in latest_trade} if latest_trade else None
    except Exception:
        latest_trade = None
        calendar_set = None

    for period_dir in sorted(settings.cache_dir.iterdir()):
        if not period_dir.is_dir():
            continue
        # reference/ 是参考元数据快照（行业/成分/合约），与行情数据检查口径不同，
        # 不混入行情文件计数与质量结论。
        if period_dir.name == "reference":
            reference_files = len(list(period_dir.glob("*.parquet")))
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
            try:
                idx = pd.to_datetime(df.index)
                if idx.tz is not None:
                    idx = idx.tz_localize(None)
                df = df.copy()
                df.index = idx.normalize()
            except Exception:
                issues.append(f"{name}: 时间索引无法解析")
                continue
            dup = int(df.index.duplicated().sum())
            if dup > 0:
                issues.append(f"{name}: 存在 {dup} 条重复索引")

            # 交易日历校验：QMT 日历可得时，标记不属于交易日的 bar
            if calendar_set is not None:
                extra = [d for d in df.index if pd.Timestamp(d) not in calendar_set]
                if extra:
                    calendar_issues += len(extra)
                    sample = ", ".join(str(d.date()) for d in extra[:3])
                    issues.append(
                        f"{name}: 存在 {len(extra)} 个非交易日 bar（如 {sample}），"
                        "请检查下载口径是否混入日历日数据"
                    )

            if "close" in df.columns:
                na = int(df["close"].isna().sum())
                if na > 0:
                    issues.append(f"{name}: close 列存在 {na} 个缺失值")
                # 价格异常：负价/零价 + 单日跳变（前复权口径下 >50% 极不正常）
                c = pd.to_numeric(df["close"], errors="coerce")
                if (c <= 0).any():
                    issues.append(f"{name}: 存在非正价格 {int((c <= 0).sum())} 个")
                adj = (
                    df["adjust_factor"].astype(float)
                    if "adjust_factor" in df.columns
                    else pd.Series(1.0, index=df.index)
                )
                if (adj <= 0).any():
                    issues.append(f"{name}: adjust_factor 存在非正值")
                elif len(adj) > 1 and (adj.diff().dropna() < 0).any():
                    issues.append(
                        f"{name}: adjust_factor 出现下降（复权因子应随时间非降），"
                        "请检查不复权/后复权合成口径"
                    )
                if len(adj) > 1:
                    qfq = c * adj / float(adj.iloc[-1])
                    jump = qfq.pct_change().abs()
                    bad = jump[jump > 0.5].dropna()
                    if len(bad):
                        price_anomalies += len(bad)
                        first = str(bad.index[0])[:10]
                        issues.append(
                            f"{name}: 前复权单日跳变 >50% 共 {len(bad)} 次（最近 {first}，"
                            "请确认除权事件是否已由 adjust_factor 正确吸收）"
                        )

            # OHLC 自洽性：high/low 必须包住 open/close（允许浮点误差）
            ohlc_cols = [col for col in ("open", "high", "low", "close") if col in df.columns]
            if {"high", "low"} <= set(ohlc_cols):
                h = pd.to_numeric(df["high"], errors="coerce")
                l = pd.to_numeric(df["low"], errors="coerce")
                bad_hl = int(((h - l) < -1e-8).sum())
                if bad_hl:
                    issues.append(f"{name}: high < low 共 {bad_hl} 处")
                for col in ("open", "close"):
                    if col in df.columns:
                        x = pd.to_numeric(df[col], errors="coerce")
                        bad_h = int((h - x < -1e-8).sum())
                        bad_l = int((x - l < -1e-8).sum())
                        if bad_h:
                            issues.append(f"{name}: high < {col} 共 {bad_h} 处")
                        if bad_l:
                            issues.append(f"{name}: {col} < low 共 {bad_l} 处")

            if "volume" in df.columns:
                v = pd.to_numeric(df["volume"], errors="coerce")
                if (v < 0).any():
                    issues.append(f"{name}: 存在负成交量 {int((v < 0).sum())} 个")
                adv = v.rolling(20).mean()
                spike = v[v > adv * 20].dropna()
                if len(spike):
                    vol_anomalies += len(spike)
                    first = str(spike.index[0])[:10]
                    issues.append(
                        f"{name}: 成交量超过 20 日均量 20 倍的尖峰共 {len(spike)} 次（最近 {first}）"
                    )

            # 记录全缓存最晚数据日，用于无 QMT 日历时的停牌/退市近似判断
            try:
                last_d = pd.Timestamp(df.index[-1]).date()
                global_latest = last_d if global_latest is None else max(global_latest, last_d)
            except Exception:
                pass

            # 疑似停牌/退市：距最新交易日/全缓存最晚日超过 60 个交易日
            if latest_trade or global_latest:
                try:
                    last_d = pd.Timestamp(df.index[-1]).date()
                    if latest_trade:
                        past = [d for d in latest_trade if d <= last_d]
                        gap = len(latest_trade) - 1 - (len(past) - 1)
                    else:
                        gap = len(pd.bdate_range(last_d, global_latest)) - 1
                    if gap > 60:
                        suspended.append(f"{name}（距今 {gap} 个交易日）")
                except Exception:
                    pass

    if checked == 0:
        return {
            "passed": True,
            "checked_files": 0,
            "reference_files": reference_files,
            "suspended_count": 0,
            "suspended": [],
            "price_anomalies": 0,
            "vol_anomalies": 0,
            "calendar_issues": 0,
            "calendar_mode": calendar_mode,
            "issues": [],
            "summary": "本地无行情缓存，无可检查项",
        }

    extras = []
    if suspended:
        extras.append(
            f"疑似停牌/退市 {len(suspended)} 只：{'、'.join(suspended[:8])}"
            f"{'…' if len(suspended) > 8 else ''}（历史回测需确认是否覆盖退市股，避免幸存者偏差）"
        )
    if price_anomalies:
        extras.append(f"价格异常 {price_anomalies} 处")
    if vol_anomalies:
        extras.append(f"量能异常 {vol_anomalies} 处")
    if calendar_issues:
        extras.append(f"非交易日 bar {calendar_issues} 个")
    if calendar_mode != "qmt":
        extras.append(
            "QMT 未连接，交易日历校验不可用；已改用全缓存最晚日期做工作日近似停牌/退市判断"
        )

    return {
        "passed": len(issues) == 0 and not suspended,
        "checked_files": checked,
        "reference_files": reference_files,
        "suspended_count": len(suspended),
        "suspended": suspended,
        "price_anomalies": price_anomalies,
        "vol_anomalies": vol_anomalies,
        "calendar_issues": calendar_issues,
        "calendar_mode": calendar_mode,
        "issues": issues,
        "summary": f"已检查 {checked} 个行情缓存文件，发现 {len(issues)} 个问题"
        + f"（参考快照 {reference_files} 个单独维护）"
        + ("；" + "；".join(extras) if extras else ""),
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


def _quote_from_qmt(code: str) -> dict | None:
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


def _cache_quote_fresh(latest_date: str) -> bool:
    """缓存行情是否新鲜：最后交易日为今天或上一交易日才算数

    口径与 data_freshness() 一致：交易日历（QMT/持久化）优先，
    无日历时按工作日近似，避免把几天前的收盘价当作当前行情展示。
    """
    try:
        d = pd.Timestamp(latest_date).date()
    except Exception:
        return False
    today = pd.Timestamp.today().date()
    cal = market_data._trading_calendar()
    if cal:
        past = [x for x in cal if x <= today]
        if not past:
            return False
        # 今天是交易日：今天或上一交易日都算新鲜；
        # 非交易日（周末/节假日）：最新数据必须是最近一个交易日，不再放宽
        threshold = past[-2] if (today in cal and len(past) >= 2) else past[-1]
        return d >= threshold
    # 无交易日历：最新数据日不早于「上一个工作日」（周末顺延，与日历分支同口径）
    ref = today - pd.Timedelta(days=1)
    while ref.weekday() >= 5:
        ref -= pd.Timedelta(days=1)
    return d >= ref


def _quote_from_cache(code: str) -> dict | None:
    """QMT 不可用时，从本地日线缓存取最近两日收盘价计算涨跌（非实时）

    缓存为不复权 + adjust_factor 存储，读取时按 qfq 口径换算，
    避免除权日前后涨跌幅跳变失真。
    """
    raw_df = market_data._cache.get(code, "1d")
    if raw_df is None or raw_df.empty or "close" not in raw_df.columns or len(raw_df) < 2:
        return None
    try:
        df = market_data._apply_adjust(raw_df, code, "qfq")
    except ValueError:
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
    date = str(df.index[-1])[:10]
    return {
        "price": round(last, 2),
        "change": round(last - prev, 2),
        "pct": round((last - prev) / prev * 100, 2) if prev else 0.0,
        "amount": amount,
        "date": date,
        "source": "cache" if _cache_quote_fresh(date) else "stale",
    }


@router.get("/ticker")
async def ticker():
    """底部状态栏行情：QMT 实时优先，未连接时回退本地缓存收盘价；都没有则标记无数据

    缓存报价带新鲜度判定：最后交易日早于「今天/上一交易日」时标记
    source='stale'，前端不再当作当前行情展示（避免过期数据误导）。
    """
    qmt_connected = market_data._qmt.connected
    quotes = []
    for name, code in _TICKER_INDICES:
        q = _quote_from_qmt(code) or _quote_from_cache(code)
        quotes.append({"name": name, "code": code, **(q or {"source": "none"})})
    stale_dates = [q["date"] for q in quotes if q.get("source") == "stale" and q.get("date")]
    return {
        "qmt_connected": qmt_connected,
        "quotes": quotes,
        "cache_latest_date": max(stale_dates) if stale_dates else None,
    }


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
