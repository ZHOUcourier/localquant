"""每日批处理调度器 — 收盘后增量行情/快照 + 开盘前重算因子池

设计:
- 由 main.py lifespan 启动一个 asyncio 常驻协程，无需额外依赖。
- 每个 job 在 daily_jobs 表落一行（running/ok/failed/skipped），前端可查。
- 各步按依赖顺序串联，任一步失败不影响后续；QMT 未连接时行情/快照自动
   skipped（macOS 开发环境常见，不当作错误）。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

from loguru import logger

from backend.config import settings


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── daily_jobs 日志 ──────────────────────────────────────────────────


async def _db_job(db, job_name: str, trigger: str):
    await db.execute(
        "INSERT INTO daily_jobs (job_name, status, trigger, started_at) "
        "VALUES (?, 'running', ?, ?)",
        (job_name, trigger, _now_ms()),
    )
    await db.commit()


async def _finish_job(db, job_name: str, status: str, detail: str):
    await db.execute(
        "UPDATE daily_jobs SET status = ?, detail = ?, finished_at = ? "
        "WHERE id = (SELECT MAX(id) FROM daily_jobs where job_name = ?)",
        (status, detail, _now_ms(), job_name),
    )
    await db.commit()


# ── 单项任务 ─────────────────────────────────────────────────────────


async def _market_step() -> tuple[str, str]:
    """收盘后: 行情增量补齐 + 参考数据快照(成分/行业/股本/合约) + 财务快照。返回 (status, detail)。"""
    from backend.data.qmt_client import QMTClient
    from backend.services import (
        data_download,
        fundamental,
        market_data,
        reference_data,
    )

    qmt = QMTClient()
    if not qmt.connected:
        return "skipped", "QMT 未连接，行情/快照跳过（xtquant 仅 Windows）"

    codes, per = data_download.build_update_plan("1d")
    added = 0
    failed = 0
    for code in codes:
        start = (per or {}).get(code, "")
        try:
            await asyncio.to_thread(data_download._download_one, code, "1d", start, "")
            added += 1
        except Exception:
            failed += 1

    snappable = codes or market_data.list_cached_codes("1d")
    ind = await asyncio.to_thread(reference_data.snapshot_industry, qmt)
    cap = await asyncio.to_thread(reference_data.snapshot_capital, qmt, snappable)
    inst = await asyncio.to_thread(reference_data.snapshot_instrument, qmt, snappable)
    fund = await asyncio.to_thread(fundamental.snapshot_fundamental, qmt, snappable)

    detail = (
        f"行情增量: {len(codes)} 只({added} 成功/{failed} 失败); "
        f"快照: industry={ind} capital={cap} instrument={inst} 财务={fund}"
    )
    return "ok", detail


async def _recalc_step() -> tuple[str, str]:
    """重算因子池 IC 指标并写 provenance（数据不足时跳过）。"""
    from backend.services import market_data
    from backend.services.factor_research import factor_research

    try:
        codes = market_data.list_cached_codes("1d")
    except Exception:
        codes = []
    if not codes:
        return "skipped", "跳过: 本地无行情缓存，请先在数据管理页下载行情"

    try:
        pool = await factor_research.get_pool()
    except Exception as e:
        return "failed", f"读取因子池失败: {e}"
    pool = pool[: max(settings.scheduler_max_recalc, 50)]

    ok = skipped = failed = 0
    for f in pool:
        try:
            factor = await factor_research.recalculate_preset_factor(f["id"])
            if factor and factor.get("recalc_mode") == "recomputed":
                ok += 1
            else:
                skipped += 1
        except Exception:
            failed += 1
    return "ok", f"因子池重算: 成功 {ok} / 跳过 {skipped} / 失败 {failed}"


# ── 一轮完整运行 ───────────────────────────────────────────────────────


async def run_jobs(trigger: str = "manual", steps: list[str] | None = None) -> dict:
    """按依赖顺序执行一个批量任务（写 daily_jobs）。

    steps: ['market','recalc'] 默认全跑; 可传子集手动重跑。
    """
    from backend.database import get_db

    if steps is None:
        steps = ["market", "recalc"]
    db = await get_db()
    results: dict[str, str] = {}

    if "market" in steps:
        await _db_job(db, "market_update", trigger)
        status, detail = await _market_step()
        await _finish_job(db, "market_update", status, detail)
        results["market_update"] = status

    if "recalc" in steps:
        await _db_job(db, "factor_recalc", trigger)
        status, detail = await _recalc_step()
        await _finish_job(db, "factor_recalc", status, detail)
        results["factor_recalc"] = status

    await db.close()
    return results


def run_jobs_sync(trigger: str = "manual", steps: list[str] | None = None) -> dict:
    """同步包装（供脚本/无事件循环环境触发）"""
    return asyncio.run(run_jobs(trigger, steps))


# ── 调度主循环 ────────────────────────────────────────────────────────


async def scheduler_loop():
    if not settings.scheduler_enabled:
        logger.info("scheduler disabled (scheduler_enabled=false)")
        return
    logger.info(
        f"每日批处理调度启动: update={settings.scheduler_update_time} "
        f"recalc={settings.scheduler_recalc_time}"
    )
    _fired_update: set[str] = set()
    _fired_recalc: set[str] = set()

    def _step_for(hhmm: str) -> str | None:
        if hhmm == settings.scheduler_update_time:
            return "market"
        if hhmm == settings.scheduler_recalc_time:
            return "recalc"
        return None

    while True:
        now = datetime.now()
        day = now.date().isoformat()
        hhmm = f"{now.hour:02d}:{now.minute:02d}"
        step = _step_for(hhmm)
        if step == "market" and day not in _fired_update:
            _fired_update.add(day)
            logger.info("调度触发: 收盘行情更新")
            asyncio.create_task(run_jobs(trigger="schedule", steps=["market"]))
        elif step == "recalc" and day not in _fired_recalc:
            _fired_recalc.add(day)
            logger.info("调度触发: 因子池重算")
            asyncio.create_task(run_jobs(trigger="schedule", steps=["recalc"]))
        # 跨半夜清空当日标记
        if now.hour == 0 and now.minute == 0:
            day0 = datetime.now().date().isoformat()
            _fired_update = {d for d in _fired_update if d == day0}
            _fired_recalc = {d for d in _fired_recalc if d == day0}
        await asyncio.sleep(30)


def _step_for(hhmm: str) -> str | None:
    if hhmm == settings.scheduler_update_time:
        return "market"
    if hhmm == settings.scheduler_recalc_time:
        return "recalc"
    return None


async def check_status() -> dict:
    """调度配置 + 最近 job 状态，供前端展示。"""
    from backend.database import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT job_name, status, trigger, detail, started_at, finished_at "
            "FROM daily_jobs ORDER BY id DESC LIMIT 20"
        )
        rows = await cursor.fetchall()
        return {
            "enabled": settings.scheduler_enabled,
            "update_time": settings.scheduler_update_time,
            "recalc_time": settings.scheduler_recalc_time,
            "recent": [dict(r) for r in rows],
        }
    finally:
        await db.close()