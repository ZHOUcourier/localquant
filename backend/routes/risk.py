"""风险/组合层 API — 风格暴露/归因、组合优化、绩效补充、压力测试

面板以 {date: {code: value}} 嵌套 dict 传输（与 DataExplore 同制式）。
"""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import market_data
from backend.services import risk as risk_svc

router = APIRouter()


def _df(d: dict) -> pd.DataFrame:
    frame = pd.DataFrame.from_dict(d, orient="index")
    if not frame.empty:
        # 前端按 {date_str: {...}} 传递 → 统一解析为 datetime index
        parsed = pd.to_datetime(frame.index, errors="coerce")
        if parsed.notna().all():
            frame.index = parsed
        frame = frame.sort_index()
    return frame


def _panel_dict(panel: pd.DataFrame) -> dict:
    return market_data.panel_to_dict(panel)


def _fundamental(d: dict | None) -> dict:
    out = {}
    for k, v in (d or {}).items():
        out[k] = _df(v)
    return out


class PanelReq(BaseModel):
    close: dict = {}
    volume: dict = {}
    amount: dict = {}
    market_cap: dict = {}
    fundamental: dict = {}


class StyleFactorReq(BaseModel):
    returns: dict = {}
    styles: dict = {}
    min_stocks: int = 10


class AttributionReq(BaseModel):
    strategy_returns: dict = {}
    portfolio_styles: dict = {}
    style_returns: dict = {}


class ScoresReq(BaseModel):
    scores: dict = {}
    industry_map: dict = {}
    max_position: float = 0.20
    max_industry_exposure: float = 0.30
    long_only: bool = True
    risk_aversion: float = 1.0
    gross_target: float = 1.0


class MetricsReq(BaseModel):
    returns: dict = {}
    benchmark: dict = {}
    weights: dict = {}
    benchmark_weights: dict = {}


class StressReq(BaseModel):
    weights: dict = {}
    scenarios: dict = {}


@router.post("/style-exposure")
async def style_exposure(req: PanelReq):
    """构建每日风格暴露面板（Barra-like）"""
    try:
        styles = risk_svc.build_style_exposures(
            _df(req.close),
            volume=_df(req.volume) if req.volume else None,
            amount=_df(req.amount) if req.amount else None,
            market_cap=_df(req.market_cap) if req.market_cap else None,
            fundamental=_fundamental(req.fundamental) if req.fundamental else None,
        )
        return {k: _panel_dict(v) for k, v in styles.items()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/style-factor")
async def style_factor(req: StyleFactorReq):
    """截面风格因子收益归因 & 摘要"""
    try:
        styles = {k: _df(v) for k, v in req.styles.items()}
        return risk_svc.style_factor_returns(_df(req.returns), styles, req.min_stocks)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/attribution")
async def attribution(req: AttributionReq):
    """策略收益归因：拆成风格贡献 + 纯 alpha（残差）"""
    try:
        pstyles = {k: pd.Series(v) for k, v in req.portfolio_styles.items()}
        sret = {k: pd.DataFrame(v) for k, v in req.style_returns.items()}
        return risk_svc.strategy_attribution(
            pd.Series(req.strategy_returns), pstyles, sret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/optimize")
async def optimize(req: ScoresReq):
    """带约束的组合权重（SLSQP）"""
    try:
        w = risk_svc.optimize_weights(
            pd.Series(req.scores),
            covariance=None,
            long_only=req.long_only,
            max_position=req.max_position,
            industry_map=req.industry_map or None,
            max_industry_exposure=req.max_industry_exposure,
            gross_target=req.gross_target,
            risk_aversion=req.risk_aversion,
        )
        return {
            "weights": w.to_dict(),
            "n_assets": int((w.abs() > 1e-9).sum()),
            "gross": float(w.abs().sum()),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/metrics")
async def metrics(req: MetricsReq):
    """补充绩效指标：alpha/beta、上下行捕获率、Active Share"""
    try:
        # returns/benchmark 均为 {date: 值} 扁平序列（组合日收益）
        bench = None
        if req.benchmark:
            s = pd.Series(req.benchmark).dropna()
            if not s.empty:
                bench = s
        return risk_svc.extended_risk_metrics(
            pd.Series(req.returns).dropna(),
            benchmark_returns=bench,
            weights=pd.Series(req.weights) if req.weights else None,
            benchmark_weights=(
                pd.Series(req.benchmark_weights) if req.benchmark_weights else None
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stress")
async def stress(req: StressReq):
    """压力测试：场景收益冲击组合权重。scenarios 为空时用内置 3 场景。"""
    try:
        out = risk_svc.stress_test(
            pd.DataFrame(),
            pd.Series(req.weights),
            dict(req.scenarios) if req.scenarios else None,
        )
        return out
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))