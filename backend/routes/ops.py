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