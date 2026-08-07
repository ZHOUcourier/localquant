"""风险/组合层 API — 风格暴露/归因、组合优化、绩效补充、压力测试

面板以 {date: {code: value}} 嵌套 dict 传输（与 DataExplore 同制式）。
"""

from __future__ import annotations

import numpy as np
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


class StressHistoricalReq(BaseModel):
    codes: str = ""
    start_date: str = ""
    end_date: str = ""
    weights: dict = {}


@router.post("/stress-historical")
async def stress_historical(req: StressHistoricalReq):
    """历史情景回放：真实危机窗口（2015股灾/2018熊市/2024小微盘…）按当前权重累计

    需要本地行情缓存（股票池 + 区间覆盖对应历史年份）；未覆盖返回 null 并提示。
    """
    try:
        pool = [c.strip() for c in req.codes.split(",") if c.strip()]
        panels = market_data.load_price_panels(
            codes=pool, start_date=req.start_date, end_date=req.end_date
        )
        close = panels["close"]
        ret = close.pct_change()
        out = risk_svc.historical_scenario_stress(
            ret, pd.Series(req.weights) if req.weights else pd.Series(dtype=float)
        )
        out["n_stocks"] = int(close.shape[1])
        out["data_start"] = str(close.index[0])[:10]
        out["data_end"] = str(close.index[-1])[:10]
        return out
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class RiskForecastReq(BaseModel):
    weights: dict = {}
    factor_returns: dict = {}
    portfolio_exposures: dict = {}
    returns: dict = {}


