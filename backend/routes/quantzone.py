"""QuantZone（宽舟科技）因子数据平台 API — 配额/因子库/对拍（Beta）"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import quantzone_service as qz_svc

router = APIRouter()


class ReconcileReq(BaseModel):
    qz_factor: str  # 如 feat_single_amt_ratio_entropy_30m
    local_formula: str  # 原始值公式（不带 RANK），如 ID_PV_ENTROPY(m_close, m_volume, 30)
    codes: list[str] = []
    start_date: str = ""
    end_date: str = ""
    max_codes: int = 20


@router.get("/status")
async def status():
    """配置状态与剩余配额（免费版每日 512MB 下载配额）"""
    if not qz_svc.is_configured():
        return {
            "configured": False,
            "message": "未配置 — 请在 .env 设置 QZ_ACCESS_KEY / QZ_SIGN_SECRET",
        }
    try:
        quota = qz_svc.get_quota()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"QuantZone 连接失败: {e}")
    return {"configured": True, "quota": quota, "beta": True}


@router.get("/factors")
async def factors(keyword: str = ""):
    """因子库清单（2600+，可按关键词过滤）"""
    try:
        return {"ok": True, "factors": qz_svc.list_factors(keyword)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/reconcile")
async def reconcile(req: ReconcileReq):
    """对拍：本地公式值 vs QZ 官方因子值逐点对比

    verdict: match（口径一致）/ direction_match（排序一致量级有差）/
    mismatch（口径不一致，注意 amt=成交额 vs volume）/ local_missing（本地无分钟数据）/
    insufficient_overlap（样本重叠不足）
    """
    try:
        return qz_svc.reconcile(
            qz_factor=req.qz_factor,
            local_formula=req.local_formula,
            codes=req.codes or None,
            start_date=req.start_date,
            end_date=req.end_date,
            max_codes=req.max_codes,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
