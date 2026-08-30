"""运营/批处理 API — 每日调度状态、手动重跑、分析溯源查询"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import provenance as provenance_svc
from backend.services import scheduler as scheduler_svc

router = APIRouter()


class RunJobsReq(BaseModel):
    steps: list[str] | None = None  # 空=全部; 传 ['market'] 或 ['recalc']


class ProvenanceWrite(BaseModel):
    kind: str = "factor"
    entity_id: str = ""
    entity_name: str = ""
    params: dict = {}
    metrics: dict = {}
    notes: str = ""
    source: str = "api"


@router.get("/scheduler")
async def scheduler_status():
    """调度配置 + 最近 job 状态"""
    try:
        return await scheduler_svc.check_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/run")
async def scheduler_run(req: RunJobsReq):
    """手动跑一轮批处理（step 缺省全跑）"""
    try:
        return await scheduler_svc.run_jobs(trigger="manual", steps=req.steps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/provenance")
async def list_provenance(kind: str | None = None, entity_id: str | None = None, limit: int = 50):
    """查询分析溯源记录"""
    try:
        return await provenance_svc.list_provenance(kind, entity_id, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/provenance")
async def write_provenance(req: ProvenanceWrite):
    """写入一条溯源记录"""
    try:
        row_id = await provenance_svc.record_provenance(
            kind=req.kind,
            entity_id=req.entity_id,
            entity_name=req.entity_name,
            params=req.params,
            metrics=req.metrics,
            notes=req.notes,
            source=req.source,
        )
        return {"id": row_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/briefing")
async def research_briefing():
    """每日研究简报（首页 Dashboard 展示）：市场状态 + 因子池体检 +
    近 7 日除权事件 + 数据时效 + 最近批处理状态

    全部为现有能力的实时聚合；本地无缓存时给出结构化提示而非报错。
    """
    import time

    from backend.database import get_db
    from backend.services import market_data, regime
    from backend.services.factor_research import factor_research

    briefing: dict = {
        "generated_at": int(time.time()),
        "market": None,
        "factors": None,
        "dividend_events": [],
        "data_freshness": None,
        "research_readiness": None,
        "recent_jobs": [],
    }

    # 1. 市场环境（regime 自带 15 分钟缓存 + 无指数缓存时结构化提示）
    briefing["market"] = regime.market_regime()

    # 2. 因子池体检摘要（生命周期阶段计数 + 近期衰减/失效因子）
    try:
        health = await factor_research.factor_health(min_snapshots=1)
        from collections import Counter

        stages = Counter(h["stage"] for h in health)
        # pool_n = 真实因子池规模（factor_pool 表）；体检范围是整个因子库，二者区分开
        pool = await factor_research.get_pool()
        briefing["factors"] = {
            "pool_n": len(pool),
            "library_health_n": len(health),
            "stages": dict(stages),
            "n_with_snapshot": sum(1 for h in health if h["n_snapshots"] >= 2),
            "decaying": [
                {
                    "factor_name": h["factor_name"],
                    "stage": h["stage"],
                    "latest_ic_mean": h["latest_ic_mean"],
                    "trend_label": h["trend_label"],
                }
                for h in health
                if h["stage"] in ("衰减", "失效") and h.get("latest_ic_mean") is not None
            ][:8],
        }
    except Exception:
        briefing["factors"] = {"error": "因子体检不可用"}

    # 3. 近 7 日除权事件
    try:
        briefing["dividend_events"] = market_data.dividend_events(days=7, limit=20)
    except Exception:
        pass

    # 4. 数据时效
    try:
        briefing["data_freshness"] = market_data.data_freshness()
    except Exception:
        pass

    # 4.5 研究数据就绪度：把「样本/历史/参考快照/财务/分钟」一次性讲清楚，
    # 研究员不会拿 100 只股票的样本当成全市场结论。
    try:
        from backend.config import settings
        from backend.services import fundamental, reference_data

        equity_codes = market_data.list_cached_codes("1d", exclude_indices=True)
        coverage = {
            e["code"]: e for e in market_data.cache_coverage("1d")
        }
        equity_rows = [coverage[c] for c in equity_codes if c in coverage]
        data_start = min((e["start"] for e in equity_rows if e.get("start")), default=None)
        data_end = max((e["end"] for e in equity_rows if e.get("end")), default=None)
        n_days = max((int(e.get("rows") or 0) for e in equity_rows), default=0)
        # 交易日历可得时以交易日计；否则 n_days 只是缓存观测行数，明确标注未验证
        trade_calendar = market_data._trading_calendar()
        calendar = market_data.trading_calendar_source()
        calendar_unverified = trade_calendar is None
        if trade_calendar and data_start and data_end:
            try:
                start_ts = pd.Timestamp(data_start)
                end_ts = pd.Timestamp(data_end)
                n_calendar_days = len(
                    [d for d in trade_calendar if start_ts.date() <= d <= end_ts.date()]
                )
                if n_calendar_days:
                    n_days = n_calendar_days
            except Exception:
                pass
        ref = reference_data.reference_status()
        ref_dates = [v["latest"] for v in ref.values() if v.get("latest")]
        ref_latest = max(ref_dates) if ref_dates else None

        blockers: list[str] = []
        warnings: list[str] = []
        if len(equity_codes) < 300:
            blockers.append(
                f"股票样本仅 {len(equity_codes)} 只（建议 ≥300），IC/分层/组合结果仅用于方法验证"
            )
        elif len(equity_codes) < 1000:
            warnings.append(
                f"股票样本 {len(equity_codes)} 只，建议全市场（≥1000）后再做正式因子筛选"
            )
        if n_days < 504:
            blockers.append(
                f"历史区间约 {n_days} 个交易日（建议 ≥504/2 年），尚不足以覆盖完整牛熊"
            )
        elif n_days < 756:
            warnings.append(f"历史区间约 {n_days} 个交易日，建议补充到 3 年以上")
        if ref_latest is None:
            blockers.append("无参考元数据快照（行业/成分/合约），中性化与 as-of 过滤不可用")
        elif data_end and ref_latest < str(data_end):
            warnings.append(
                f"参考快照最新日期 {ref_latest}，早于行情末日 {data_end}；"
                "历史行业/成分/ST/两融状态存在静态回填偏差"
            )
        fund = fundamental.snapshot_status()
        if not fund.get("ready"):
            warnings.append("财务快照为空，fund_* 基本面因子当前不可用")
        minute_dir = settings.cache_dir / "5m"
        minute_files = list(minute_dir.glob("*.parquet")) if minute_dir.exists() else []
        if not minute_files:
            warnings.append("无分钟缓存，日内高频因子（m_*/ID_*/M_*）不可用")
        if not market_data._qmt.connected:
            warnings.append("QMT 未连接，行情/快照无法增量更新（仅 Windows + QMT 客户端可用）")
        if calendar_unverified:
            warnings.append(
                "无可靠交易日历，n_days 为缓存观测行数（非交易日，未含节假日校正）；"
                "年化/IC t 值/换手等统计口径仅供参考"
            )

        briefing["research_readiness"] = {
            "ready": not blockers,
            "n_stocks": len(equity_codes),
            "n_days": n_days,
            "calendar": calendar,
            "calendar_unverified": calendar_unverified,
            "data_start": data_start,
            "data_end": data_end,
            "reference_latest": ref_latest,
            "fundamental_ready": bool(fund.get("ready")),
            "minute_ready": bool(minute_files),
            "qmt_connected": bool(market_data._qmt.connected),
            "blockers": blockers,
            "warnings": warnings,
        }
    except Exception:
        briefing["research_readiness"] = {"error": "研究数据就绪度评估不可用"}

    # 5. 最近批处理任务
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT job_name, status, trigger, detail, started_at, finished_at "
                "FROM daily_jobs ORDER BY id DESC LIMIT 6"
            )
            briefing["recent_jobs"] = [dict(r) for r in await cursor.fetchall()]
        finally:
            await db.close()
    except Exception:
        pass

    return briefing