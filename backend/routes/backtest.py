"""回测路由（含回测记录 backtest_runs：8 阶段进度落库，画板/回测中心共用）"""

import asyncio
import json

import pandas as pd
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from backend.database import get_db
from backend.services import market_data, tasks
from backend.services.backtest_analysis import backtest_analysis

router = APIRouter()

# 回测后台任务并发上限（懒创建，避免 import 时绑定事件循环）。
# 注意：变量与函数不能同名，否则 def 会把变量绑定成函数对象，
# 调用 _backtest_sem() 时返回函数本身而非 Semaphore。
_backtest_sem_obj: asyncio.Semaphore | None = None


def _backtest_sem() -> asyncio.Semaphore:
    global _backtest_sem_obj
    if _backtest_sem_obj is None:
        _backtest_sem_obj = asyncio.Semaphore(2)
    return _backtest_sem_obj


# ── 请求模型 ─────────────────────────────────────────────────


class RunBacktestRequest(BaseModel):
    signals: dict  # {code: {date_str: value}}（列优先，与面板转 dict 一致）
    prices: dict  # {code: {date_str: price}}
    initial_capital: float = 1_000_000
    commission_rate: float = 0.001
    slippage: float = 0.001
    stamp_tax: float = 0.0005
    normalize: str = "long_only"  # 仅支持普通股票多头；不融资、不融券、不做空
    max_gross_exposure: float = 1.0  # 最大日总仓位 Σ|w|；普通股票投资固定为 100%
    take_profit: float = 0.0  # 单仓止盈比例（0=关闭）
    stop_loss: float = 0.0  # 单仓止损比例（0=关闭）
    trailing_stop: float = 0.0  # 移动止损比例（0=关闭）
    shortable_codes: list[str] = []  # 兼容旧字段；系统只做多，已不参与交易逻辑
    execute_at: str = "next_close"  # next_close=信号日收盘 / tail=尾盘 / next_open=次日开盘
    delisting_loss: float = 0.0  # 数据提前截止标的的强制清算折价


class TearSheetRequest(BaseModel):
    returns: dict  # {date_str: return_value}
    benchmark_returns: dict | None = None  # {date_str: return_value}
    risk_free_rate: float = 0.03


class MonteCarloRequest(BaseModel):
    returns: dict  # {date_str: return_value}
    n_sims: int = 1000
    n_days: int = 252
    method: str = "block"  # block（块自助，默认）/ gaussian（正态）
    block_size: int = 20


class RunStrategyRequest(BaseModel):
    signal_code: str
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""
    benchmark_code: str = ""  # 可选基准（如 000300.SH），用于相对收益指标
    initial_capital: float = 1_000_000
    commission_rate: float = 0.001
    slippage: float = 0.001
    stamp_tax: float = 0.0005
    normalize: str = "long_only"  # 仅支持普通股票多头；不融资、不融券、不做空
    max_gross_exposure: float = 1.0  # 最大日总仓位 Σ|w|；普通股票投资固定为 100%
    risk_free_rate: float = 0.03
    take_profit: float = 0.0
    stop_loss: float = 0.0
    trailing_stop: float = 0.0
    execute_at: str = "next_close"  # next_close / tail / next_open（开→收计收益）
    shortable_codes: list[str] = []  # 兼容旧字段；系统只做多，已不参与交易逻辑
    delisting_loss: float = 0.0  # 数据提前截止标的的强制清算折价


# ── 工具函数 ─────────────────────────────────────────────────


def _dict_to_series(d: dict) -> pd.Series:
    s = pd.Series(d)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    return s


def _dict_to_df(d: dict) -> pd.DataFrame:
    return pd.DataFrame(d).apply(pd.to_numeric, errors="coerce")


# ── 路由 ─────────────────────────────────────────────────────


