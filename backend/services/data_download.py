"""批量数据下载服务 — 板块/指数/代码列表批量下载，SSE 逐只进度

事件类型（与工作流 runner 的 SSE 风格一致）：
  batch_start:     {total, codes}
  symbol_complete: {index, code, rows}
  symbol_failed:   {index, code, error}
  reference_saved: {kind, rows}          参考数据快照结果（非致命）
  batch_complete:  {ok, failed, failed_codes, duration_ms}

QMT 调用为同步阻塞，逐只放入线程池避免卡住事件循环；
每只失败自动重试一次，最终失败进入 failed_codes 供前端重试。
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, AsyncGenerator

from loguru import logger

from backend.services import market_data, reference_data


def _sse(event_type: str, data: dict[str, Any]) -> str:
    data.setdefault("timestamp", datetime.now().isoformat())
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


def expand_sector(sector: str) -> list[str]:
    """展开板块/指数成分股（需 QMT 连接）"""
    qmt = market_data._qmt
    if not qmt.connected:
        raise ConnectionError("QMT 未连接，无法展开板块成分")
    stocks = qmt.get_sector_stocks(sector)
    if not stocks:
        raise ValueError(f"板块「{sector}」无成分股或不存在")
    return stocks


def _download_one(code: str, period: str, start: str, end: str) -> int:
    """下载单只并合并入缓存，返回缓存总行数"""
    qmt = market_data._qmt
    qmt.download_history([code], period=period, start_time=start, end_time=end)
    data = qmt.get_kline([code], period=period, start_time=start, end_time=end)
    df = data.get(code)
    if df is None or df.empty:
        raise ValueError("QMT 未返回数据")
    merged = market_data._cache.get_or_append(code, period, df)
    return len(merged)


async def batch_download_stream(
    codes: list[str],
    period: str = "1d",
    start_date: str = "",
    end_date: str = "",
    sector: str = "",
    per_code_start: dict[str, str] | None = None,
) -> AsyncGenerator[str, None]:
    """批量下载 SSE 生成器

    Args:
        codes: 代码列表（已展开）
        sector: 非空时下载完成后记录该板块的成分快照
        per_code_start: 增量补齐模式下每只股票各自的起始日期（yyyymmdd）
    """
    qmt = market_data._qmt
    if not qmt.connected:
        yield _sse(
            "batch_failed",
            {
                "status": "failed",
                "message": "QMT 未连接，无法下载数据 — xtquant 仅 Windows 可用",
            },
        )
        return

    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    started = time.perf_counter()

    yield _sse("batch_start", {"total": len(codes), "codes": codes})

    ok = 0
    failed_codes: list[str] = []
    for i, code in enumerate(codes):
        code_start = (per_code_start or {}).get(code, start)
        error: str = ""
        rows = 0
        # 每只失败自动重试一次
        for attempt in range(2):
            try:
                rows = await asyncio.to_thread(
                    _download_one, code, period, code_start, end
                )
                error = ""
                break
            except Exception as e:
                error = str(e)
                logger.warning(f"下载 {code} 失败（第 {attempt + 1} 次）: {e}")
        if error:
            failed_codes.append(code)
            yield _sse(
                "symbol_failed",
                {"index": i, "code": code, "error": error, "level": "error"},
            )
        else:
            ok += 1
            yield _sse("symbol_complete", {"index": i, "code": code, "rows": rows})

    # 参考数据快照（非致命：失败只记录，不影响行情下载结果）
    downloaded = [c for c in codes if c not in failed_codes]
    async for event in _snapshot_reference(sector, downloaded):
        yield event

    yield _sse(
        "batch_complete",
        {
            "ok": ok,
            "failed": len(failed_codes),
            "failed_codes": failed_codes,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        },
    )


async def _snapshot_reference(
    sector: str, codes: list[str]
) -> AsyncGenerator[str, None]:
    """采集参考数据快照并逐项 yield 结果事件"""
    qmt = market_data._qmt
    if not qmt.connected or not codes:
        return

    tasks: list[tuple[str, Any]] = [
        ("instrument", lambda: reference_data.snapshot_instrument(qmt, codes)),
        ("capital", lambda: reference_data.snapshot_capital(qmt, codes)),
        ("industry", lambda: reference_data.snapshot_industry(qmt)),
    ]
    if sector:
        tasks.insert(
            0,
            (
                "index_constituents",
                lambda: reference_data.snapshot_index_constituents(qmt, sector),
            ),
        )

    for kind, fn in tasks:
        try:
            rows = await asyncio.to_thread(fn)
            yield _sse("reference_saved", {"kind": kind, "rows": rows})
        except Exception as e:
            logger.warning(f"参考数据快照 {kind} 失败: {e}")
            yield _sse(
                "reference_saved",
                {"kind": kind, "rows": 0, "error": str(e), "level": "warning"},
            )


def build_update_plan(period: str = "1d") -> tuple[list[str], dict[str, str]]:
    """一键补齐计划：已缓存品种 → 各自末日期作为增量起点"""
    import pandas as pd

    from backend.data.converter import normalize_timestamp

    codes = market_data.list_cached_codes(period)
    per_code_start: dict[str, str] = {}
    for code in codes:
        df = market_data._cache.get(code, period)
        if df is None or df.empty:
            continue
        try:
            idx = normalize_timestamp(df.index)
            latest = pd.Timestamp(idx.max())
            if latest.tzinfo is not None:
                latest = latest.tz_localize(None)
            per_code_start[code] = latest.strftime("%Y%m%d")
        except Exception as e:
            logger.warning(f"解析 {code} 最新时间失败: {e}")
    return codes, per_code_start
