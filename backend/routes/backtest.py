"""回测路由"""
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel
from typing import Optional

from backend.services.backtest_analysis import backtest_analysis

router = APIRouter()


# ── 请求模型 ─────────────────────────────────────────────────

class RunBacktestRequest(BaseModel):
    signals: dict  # {date_str: {code: signal_value}}
    prices: dict   # {date_str: {code: price}}
    initial_capital: float = 1_000_000
    commission_rate: float = 0.001
    slippage: float = 0.001


class TearSheetRequest(BaseModel):
    returns: dict  # {date_str: return_value}
    benchmark_returns: Optional[dict] = None  # {date_str: return_value}
    risk_free_rate: float = 0.03


class MonteCarloRequest(BaseModel):
    returns: dict  # {date_str: return_value}
    n_sims: int = 1000
    n_days: int = 252


# ── 工具函数 ─────────────────────────────────────────────────

def _dict_to_series(d: dict) -> "pd.Series":
    import pandas as pd
    s = pd.Series(d)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    return s


def _dict_to_df(d: dict) -> "pd.DataFrame":
    import pandas as pd
    return pd.DataFrame(d).apply(pd.to_numeric, errors="coerce")


# ── 路由 ─────────────────────────────────────────────────────

@router.post("/run")
async def run_backtest(req: RunBacktestRequest):
    """执行向量化回测"""
    try:
        import pandas as pd
        signals_df = _dict_to_df(req.signals)
        prices_df = _dict_to_df(req.prices)

        result = backtest_analysis.run_backtest(
            signals=signals_df,
            prices=prices_df,
            initial_capital=req.initial_capital,
            commission_rate=req.commission_rate,
            slippage=req.slippage,
        )

        # 序列化
        equity_curve = result["equity_curve"]
        strategy_returns = result["strategy_returns"]

        total_return = float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1) if len(equity_curve) > 0 else 0.0

        return {
            "status": "ok",
            "total_return": total_return,
            "equity_curve": {str(k.date() if hasattr(k, "date") else k): float(v) for k, v in equity_curve.items()},
            "strategy_returns": {str(k.date() if hasattr(k, "date") else k): float(v) for k, v in strategy_returns.items()},
            "initial_capital": req.initial_capital,
        }
    except Exception as e:
        logger.error(f"回测执行失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tear-sheet")
async def tear_sheet(req: TearSheetRequest):
    """计算绩效报告"""
    try:
        returns_series = _dict_to_series(req.returns)
        bm = _dict_to_series(req.benchmark_returns) if req.benchmark_returns else None

        result = backtest_analysis.performance_tear_sheet(
            returns=returns_series,
            benchmark_returns=bm,
            risk_free_rate=req.risk_free_rate,
        )

        # 序列化 drawdown_series
        from backend.services.backtest_analysis import backtest_analysis as ba
        dd = ba.drawdown_analysis(returns_series)
        result["drawdown_series"] = {
            str(k.date() if hasattr(k, "date") else k): float(v)
            for k, v in dd["drawdown_series"].items()
        }
        result["top_drawdowns"] = dd["top_drawdowns"]
        result["max_drawdown"] = dd["max_drawdown"]

        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"绩效计算失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/monte-carlo")
async def monte_carlo(req: MonteCarloRequest):
    """蒙特卡洛模拟"""
    try:
        returns_series = _dict_to_series(req.returns)

        result = backtest_analysis.monte_carlo_simulation(
            returns=returns_series,
            n_sims=req.n_sims,
            n_days=req.n_days,
        )

        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"蒙特卡洛模拟失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
