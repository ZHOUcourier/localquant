"""因子路由 — 直接调用本地因子研究服务"""
from fastapi import APIRouter, HTTPException
from loguru import logger
import pandas as pd
import numpy as np

from backend.models.factor import (
    ICAnalysisRequest, QuantileRequest, NeutralizeRequest,
    CorrelationRequest, FactorCreate,
)
from backend.services.factor_research import factor_research
from backend.database import get_db
import uuid
import time

router = APIRouter()


def _dict_to_df(d: dict) -> pd.DataFrame:
    """将 {date: {code: value}} 嵌套字典转为 DataFrame (index=date, columns=stocks)"""
    return pd.DataFrame.from_dict(d, orient="index")


@router.post("/ic-analysis")
async def ic_analysis(req: ICAnalysisRequest):
    try:
        factor_df = _dict_to_df(req.factor_data)
        return_df = _dict_to_df(req.return_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        return_df.index = pd.to_datetime(return_df.index)
        result = factor_research.ic_analysis(factor_df, return_df, req.periods)
        return result
    except Exception as e:
        logger.error(f"IC分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"IC分析失败: {e}")


@router.post("/quantile")
async def quantile_analysis(req: QuantileRequest):
    try:
        factor_df = _dict_to_df(req.factor_data)
        return_df = _dict_to_df(req.return_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        return_df.index = pd.to_datetime(return_df.index)
        result = factor_research.quantile_analysis(factor_df, return_df, req.n_groups)
        return result
    except Exception as e:
        logger.error(f"分层分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"分层分析失败: {e}")


@router.post("/neutralize")
async def neutralize(req: NeutralizeRequest):
    try:
        factor_df = _dict_to_df(req.factor_data)
        industry_df = _dict_to_df(req.industry_data)
        market_cap_df = _dict_to_df(req.market_cap_data)
        factor_df.index = pd.to_datetime(factor_df.index)
        industry_df.index = pd.to_datetime(industry_df.index)
        market_cap_df.index = pd.to_datetime(market_cap_df.index)
        result = factor_research.neutralize(factor_df, industry_df, market_cap_df)
        return result.fillna("").to_dict(orient="index")
    except Exception as e:
        logger.error(f"中性化失败: {e}")
        raise HTTPException(status_code=500, detail=f"中性化失败: {e}")


@router.post("/correlation")
async def correlation(req: CorrelationRequest):
    try:
        factors = {}
        for name, data in req.factors.items():
            df = _dict_to_df(data)
            df.index = pd.to_datetime(df.index)
            factors[name] = df
        result = factor_research.factor_correlation(factors)
        return result
    except Exception as e:
        logger.error(f"相关性分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"相关性分析失败: {e}")


@router.post("/combine")
async def combine_factors(req: CorrelationRequest):
    """多因子合成 — 复用 CorrelationRequest 结构传入 factors"""
    try:
        factors = {}
        for name, data in req.factors.items():
            df = _dict_to_df(data)
            df.index = pd.to_datetime(df.index)
            factors[name] = df
        result = factor_research.multi_factor_combine(factors)
        return result.fillna(0).to_dict(orient="index")
    except Exception as e:
        logger.error(f"因子合成失败: {e}")
        raise HTTPException(status_code=500, detail=f"因子合成失败: {e}")


@router.get("/library")
async def list_factors():
    db = await get_db()
    cursor = await db.execute("SELECT * FROM factors ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(row) for row in rows]


@router.post("/library")
async def register_factor(req: FactorCreate):
    factor_id = str(uuid.uuid4())
    now = int(time.time() * 1000)
    db = await get_db()
    await db.execute(
        "INSERT INTO factors (id, name, description, category, formula, code, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (factor_id, req.name, req.description, req.category, req.formula, req.code, now, now),
    )
    await db.commit()
    await db.close()
    return {"id": factor_id, "name": req.name}


@router.delete("/library/{factor_id}")
async def delete_factor(factor_id: str):
    db = await get_db()
    await db.execute("DELETE FROM factors WHERE id = ?", (factor_id,))
    await db.commit()
    await db.close()
    return {"deleted": factor_id}
