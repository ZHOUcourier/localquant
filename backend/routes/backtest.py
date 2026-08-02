"""回测路由（含回测记录 backtest_runs：8 阶段进度落库，画板/回测中心共用）"""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from backend.database import get_db
from backend.services import market_data
from backend.services.backtest_analysis import backtest_analysis

router = APIRouter()


# ── 请求模型 ─────────────────────────────────────────────────


class RunBacktestRequest(BaseModel):
    signals: dict  # {date_str: {code: signal_value}}
    prices: dict  # {date_str: {code: price}}
    initial_capital: float = 1_000_000
    commission_rate: float = 0.001
    slippage: float = 0.001
    stamp_tax: float = 0.0005
    normalize: str = "none"  # none / long_only / dollar_neutral
    take_profit: float = 0.0  # 单仓止盈比例（0=关闭）
    stop_loss: float = 0.0  # 单仓止损比例（0=关闭）
    trailing_stop: float = 0.0  # 移动止损比例（0=关闭）


class TearSheetRequest(BaseModel):
    returns: dict  # {date_str: return_value}
    benchmark_returns: Optional[dict] = None  # {date_str: return_value}
    risk_free_rate: float = 0.03


class MonteCarloRequest(BaseModel):
    returns: dict  # {date_str: return_value}
    n_sims: int = 1000
    n_days: int = 252


class RunStrategyRequest(BaseModel):
    signal_code: str
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1_000_000
    commission_rate: float = 0.001
    slippage: float = 0.001
    stamp_tax: float = 0.0005
    normalize: str = "none"  # none / long_only / dollar_neutral
    risk_free_rate: float = 0.03
    take_profit: float = 0.0
    stop_loss: float = 0.0
    trailing_stop: float = 0.0


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