@router.post("/run-strategy")
async def run_strategy(req: RunStrategyRequest):
    """基于本地行情数据执行策略回测：执行信号代码 → 回测 → 绩效报告

    信号代码在 OpenSandbox 容器中隔离执行（Docker 不可用时降级进程内），
    见 services/sandbox.run_signals；回测计算本身在宿主机进行。
    """
    from backend.services.sandbox import run_signals

    # 1. 加载真实行情（无数据时返回明确错误）；重活放线程池，避免阻塞事件循环
    try:
        panels = await asyncio.to_thread(
            market_data.load_price_panels,
            codes=req.stock_pool
            or market_data.list_cached_codes("1d", exclude_indices=True),
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
        reference = await asyncio.to_thread(
            market_data.load_reference_panels, close=prices, volume=panels.get("volume")
        )
        # 普通多头：不做空，shortable 始终为 None（不参与交易逻辑）
        shortable = None
        result = await asyncio.to_thread(
            backtest_analysis.run_backtest,
            signals=signals_df,
            prices=prices,
            initial_capital=req.initial_capital,
            commission_rate=req.commission_rate,
            slippage=req.slippage,
            stamp_tax=req.stamp_tax,
            normalize=req.normalize,
            tradable_mask=reference["tradable_mask"],
            shortable_mask=shortable,
            up_limit=reference["up_limit"],
            down_limit=reference["down_limit"],
            high=panels.get("high"),
            low=panels.get("low"),
            take_profit=req.take_profit,
            stop_loss=req.stop_loss,
            trailing_stop=req.trailing_stop,
            execute_at=req.execute_at,
            open_prices=panels.get("open") if req.execute_at == "next_open" else None,
            delisting_loss=req.delisting_loss,
            max_gross_exposure=req.max_gross_exposure,
        )
        equity_curve = result["equity_curve"]
        strategy_returns = result["strategy_returns"]

        benchmark_returns = None
        if req.benchmark_code.strip():
            try:
                bench_panels = await asyncio.to_thread(
                    market_data.load_price_panels,
                    codes=[req.benchmark_code.strip()],
                    start_date=req.start_date,
                    end_date=req.end_date,
                )
                bench_close = bench_panels["close"]
                benchmark_returns = market_data.build_return_panel(bench_close).iloc[:, 0]
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"基准行情加载失败 {req.benchmark_code}: {e}",
                )

        tear, dd = await asyncio.to_thread(
            lambda: (
                backtest_analysis.performance_tear_sheet(
                    returns=strategy_returns,
                    benchmark_returns=benchmark_returns,
                    risk_free_rate=req.risk_free_rate,
                ),
                backtest_analysis.drawdown_analysis(strategy_returns),
            )
        )

        def _ser(s) -> dict:
            return {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in s.items()
            }

        tear_sheet = {**tear, "max_drawdown": dd["max_drawdown"]}

        # 所有回测入口统一落库 + provenance，保证回测中心可追溯
        from backend.services.backtest_records import persist_backtest_run

        result["prices"] = prices
        run_params = req.model_dump()
        run_params["n_stocks"] = int(signals_df.shape[1])
        run_params["n_days"] = int(signals_df.shape[0])
        run_id = await persist_backtest_run(
            params=run_params,
            result=result,
            metrics={
                **tear_sheet,
                "trade_count": 0,
                "final_equity": float(equity_curve.iloc[-1]),
            },
            strategy_id="",
            strategy_name=f"run-strategy·{req.signal_code.strip()[:24]}",
            source="run_strategy",
        )

        return {
            "status": "ok",
            "backtest_run_id": run_id,
            "initial_capital": req.initial_capital,
            "sandboxed": sandboxed,
            "equity_curve": _ser(equity_curve),
            "strategy_returns": _ser(strategy_returns),
            "drawdown_series": _ser(dd["drawdown_series"]),
            "tear_sheet": tear_sheet,
            "cost_summary": result["cost_summary"],
            "assumptions": result["assumptions"],
            "delisting_events": result.get("delisting_events", []),
            "leverage_summary": result.get("leverage_summary", {}),
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

        signals_df = _dict_to_df(req.signals)
        prices_df = _dict_to_df(req.prices)

        # 普通多头：不做空，shortable 始终为 None（不参与交易逻辑）
        shortable = None

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
            shortable_mask=shortable,
            execute_at=req.execute_at,
            delisting_loss=req.delisting_loss,
            max_gross_exposure=req.max_gross_exposure,
        )

        # 序列化
        equity_curve = result["equity_curve"]
        strategy_returns = result["strategy_returns"]

        total_return = (
            float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)
            if len(equity_curve) > 0
            else 0.0
        )

        from backend.services.backtest_records import persist_backtest_run

        result["prices"] = prices_df
        run_params = {k: v for k, v in req.model_dump().items() if k not in ("signals", "prices")}
        run_params["n_stocks"] = int(signals_df.shape[1])
        run_params["n_days"] = int(signals_df.shape[0])
        run_id = await persist_backtest_run(
            params=run_params,
            result=result,
            metrics={"total_return": total_return, "final_equity": float(equity_curve.iloc[-1])},
            strategy_name="run-api",
            source="run_api",
        )

        return {
            "status": "ok",
            "backtest_run_id": run_id,
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
            "cost_summary": result["cost_summary"],
            "assumptions": result["assumptions"],
            "delisting_events": result.get("delisting_events", []),
            "leverage_summary": result.get("leverage_summary", {}),
        }
    except Exception as e:
        logger.error(f"回测执行失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


class CapacityRequest(BaseModel):
    signals: dict  # {date_str: {code: signal_value}}
    prices: dict  # {date_str: {code: price}}
    amount: dict | None = None  # {date_str: {code: 成交额}}（建议提供）
    normalize: str = "long_only"  # 仅支持普通股票多头
    participation_rate: float = 0.1
    capital_levels: list[float] | None = None
    adv_window: int = 20  # 平均成交额滚动窗口（交易日）
    lot_size: int = 100  # A 股整手股数（写入 assumptions，不改变金额口径）


@router.post("/capacity")
async def capacity(req: CapacityRequest):
    """容量分析：信号在参与率约束下可容纳的资金规模（需成交额面板）"""
    try:

        signals_df = _dict_to_df(req.signals)
        prices_df = _dict_to_df(req.prices)
        amount_df = _dict_to_df(req.amount) if req.amount else None

        result = backtest_analysis.capacity_analysis(
            signals=signals_df,
            prices=prices_df,
            amount=amount_df,
            normalize=req.normalize,
            participation_rate=req.participation_rate,
            capital_levels=req.capital_levels,
            adv_window=req.adv_window,
            lot_size=req.lot_size,
        )
        result["status"] = "ok"
        return result
    except Exception as e:
        logger.error(f"容量分析失败: {e}")
        raise HTTPException(status_code=400, detail=f"容量分析失败: {e}")



class PortfolioRequest(BaseModel):
    factor_ids: list[int] = []  # 空 = 取整个因子池
    stock_pool: list[str] = []  # 空 = 本地缓存中的股票池（自动剔除指数缓存）
    combine_method: str = "equal"  # equal / ic_weighted
    top_n: int = 20  # 每日截面做多只数（0=全部正值做多）
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1_000_000
    commission_rate: float = 0.001
    slippage: float = 0.001
    stamp_tax: float = 0.0005
    take_profit: float = 0.0
    stop_loss: float = 0.0
    trailing_stop: float = 0.0
    delisting_loss: float = 0.0  # 数据提前截止标的的强制清算折价


@router.post("/portfolio")
async def portfolio_backtest(req: PortfolioRequest):
    """因子池 → 组合回测闭环：因子求值 → 合成（等权/IC加权）→ Top-N 做多 →
    回测 → 绩效 → 风格归因（研究主链路一键打通）"""
    from backend.services.factor_research import extract_formula

    db = await get_db()
    try:
        if req.factor_ids:
            marks = ",".join("?" * len(req.factor_ids))
            cursor = await db.execute(
                f"SELECT id, factor_name, description, metric_source FROM preset_factors "
                f"WHERE id IN ({marks}) ORDER BY id",
                req.factor_ids,
            )
        else:
            cursor = await db.execute(
                "SELECT pf.id, pf.factor_name, pf.description, pf.metric_source "
                "FROM preset_factors pf "
                "INNER JOIN factor_pool fp ON fp.factor_id = pf.id ORDER BY fp.added_at DESC"
            )
        rows = [dict(r) for r in await cursor.fetchall()]
    finally:
        await db.close()

    factors = []
    skipped: list[str] = []
    for r in rows:
        if r.get("metric_source") != "local_recalc":
            skipped.append(str(r["factor_name"]))
            continue
        formula = extract_formula(r.get("description"))
        if formula:
            factors.append(
                {"factor_id": r["id"], "factor_name": r["factor_name"], "formula": formula}
            )
    if skipped:
        raise HTTPException(
            status_code=400,
            detail="以下因子指标仍为外部参考值，未基于本地 QMT 样本重算，禁止进入组合回测：\n"
            + "、".join(skipped[:10])
            + ("…" if len(skipped) > 10 else "")
            + "。请先在因子详情页重算后再试。",
        )
    if not factors:
        raise HTTPException(status_code=400, detail="所选因子均无可用公式（仅支持公式型因子）")

    try:
        result = await asyncio.to_thread(
            backtest_analysis.portfolio_backtest,
            factors=factors,
            stock_pool=req.stock_pool,
            start_date=req.start_date,
            end_date=req.end_date,
            combine_method=req.combine_method,
            top_n=req.top_n,
            initial_capital=req.initial_capital,
            commission_rate=req.commission_rate,
            slippage=req.slippage,
            stamp_tax=req.stamp_tax,
            take_profit=req.take_profit,
            stop_loss=req.stop_loss,
            trailing_stop=req.trailing_stop,
            delisting_loss=req.delisting_loss,
        )
        # 溯源
        try:
            from backend.routes.factor import _spawn_provenance

            await _spawn_provenance(
                kind="backtest",
                entity_id="portfolio",
                entity_name=f"组合回测({len(factors)}因子,{req.combine_method},Top{req.top_n})",
                params=req.model_dump(),
                metrics={
                    "total_return": result.get("tear_sheet", {}).get("total_return"),
                    "sharpe_ratio": result.get("tear_sheet", {}).get("sharpe_ratio"),
                    "alpha_cum": (result.get("attribution") or {}).get("alpha_cum"),
                },
                notes="因子池组合回测（等权/IC加权合成 + Top-N 多空）",
                source="portfolio",
            )
        except Exception:
            pass
        result["status"] = "ok"
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"组合回测失败: {e}")
        raise HTTPException(status_code=400, detail=f"组合回测失败: {e}")


