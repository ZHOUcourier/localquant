"""因子路由 — 直接调用本地因子研究服务"""

import time
import uuid

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from backend.database import get_db
from backend.models.factor import (
    CorrelationRequest,
    FactorCreate,
    ICAnalysisRequest,
    NeutralizeRequest,
    QuantileRequest,
)
from backend.services import market_data
from backend.services.factor_research import factor_research

router = APIRouter()


def _dict_to_df(d: dict) -> pd.DataFrame:
    """将 {date: {code: value}} 嵌套字典转为 DataFrame (index=date, columns=stocks)"""
    return pd.DataFrame.from_dict(d, orient="index")


class FactorComputeRequest(BaseModel):
    mode: str = "formula"  # formula | code
    formula: str = ""
    code: str = ""
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""


@router.post("/compute")
async def compute_factor(req: FactorComputeRequest):
    """基于本地行情数据计算因子值，同时返回远期收益供 IC/分层分析使用"""
    try:
        panels = market_data.load_price_panels(
            codes=req.stock_pool,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    close = panels["close"]
    eval_ctx = {
        "np": np,
        "pd": pd,
        "open": panels.get("open"),
        "high": panels.get("high"),
        "low": panels.get("low"),
        "close": close,
        "volume": panels.get("volume"),
        "amount": panels.get("amount"),
    }

    try:
        if req.mode == "formula":
            if not req.formula.strip():
                raise ValueError(
                    "因子公式为空，请输入表达式，如: close / close.shift(5) - 1"
                )
            factor = eval(req.formula, {"__builtins__": {}}, eval_ctx)  # noqa: S307
        else:
            if not req.code.strip():
                raise ValueError("因子代码为空")
            exec_ctx = dict(eval_ctx)
            exec(req.code, {"__builtins__": __builtins__}, exec_ctx)  # noqa: S102
            fn = exec_ctx.get("compute_factor")
            if callable(fn):
                factor = fn(close=close, volume=panels.get("volume"))
            else:
                factor = exec_ctx.get("factor_data")
            if factor is None:
                raise ValueError("代码未定义 compute_factor 函数或 factor_data 变量")
        if isinstance(factor, pd.Series):
            factor = factor.to_frame()
        if not isinstance(factor, pd.DataFrame):
            raise ValueError(
                f"因子计算结果应为 DataFrame，得到 {type(factor).__name__}"
            )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"因子计算失败: {e}")
        raise HTTPException(status_code=400, detail=f"因子计算失败: {e}")

    factor = factor.dropna(how="all")
    if factor.empty:
        raise HTTPException(
            status_code=400, detail="因子计算结果为空（可能回看期超过数据长度）"
        )

    # 次日收益（T 日因子对齐 T+1 收益由 IC 分析接口内部处理）
    returns = close.pct_change()

    return {
        "dates": [str(d.date()) for d in factor.index],
        "stocks": list(factor.columns),
        "factor_data": market_data.panel_to_dict(factor),
        "return_data": market_data.panel_to_dict(returns),
    }


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
        (
            factor_id,
            req.name,
            req.description,
            req.category,
            req.formula,
            req.code,
            now,
            now,
        ),
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