@router.post("/forecast")
async def forecast(req: RiskForecastReq):
    """组合事前风险预测：因子协方差 + 市场模型残差，分解因子风险贡献"""
    try:
        fr = {k: pd.Series(v) for k, v in req.factor_returns.items()}
        pe = {k: pd.Series(v) for k, v in req.portfolio_exposures.items()}
        ret = _df(req.returns) if req.returns else pd.DataFrame()
        return risk_svc.risk_forecast(
            pd.Series(req.weights) if req.weights else pd.Series(dtype=float),
            factor_returns=fr,
            portfolio_exposures=pe if pe else None,
            returns=ret,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class RiskForecastPanelReq(BaseModel):
    codes: str = ""
    start_date: str = ""
    end_date: str = ""
    weights: dict = {}


@router.post("/forecast-panel")
async def forecast_panel(req: RiskForecastPanelReq):
    """组合事前风险（一键）：从本地行情缓存取面板 → 风格暴露 → 因子收益
    → 组合暴露 → 协方差预测 + 风险贡献分解；另附行业因子与历史情景回放"""
    try:
        pool = [c.strip() for c in req.codes.split(",") if c.strip()]
        panels = market_data.load_price_panels(
            codes=pool, start_date=req.start_date, end_date=req.end_date
        )
        close = panels["close"]
        ret = close.pct_change()
        w = pd.Series(req.weights) if req.weights else pd.Series(dtype=float)
        w = w[w.index.isin(close.columns)]
        if w.empty:
            raise HTTPException(status_code=400, detail="权重与缓存股票池无交集")

        styles = risk_svc.build_style_exposures(
            close,
            volume=panels.get("volume"),
            amount=panels.get("amount"),
        )
        sres = risk_svc.style_factor_returns(ret, styles)
        wf = pd.DataFrame(
            np.tile(w.reindex(close.columns).fillna(0.0).to_numpy(), (len(close.index), 1)),
            index=close.index,
            columns=close.columns,
        )
        pstyles = risk_svc.portfolio_style_exposure(wf, styles)
        fr = dict(sres["factor_returns"])

        # 行业因子（均值偏离编码）
        try:
            from backend.services import reference_data

            ind_map = reference_data.load_industry_map(
                as_of=str(close.index[0])[:10]
            )
            if ind_map:
                ires = risk_svc.industry_factor_returns(ret, ind_map)
                fr.update(ires["factor_returns"])
                sres["summary"].extend(ires["summary"])
        except Exception:
            pass

        forecast = risk_svc.risk_forecast(
            w,
            factor_returns=fr,
            portfolio_exposures=pstyles,
            returns=ret,
        )
        hist = risk_svc.historical_scenario_stress(ret, w)
        return {
            **forecast,
            "n_stocks": int(close.shape[1]),
            "data_start": str(close.index[0])[:10],
            "data_end": str(close.index[-1])[:10],
            "style_factor_summary": sres["summary"],
            "historical_scenarios": hist,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/panel")
async def risk_panel(
    codes: str = "",
    start_date: str = "",
    end_date: str = "",
):
    """从本地行情缓存加载风险分析面板（close/volume/amount，前复权口径）

    让风险页直接使用真实缓存数据（股票池 + 区间），无需手工粘贴 JSON。
    """
    pool = [c.strip() for c in codes.split(",") if c.strip()]
    try:
        panels = market_data.load_price_panels(
            codes=pool, start_date=start_date, end_date=end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out = {
        "codes": list(panels.get("close", pd.DataFrame()).columns),
        "start": (
            str(panels["close"].index[0].date())
            if "close" in panels and len(panels["close"])
            else ""
        ),
        "end": (
            str(panels["close"].index[-1].date())
            if "close" in panels and len(panels["close"])
            else ""
        ),
        "close": _panel_dict(panels.get("close", pd.DataFrame())),
        "volume": _panel_dict(panels.get("volume", pd.DataFrame())),
        "amount": _panel_dict(panels.get("amount", pd.DataFrame())),
    }
    return out


class AttributionRunRequest(BaseModel):
    run_id: str


@router.post("/attribution-run")
async def attribution_run(req: AttributionRunRequest):
    """回测记录风格归因（回归法）：读取已落库净值 + 本地行情面板

    组合日收益 ~ Σ β×风格因子收益 + alpha：回答「策略赚的钱来自哪种风格，
    剩下的是不是纯 alpha」。股票池/区间取自回测参数，风格暴露基于缓存面板。
    """
    import json

    from backend.database import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM backtest_runs WHERE id = ?", (req.run_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    if not row:
        raise HTTPException(status_code=404, detail="回测记录不存在")

    equity = json.loads(row["equity_json"] or "[]")
    if len(equity) < 10:
        raise HTTPException(status_code=400, detail="回测记录无净值数据（未完成或过于短暂）")
    params = json.loads(row["params_json"] or "{}")
    eq = pd.Series(
        {e["ts"]: float(e["equity"]) for e in equity if e.get("equity")}
    ).sort_index()
    eq.index = pd.to_datetime(eq.index)
    strategy_returns = eq.pct_change().dropna()
    if len(strategy_returns) < 30:
        raise HTTPException(status_code=400, detail="回测区间过短，不足以做风格归因（需 ≥30 个交易日）")

    try:
        panels = market_data.load_price_panels(
            codes=list(params.get("stock_pool") or []),
            start_date=str(params.get("period_start") or ""),
            end_date=str(params.get("period_end") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    close = panels["close"]
    styles = risk_svc.build_style_exposures(
        close,
        volume=panels.get("volume"),
        amount=panels.get("amount"),
    )
    ret = close.pct_change()
    style_res = risk_svc.style_factor_returns(ret, styles)
    factor_returns = dict(style_res["factor_returns"])
    industry_note = ""
    # 行业因子收益（均值偏离编码）：回答「超额来自哪个行业」
    try:
        from backend.services import reference_data

        ind_map = reference_data.load_industry_map(as_of=str(close.index[0])[:10])
        if ind_map:
            ind_res = risk_svc.industry_factor_returns(ret, ind_map)
            if ind_res["factor_returns"]:
                factor_returns.update(ind_res["factor_returns"])
                style_res["summary"].extend(ind_res["summary"])
                industry_note = (
                    f"含 {len(ind_res['factor_returns'])} 个行业因子（均值偏离编码，"
                    "相对全市场平均行业的超额）"
                )
    except Exception:
        industry_note = "行业映射不可用，归因仅含风格因子"
    result = risk_svc.strategy_regression_attribution(
        strategy_returns, factor_returns
    )
    result["status"] = "ok"
    result["run_id"] = req.run_id
    result["strategy_name"] = row["strategy_name"] or ""
    result["n_stocks"] = int(close.shape[1])
    result["data_date"] = str(close.index[-1])[:10]
    result["style_factor_summary"] = style_res["summary"]
    result["industry_note"] = industry_note
    return result