@router.post("/run-strategy")
async def run_strategy(req: RunStrategyRequest):
    """基于本地行情数据执行策略回测：执行信号代码 → 回测 → 绩效报告

    信号代码在 OpenSandbox 容器中隔离执行（Docker 不可用时降级进程内），
    见 services/sandbox.run_signals；回测计算本身在宿主机进行。
    """
    from backend.services.sandbox import run_signals

    # 1. 加载真实行情（无数据时返回明确错误）
    try:
        panels = market_data.load_price_panels(
            codes=req.stock_pool,
            start_date=req.start_date,
            end_date=req.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    prices = panels["close"]

    # 2. 在沙箱（或降级进程内）执行信号代码，要求定义 generate_signals(prices, **kwargs)
    try:
        signals_df, sandboxed = await run_signals(req.signal_code, prices)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"信号生成失败: {e}")
        raise HTTPException(status_code=400, detail=f"信号代码执行失败: {e}")

    if signals_df is None or signals_df.empty:
        raise HTTPException(
            status_code=400, detail="信号为空 — 请检查信号逻辑与数据区间"
        )

    # 3. 回测 + 绩效（接入停牌/涨跌停等参考面板，缺失项记入 assumptions）
    try:
        reference = market_data.load_reference_panels(
            close=prices, volume=panels.get("volume")
        )
        result = backtest_analysis.run_backtest(
            signals=signals_df,
            prices=prices,
            initial_capital=req.initial_capital,
            commission_rate=req.commission_rate,
            slippage=req.slippage,
            stamp_tax=req.stamp_tax,
            normalize=req.normalize,
            tradable_mask=reference["tradable_mask"],
            up_limit=reference["up_limit"],
            down_limit=reference["down_limit"],
            high=panels.get("high"),
            low=panels.get("low"),
            take_profit=req.take_profit,
            stop_loss=req.stop_loss,
            trailing_stop=req.trailing_stop,
        )
        equity_curve = result["equity_curve"]
        strategy_returns = result["strategy_returns"]

        tear = backtest_analysis.performance_tear_sheet(
            returns=strategy_returns,
            risk_free_rate=req.risk_free_rate,
        )
        dd = backtest_analysis.drawdown_analysis(strategy_returns)

        def _ser(s) -> dict:
            return {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in s.items()
            }

        return {
            "status": "ok",
            "initial_capital": req.initial_capital,
            "sandboxed": sandboxed,
            "equity_curve": _ser(equity_curve),
            "strategy_returns": _ser(strategy_returns),
            "drawdown_series": _ser(dd["drawdown_series"]),
            "tear_sheet": {**tear, "max_drawdown": dd["max_drawdown"]},
            "assumptions": result["assumptions"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"回测执行失败: {e}")
        raise HTTPException(status_code=400, detail=f"回测执行失败: {e}")


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
            stamp_tax=req.stamp_tax,
            normalize=req.normalize,
            take_profit=req.take_profit,
            stop_loss=req.stop_loss,
            trailing_stop=req.trailing_stop,
        )

        # 序列化
        equity_curve = result["equity_curve"]
        strategy_returns = result["strategy_returns"]

        total_return = (
            float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)
            if len(equity_curve) > 0
            else 0.0
        )

        return {
            "status": "ok",
            "total_return": total_return,
            "equity_curve": {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in equity_curve.items()
            },
            "strategy_returns": {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in strategy_returns.items()
            },
            "initial_capital": req.initial_capital,
            "assumptions": result["assumptions"],
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


# ── 回测记录（backtest_runs：落库 + 8 阶段进度，QUBE 画板与回测中心共用）──


class CreateRunRequest(BaseModel):
    strategy_id: str = ""
    strategy_name: str = ""
    session_id: str = ""
    signal_code: str = ""  # 空则从 strategy_id 读策略代码
    period_start: str = ""
    period_end: str = ""
    init_balance: float = 1_000_000
    commission_rate: float = 0.001
    slippage: float = 0.001
    stock_pool: list[str] = []


@router.post("/runs")
async def create_run(req: CreateRunRequest):
    """创建并后台执行一次回测；前端轮询 GET /runs/{id} 直至 done/error"""
    from backend.services.qube_research import (
        create_backtest_run,
        execute_backtest_run,
    )

    code = req.signal_code
    name = req.strategy_name
    if req.strategy_id and not code.strip():
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT name, code FROM strategies WHERE id = ?", (req.strategy_id,)
            )
            row = await cursor.fetchone()
        finally:
            await db.close()
        if not row:
            raise HTTPException(status_code=404, detail="策略不存在")
        code = row["code"]
        name = name or row["name"]
    if not code.strip():
        raise HTTPException(status_code=400, detail="策略代码为空，无法回测")

    run_id = await create_backtest_run(
        req.strategy_id,
        name,
        req.session_id,
        code,
        req.model_dump(
            exclude={"strategy_id", "strategy_name", "session_id", "signal_code"}
        ),
    )

    async def _run():
        try:
            await execute_backtest_run(run_id)
        except Exception:
            pass  # 错误已落库（status=error）

    asyncio.create_task(_run())
    return {"id": run_id, "status": "running"}


@router.get("/runs")
async def list_runs(strategy_id: str = "", session_id: str = "", limit: int = 50):
    """回测记录列表（不含大字段；画板历史下拉与回测中心列表共用）"""
    from backend.services.qube_research import run_row_to_dict

    db = await get_db()
    try:
        where, args = [], []
        if strategy_id:
            where.append("strategy_id = ?")
            args.append(strategy_id)
        if session_id:
            where.append("session_id = ?")
            args.append(session_id)
        sql = "SELECT * FROM backtest_runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        cursor = await db.execute(sql, (*args, limit))  # noqa: S608
        return {"runs": [run_row_to_dict(r) for r in await cursor.fetchall()]}
    finally:
        await db.close()


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """回测详情（含净值曲线/交易明细/日志）"""
    from backend.services.qube_research import run_row_to_dict

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM backtest_runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="回测记录不存在")
        return run_row_to_dict(row, with_detail=True)
    finally:
        await db.close()
