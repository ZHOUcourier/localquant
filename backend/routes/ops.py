"""运营/批处理 API — 每日调度状态、手动重跑、分析溯源查询"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import scheduler as scheduler_svc
from backend.services import provenance as provenance_svc

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
        "recent_jobs": [],
    }

    # 1. 市场环境（regime 自带 15 分钟缓存 + 无指数缓存时结构化提示）
    briefing["market"] = regime.market_regime()

    # 2. 因子池体检摘要（生命周期阶段计数 + 近期衰减/失效因子）
    try:
        health = await factor_research.factor_health(min_snapshots=1)
        from collections import Counter

        stages = Counter(h["stage"] for h in health)
        briefing["factors"] = {
            "pool_n": len(health),
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