class SensitivityRequest(BaseModel):
    signal_code: str  # 需定义 generate_signals(prices, **kwargs)
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""
    param_grid: dict[str, list]  # {commission_rate: [0.0005, 0.001, 0.002], ...}
    base_params: dict = {}


@router.post("/sensitivity")
async def sensitivity(req: SensitivityRequest):
    """回测参数敏感性（网格扫描）：信号只算一次，逐参数组合回测对比

    支持扫描参数：commission_rate / slippage / stamp_tax /
    take_profit / stop_loss / trailing_stop（normalize 固定为 long_only）
    """
    from backend.services.sandbox import run_signals

    if not req.param_grid:
        raise HTTPException(status_code=400, detail="param_grid 为空，无可扫描的参数")

    try:
        panels = await asyncio.to_thread(
            market_data.load_price_panels,
            codes=req.stock_pool
            or market_data.list_cached_codes("1d", exclude_indices=True),
            start_date=req.start_date,
            end_date=req.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    prices = panels["close"]

    try:
        signals_df, sandboxed = await run_signals(req.signal_code, prices)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if signals_df is None or signals_df.empty:
        raise HTTPException(status_code=400, detail="信号为空 — 请检查信号逻辑与数据区间")

    reference = await asyncio.to_thread(
        market_data.load_reference_panels, prices, panels.get("volume")
    )
    try:
        result = await asyncio.to_thread(
            backtest_analysis.sensitivity_scan,
            signals=signals_df,
            prices=prices,
            param_grid=req.param_grid,
            base=req.base_params,
            tradable_mask=reference["tradable_mask"],
            up_limit=reference["up_limit"],
            down_limit=reference["down_limit"],
            high=panels.get("high"),
            low=panels.get("low"),
        )
        result["status"] = "ok"
        result["sandboxed"] = sandboxed
        result["n_stocks"] = int(prices.shape[1])
        return result
    except Exception as e:
        logger.error(f"参数敏感性扫描失败: {e}")
        raise HTTPException(status_code=400, detail=f"参数敏感性扫描失败: {e}")


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
            method=req.method,
            block_size=req.block_size,
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
    stamp_tax: float = 0.0005
    normalize: str = "long_only"  # 仅支持普通股票多头
    max_gross_exposure: float = 1.0
    take_profit: float = 0.0
    stop_loss: float = 0.0
    trailing_stop: float = 0.0
    stock_pool: list[str] = []
    execute_at: str = "next_close"  # next_close / tail / next_open
    delisting_loss: float = 0.0  # 数据提前截止标的的强制清算折价


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
        # 并发上限：避免无限堆积的重回测任务耗尽线程/内存
        sem = _backtest_sem()
        async with sem:
            try:
                await execute_backtest_run(run_id)
            except Exception:
                pass  # 错误已落库（status=error）

    # 必须持有任务引用：事件循环只弱引用 task，路由返回后任务可能被 GC，
    # 表现为回测永远停在 task_start。
    tasks.spawn(_run())
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
        cursor = await db.execute(sql, (*args, limit))
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


@router.get("/runs/{run_id}/export")
async def export_run(run_id: str, part: str = "equity"):
    """导出回测结果 CSV（equity=净值曲线 / returns=日收益 / trades=交易明细 / log=日志）

    研究交付与离线复核：明细数据可直接导入外部工具做二次分析。
    """
    from fastapi.responses import StreamingResponse

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM backtest_runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
    finally:
        await db.close()
    if not row:
        raise HTTPException(status_code=404, detail="回测记录不存在")
    if row["status"] != "done":
        raise HTTPException(status_code=400, detail="回测尚未完成，无结果可导出")

    import io

    import pandas as pd

    if part == "equity":
        data = json.loads(row["equity_json"] or "[]")
        df = pd.DataFrame(data).set_index("ts") if data else pd.DataFrame()
        fname = f"{run_id[:8]}_equity.csv"
    elif part == "returns":
        eq = json.loads(row["equity_json"] or "[]")
        if not eq:
            df = pd.DataFrame()
        else:
            df = pd.DataFrame(eq).set_index("ts")
            df["equity"] = df["equity"].astype(float)
            df["returns"] = df["equity"].pct_change().fillna(0.0)
        fname = f"{run_id[:8]}_returns.csv"
    elif part == "trades":
        data = json.loads(row["trades_json"] or "[]")
        df = pd.DataFrame(data) if data else pd.DataFrame()
        fname = f"{run_id[:8]}_trades.csv"
    elif part == "log":
        return StreamingResponse(
            iter([(row["log_text"] or "") + "\n"]),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{run_id[:8]}_log.txt"'
            },
        )
    else:
        raise HTTPException(
            status_code=400, detail="part 可选 equity / returns / trades / log"
        )

    def _generate():
        buf = io.StringIO()
        df.to_csv(buf)
        yield buf.getvalue()

    return StreamingResponse(
        _generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


class WalkForwardRequest(BaseModel):
    factors: list[dict] = []  # [{factor_name, formula}]
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""
    combine_method: str = "equal"  # equal / ic_weighted（训练窗口 RankIC 加权）
    top_n: int = 20
    train_days: int = 120
    test_days: int = 60
    initial_capital: float = 1_000_000
    commission_rate: float = 0.001
    slippage: float = 0.001
    stamp_tax: float = 0.0005
    take_profit: float = 0.0
    stop_loss: float = 0.0
    trailing_stop: float = 0.0
    delisting_loss: float = 0.0  # 数据提前截止标的的强制清算折价


@router.post("/walk-forward")
async def walk_forward(req: WalkForwardRequest):
    """组合 walk-forward 回测：滚动锚定训练/测试划分，拼接样本外净值

    防过拟合最后一环：与因子样本外验证（只验 IC）互补，这里是完整组合闭环。
    返回每折划分、样本外净值/绩效，以及全样本参考（直观展示过拟合差距）。
    """
    try:
        result = await asyncio.to_thread(
            backtest_analysis.walk_forward_portfolio,
            factors=req.factors,
            stock_pool=req.stock_pool,
            start_date=req.start_date,
            end_date=req.end_date,
            combine_method=req.combine_method,
            top_n=req.top_n,
            train_days=req.train_days,
            test_days=req.test_days,
            initial_capital=req.initial_capital,
            commission_rate=req.commission_rate,
            slippage=req.slippage,
            stamp_tax=req.stamp_tax,
            take_profit=req.take_profit,
            stop_loss=req.stop_loss,
            trailing_stop=req.trailing_stop,
            delisting_loss=req.delisting_loss,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"walk-forward 回测失败: {e}")
        raise HTTPException(status_code=400, detail=f"walk-forward 回测失败: {e}")
