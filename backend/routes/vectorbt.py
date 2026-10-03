"""vectorbt 快速参数扫描 API（Beta）— 因子组合参数网格的向量化模拟"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services import vectorbt_scan

router = APIRouter()


class QuantileScanReq(BaseModel):
    formula: str
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""
    period: str = "5m"  # 分钟公式求值周期；日频公式忽略
    groups: list[int] = Field(default_factory=lambda: [5, 10, 20])
    rebalance_days: list[int] = Field(default_factory=lambda: [1, 5, 10, 20])
    fee_rate: float = 0.0015
    direction: int = 1  # 1=高值做多；-1=低值做多


@router.post("/quantile-scan")
async def quantile_scan(req: QuantileScanReq):
    """对公式因子跑 分组数×调仓周期 参数网格（简化假设，Beta）

    分钟公式走本地分钟缓存求值，日频公式走日线缓存；随后用 vectorbt
    以「等权目标仓位 + 固定费率」模拟每组参数的组合表现。
    """
    from backend.services.factor_research import FactorResearchService

    formula = (req.formula or "").strip()
    if not formula:
        raise HTTPException(status_code=400, detail="公式为空")
    try:
        if FactorResearchService._is_intraday_formula(formula):
            from backend.services import market_data
            from backend.services.factor_operators import eval_factor_formula
            from backend.services.intraday_cleaner import load_intraday_panels
            from backend.services.intraday_operators import (
                ID_LAST,
                build_intraday_namespace,
            )

            codes = req.stock_pool or market_data.list_cached_codes(req.period)
            if not codes:
                raise HTTPException(
                    status_code=400,
                    detail=f"本地无 {req.period} 分钟缓存 — 请先在数据管理下载分钟行情",
                )
            loaded = load_intraday_panels(
                codes=codes,
                period=req.period,
                start_date=req.start_date,
                end_date=req.end_date,
            )
            ns = build_intraday_namespace(loaded["panels"], loaded["meta"])
            factor_df = eval_factor_formula(formula, ns)
            if isinstance(factor_df, pd.Series):
                factor_df = factor_df.to_frame()
            idx = pd.to_datetime(factor_df.index)
            if (idx.normalize() != idx).any():
                factor_df = ID_LAST(factor_df, 0)
            factor_df.index = pd.to_datetime(factor_df.index).normalize()
            close_daily = (
                loaded["panels"]["close"]
                .groupby(loaded["panels"]["close"].index.normalize())
                .last()
            )
        else:
            from backend.services.factor_research import factor_research

            res = factor_research.eval_formula_on_local(
                formula,
                start_date=req.start_date,
                end_date=req.end_date,
            )
            if not res.get("ok"):
                raise HTTPException(status_code=400, detail=res.get("message", "本地求值失败"))
            factor_df = res["factor_df"]
            close_daily = res["panels"]["close"]
        result = vectorbt_scan.scan_quantile_portfolios(
            factor_df=factor_df,
            close_df=close_daily,
            group_list=req.groups,
            rebalance_list=req.rebalance_days,
            fee_rate=req.fee_rate,
            direction=req.direction,
        )
        result["beta"] = True
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"参数扫描失败: {e}")
