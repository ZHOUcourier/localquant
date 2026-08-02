"""QUBE 投研编排 — 因子分析（9 阶段）与策略回测（8 阶段）落库执行

阶段码与文案对齐参考站（panda）语义：
- 因子分析: task_start/factor_build/market_data/clean/returns/grouping/analysis/summary/complete
- 回测:     task_start/queued/validation/engine_start/market_init/simulation/summary/complete

执行模型：REST/Agent 工具先 create_* 落一行 running 记录，随后 execute_*
逐阶段推进并把 progress 回写 DB（前端画板轮询详情直至 done/error）。
计算密集步骤放 asyncio.to_thread，不阻塞事件循环；不设执行超时。
"""

import asyncio
import json
import time
import uuid

from loguru import logger

from backend.database import get_db

FACTOR_STAGES: list[tuple[str, str]] = [
    ("task_start", "任务开始"),
    ("factor_build", "构建因子"),
    ("market_data", "加载并对齐行情"),
    ("clean", "清洗并标准化因子"),
    ("returns", "计算收益和滞后项"),
    ("grouping", "因子分组"),
    ("analysis", "计算分组收益和 IC"),
    ("summary", "汇总指标和完整图表"),
    ("complete", "分析完成"),
]

BACKTEST_STAGES: list[tuple[str, str]] = [
    ("task_start", "任务开始"),
    ("queued", "等待计算资源"),
    ("validation", "校验策略与参数"),
    ("engine_start", "提交并启动回测引擎"),
    ("market_init", "加载行情并初始化账户"),
    ("simulation", "按交易日执行回测"),
    ("summary", "汇总指标与交易记录"),
    ("complete", "回测完成"),
]


def _progress(
    stages: list[tuple[str, str]], done_until: int, error: bool = False
) -> dict:
    """构造 progress JSON：done_until 之前的阶段已完成，done_until 为进行中"""
    items = []
    for i, (code, label) in enumerate(stages):
        if i < done_until:
            status = "done"
        elif i == done_until:
            status = "error" if error else "running"
        else:
            status = "pending"
        items.append({"code": code, "label": label, "status": status})
    total = len(stages)
    percent = round(min(done_until, total) / total * 100)
    if done_until >= total:
        percent = 100
    current = stages[min(done_until, total - 1)]
    return {
        "stage": current[0],
        "label": current[1],
        "percent": percent,
        "current": min(done_until + 1, total),
        "total": total,
        "stages": items,
    }


async def _update(table: str, row_id: str, **fields) -> None:
    db = await get_db()
    try:
        keys = ", ".join(f"{k} = ?" for k in fields)
        await db.execute(
            f"UPDATE {table} SET {keys} WHERE id = ?",  # noqa: S608
            (*fields.values(), row_id),
        )
        await db.commit()
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# 因子分析
# ---------------------------------------------------------------------------


DEFAULT_ANALYSIS_PARAMS = {
    "period_start": "",
    "period_end": "",
    "adjustment_cycle": 5,
    "group_number": 5,
    "factor_direction": 1,
    "stock_pool": [],
}


async def create_factor_analysis(factor_id: str, session_id: str, params: dict) -> str:
    """落一行 running 分析记录并返回 id（执行由 execute_factor_analysis 负责）"""
    merged = {
        **DEFAULT_ANALYSIS_PARAMS,
        **{k: v for k, v in params.items() if v not in (None, "")},
    }
    aid = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO factor_analyses (id, factor_id, session_id, status, "
            "progress_json, params_json, created_at) VALUES (?, ?, ?, 'running', ?, ?, ?)",
            (
                aid,
                factor_id,
                session_id,
                json.dumps(_progress(FACTOR_STAGES, 0), ensure_ascii=False),
                json.dumps(merged, ensure_ascii=False),
                int(time.time()),
            ),
        )
        await db.commit()
    finally:
        await db.close()
    return aid


async def execute_factor_analysis(analysis_id: str) -> dict:
    """逐阶段执行因子分析，进度实时回写；返回 {summary} 摘要（供 Agent 回传模型）"""

    async def stage(i: int) -> None:
        await _update(
            "factor_analyses",
            analysis_id,
            progress_json=json.dumps(_progress(FACTOR_STAGES, i), ensure_ascii=False),
        )

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT a.*, f.name AS factor_name, f.code_type, f.code "
            "FROM factor_analyses a JOIN qube_factors f ON f.id = a.factor_id "
            "WHERE a.id = ?",
            (analysis_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    if not row:
        raise ValueError(f"分析记录不存在: {analysis_id}")
    params = json.loads(row["params_json"] or "{}")

    try:
        # 1. task_start → 2. factor_build：准备因子表达式
        await stage(1)
        code_type = row["code_type"] or "formula"
        code = row["code"] or ""
        if not code.strip():
            raise ValueError("因子代码/公式为空")

        # 2 → 3. market_data：加载行情面板
        await stage(2)
        from backend.services import market_data

        panels = await asyncio.to_thread(
            market_data.load_price_panels,
            list(params.get("stock_pool") or []),
            str(params.get("period_start") or ""),
            str(params.get("period_end") or ""),
        )
        close = panels["close"]

        # 3 → 4. clean：求值因子 + 方向调整 + 清洗
        await stage(3)

        def _eval_factor():
            import pandas as pd

            from backend.services.factor_operators import build_operator_namespace

            ctx = build_operator_namespace(panels)
            if code_type == "formula":
                lines = [
                    ln
                    for ln in code.strip().splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
                if len(lines) > 1:
                    exec_ctx = dict(ctx)
                    exec("\n".join(lines[:-1]), {"__builtins__": {}}, exec_ctx)  # noqa: S102
                    factor = eval(lines[-1], {"__builtins__": {}}, exec_ctx)  # noqa: S307
                else:
                    factor = eval(code, {"__builtins__": {}}, ctx)  # noqa: S307
            else:
                exec_ctx = dict(ctx)
                exec(code, {"__builtins__": __builtins__}, exec_ctx)  # noqa: S102
                fn = exec_ctx.get("compute_factor")
                factor = (
                    fn(close=close, volume=panels.get("volume"))
                    if callable(fn)
                    else exec_ctx.get("factor_data")
                )
            if factor is None:
                raise ValueError("代码未定义 compute_factor 函数或 factor_data 变量")
            if isinstance(factor, pd.Series):
                factor = factor.to_frame()
            if not isinstance(factor, pd.DataFrame):
                raise ValueError(
                    f"因子结果应为 DataFrame，得到 {type(factor).__name__}"
                )
            factor = factor.dropna(how="all")
            if factor.empty:
                raise ValueError("因子计算结果为空（可能回看期超过数据长度）")
            direction = int(params.get("factor_direction") or 1)
            return factor * direction

        factor = await asyncio.to_thread(_eval_factor)

        # 4 → 5. returns：远期收益
        await stage(4)
        returns = await asyncio.to_thread(lambda: close.pct_change())

        # 5 → 6. grouping → 7. analysis → 8. summary：完整分析
        await stage(5)
        cycle = int(params.get("adjustment_cycle") or 5)
        n_groups = int(params.get("group_number") or 5)
        periods = sorted({cycle, 1, 5, 10, 20})
        periods.remove(cycle)
        periods = [cycle, *periods]
        await stage(6)
        from backend.services.factor_research import factor_research

        mask = None
        try:
            from backend.services.market_data import build_cross_section_mask

            mask = build_cross_section_mask(panels)
        except Exception:
            mask = None
            logger.warning("无法构建可交易掩码，QUBE 因子研究将不做停牌/ST 过滤", exc_info=True)
        result = await asyncio.to_thread(
            factor_research.full_factor_analysis,
            factor,
            returns,
            periods,
            n_groups,
            mask=mask,
        )
        await stage(7)

        metrics = {"summary": result["summary"], "ic_summary": result["ic_summary"]}
        group_return = {
            "group_perf": result["group_perf"],
            "mean_return_by_group": result["mean_return_by_group"],
        }
        charts = {
            "ic": result["ic"],
            "rank_ic": result["rank_ic"],
            "group_cumulative": result["group_cumulative"],
            "group_excess_cumulative": result["group_excess_cumulative"],
            "long_short_cumulative": result["long_short_cumulative"],
        }

        # 8 → 9. complete
        await _update(
            "factor_analyses",
            analysis_id,
            status="done",
            progress_json=json.dumps(
                _progress(FACTOR_STAGES, len(FACTOR_STAGES)), ensure_ascii=False
            ),
            metrics_json=json.dumps(metrics, ensure_ascii=False, default=str),
            group_return_json=json.dumps(group_return, ensure_ascii=False, default=str),
            charts_json=json.dumps(charts, ensure_ascii=False, default=str),
            finished_at=int(time.time()),
        )
        return {"analysis_id": analysis_id, "summary": result["summary"]}
    except Exception as e:
        logger.error(f"因子分析 {analysis_id} 失败: {e}")
        # 找到当前进行中的阶段标记 error
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT progress_json FROM factor_analyses WHERE id = ?", (analysis_id,)
            )
            r = await cursor.fetchone()
        finally:
            await db.close()
        prog = json.loads(r["progress_json"] or "{}") if r else {}
        idx = max((prog.get("current") or 1) - 1, 0)
        await _update(
            "factor_analyses",
            analysis_id,
            status="error",
            error=str(e)[:500],
            progress_json=json.dumps(
                _progress(FACTOR_STAGES, idx, error=True), ensure_ascii=False
            ),
            finished_at=int(time.time()),
        )
        raise


def analysis_row_to_dict(row, with_detail: bool = False) -> dict:
    d = {
        "id": row["id"],
        "factor_id": row["factor_id"],
        "session_id": row["session_id"],
        "status": row["status"],
        "progress": json.loads(row["progress_json"] or "{}"),
        "params": json.loads(row["params_json"] or "{}"),
        "error": row["error"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
    }
    if with_detail:
        d["metrics"] = json.loads(row["metrics_json"] or "{}")
        d["group_return"] = json.loads(row["group_return_json"] or "[]")
        d["charts"] = json.loads(row["charts_json"] or "{}")
    else:
        d["metrics"] = json.loads(row["metrics_json"] or "{}").get("summary", {})
    return d


# ---------------------------------------------------------------------------
# 策略回测
# ---------------------------------------------------------------------------


DEFAULT_BACKTEST_PARAMS = {
    "period_start": "",
    "period_end": "",
    "init_balance": 1_000_000,
    "commission_rate": 0.001,
    "slippage": 0.001,
    "stamp_tax": 0.0005,
    "normalize": "none",
    "take_profit": 0.0,
    "stop_loss": 0.0,
    "trailing_stop": 0.0,
    "frequency": "1d",
    "stock_pool": [],
}


async def create_backtest_run(
    strategy_id: str,
    strategy_name: str,
    session_id: str,
    code: str,
    params: dict,
) -> str:
    """落一行 running 回测记录（code 存进 params_json.signal_code）"""
    merged = {
        **DEFAULT_BACKTEST_PARAMS,
        **{k: v for k, v in params.items() if v not in (None, "")},
    }
    merged["signal_code"] = code
    rid = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO backtest_runs (id, strategy_id, strategy_name, session_id, "
            "status, progress_json, params_json, created_at) "
            "VALUES (?, ?, ?, ?, 'running', ?, ?, ?)",
            (
                rid,
                strategy_id,
                strategy_name,
                session_id,
                json.dumps(_progress(BACKTEST_STAGES, 0), ensure_ascii=False),
                json.dumps(merged, ensure_ascii=False),
                int(time.time()),
            ),
        )
        await db.commit()
    finally:
        await db.close()
    return rid


async def execute_backtest_run(run_id: str) -> dict:
    """逐阶段执行回测，落库净值/交易明细/日志；返回指标摘要"""

    async def stage(i: int) -> None:
        await _update(
            "backtest_runs",
            run_id,
            progress_json=json.dumps(_progress(BACKTEST_STAGES, i), ensure_ascii=False),
        )

    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM backtest_runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
    finally:
        await db.close()
    if not row:
        raise ValueError(f"回测记录不存在: {run_id}")
    params = json.loads(row["params_json"] or "{}")
    log_lines: list[str] = [f"[INFO] 回测 #{run_id[:8]} 任务开始"]

    try:
        # 1. queued → 2. validation
        await stage(1)
        await stage(2)
        code = str(params.get("signal_code") or "")
        if not code.strip():
            raise ValueError("策略代码为空，无法回测")
        log_lines.append("[INFO] 策略与参数校验通过")

        # 3. engine_start
        await stage(3)

        # 4. market_init：加载行情
        await stage(4)
        from backend.services import market_data

        panels = await asyncio.to_thread(
            market_data.load_price_panels,
            list(params.get("stock_pool") or []),
            str(params.get("period_start") or ""),
            str(params.get("period_end") or ""),
        )
        prices = panels["close"]
        log_lines.append(
            f"[INFO] 行情加载完成：{prices.shape[1]} 只标的 · "
            f"{str(prices.index[0].date())} → {str(prices.index[-1].date())}"
        )

        # 5. simulation：沙箱执行信号 + 向量化回测
        await stage(5)
        from backend.services.backtest_analysis import backtest_analysis
        from backend.services.sandbox import run_signals

        signals_df, sandboxed = await run_signals(code, prices)
        if signals_df is None or signals_df.empty:
            raise ValueError("信号为空 — 请检查信号逻辑与数据区间")
        log_lines.append(
            f"[INFO] 信号生成完成（{'沙箱隔离' if sandboxed else '进程内执行'}）"
        )
        reference = await asyncio.to_thread(
            market_data.load_reference_panels, prices, panels.get("volume")
        )
        init_balance = float(params.get("init_balance") or 1_000_000)
        commission = float(params.get("commission_rate") or 0.001)
        slippage = float(params.get("slippage") or 0.001)
        stamp_tax = float(params.get("stamp_tax") or 0.0005)
        take_profit = float(params.get("take_profit") or 0.0)
        stop_loss = float(params.get("stop_loss") or 0.0)
        trailing_stop = float(params.get("trailing_stop") or 0.0)
        normalize = str(params.get("normalize") or "none")
        result = await asyncio.to_thread(
            lambda: backtest_analysis.run_backtest(
                signals=signals_df,
                prices=prices,
                initial_capital=init_balance,
                commission_rate=commission,
                slippage=slippage,
                stamp_tax=stamp_tax,
                normalize=normalize,
                tradable_mask=reference["tradable_mask"],
                up_limit=reference["up_limit"],
                down_limit=reference["down_limit"],
                high=panels.get("high"),
                low=panels.get("low"),
                take_profit=take_profit,
                stop_loss=stop_loss,
                trailing_stop=trailing_stop,
            )
        )
        for a in result.get("assumptions", []):
            log_lines.append(f"[WARN] 假设: {a}")

        # 6. summary：指标 + 交易明细
        await stage(6)

        def _summarize():
            equity = result["equity_curve"]
            returns = result["strategy_returns"]
            positions = result["positions"]
            tear = backtest_analysis.performance_tear_sheet(returns=returns)
            dd = backtest_analysis.drawdown_analysis(returns)
            equity_list = [
                {"ts": str(k.date() if hasattr(k, "date") else k), "equity": float(v)}
                for k, v in equity.items()
            ]
            # 交易明细：由持仓权重变化推导（|Δw|>1e-6 记一笔，qty 以当日净值折算）
            trades: list[dict] = []
            dw = positions.diff().fillna(positions)
            for ts, drow in dw.iterrows():
                eq = float(equity.get(ts, init_balance))
                for sym, w in drow.items():
                    if w != w or abs(w) < 1e-6:
                        continue
                    price = (
                        float(prices.at[ts, sym])
                        if prices.at[ts, sym] == prices.at[ts, sym]
                        else 0.0
                    )
                    if price <= 0:
                        continue
                    qty = int(abs(w) * eq / price // 100 * 100)
                    fee_rate = commission + slippage + (stamp_tax if w < 0 else 0.0)
                    trades.append(
                        {
                            "ts": str(ts.date() if hasattr(ts, "date") else ts),
                            "symbol": str(sym),
                            "side": "买入" if w > 0 else "卖出",
                            "price": round(price, 3),
                            "qty": qty,
                            "fee": round(abs(w) * eq * fee_rate, 2),
                            "reason": "调仓",
                        }
                    )
            metrics = {
                **tear,
                "max_drawdown": dd["max_drawdown"],
                "trade_count": len(trades),
                "final_equity": float(equity.iloc[-1]) if len(equity) else init_balance,
            }
            # 明细数据量受限时只保留尾部，并显式标注截断，避免 trade_count 与明细不一致
            _TRADE_TAIL = 1000
            trimmed = trades[:_TRADE_TAIL]
            if len(trades) > _TRADE_TAIL:
                metrics["trades_truncated"] = True
                metrics["stored_trade_count"] = len(trimmed)
            return metrics, equity_list, trimmed

        metrics, equity_list, trades = await asyncio.to_thread(_summarize)
        log_lines.append(
            f"[INFO] 回测完成：总收益 {metrics.get('total_return', 0) * 100:.2f}% · "
            f"夏普 {metrics.get('sharpe_ratio', 0):.2f} · "
            f"最大回撤 {metrics.get('max_drawdown', 0) * 100:.2f}% · {len(trades)} 笔交易"
        )

        # 7. complete
        await _update(
            "backtest_runs",
            run_id,
            status="done",
            progress_json=json.dumps(
                _progress(BACKTEST_STAGES, len(BACKTEST_STAGES)), ensure_ascii=False
            ),
            metrics_json=json.dumps(metrics, ensure_ascii=False, default=str),
            equity_json=json.dumps(equity_list, ensure_ascii=False),
            trades_json=json.dumps(trades, ensure_ascii=False),
            log_text="\n".join(log_lines),
            finished_at=int(time.time()),
        )
        # 溯源：记录本次回测的参数与环境，确保指标可复现
        try:
            from backend.services.provenance import record_provenance

            prov_params = {
                k: v
                for k, v in params.items()
                if k not in ("signal_code", "stock_pool", "period_start", "period_end")
            }
            prov_params["run_id"] = run_id
            await record_provenance(
                kind="backtest",
                entity_id=run_id,
                entity_name=f"回测·{run_id[:8]}",
                params=prov_params,
                metrics={
                    "total_return": metrics.get("total_return"),
                    "sharpe_ratio": metrics.get("sharpe_ratio"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "trade_count": metrics.get("trade_count"),
                },
                source="qube_backtest",
            )
        except Exception:
            logger.debug("回测溯源记录失败（非致命）", exc_info=True)
        return {"backtest_run_id": run_id, "metrics": metrics}
    except Exception as e:
        logger.error(f"回测 {run_id} 失败: {e}")
        log_lines.append(f"[ERROR] {e}")
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT progress_json FROM backtest_runs WHERE id = ?", (run_id,)
            )
            r = await cursor.fetchone()
        finally:
            await db.close()
        prog = json.loads(r["progress_json"] or "{}") if r else {}
        idx = max((prog.get("current") or 1) - 1, 0)
        await _update(
            "backtest_runs",
            run_id,
            status="error",
            error=str(e)[:500],
            progress_json=json.dumps(
                _progress(BACKTEST_STAGES, idx, error=True), ensure_ascii=False
            ),
            log_text="\n".join(log_lines),
            finished_at=int(time.time()),
        )
        raise


def run_row_to_dict(row, with_detail: bool = False) -> dict:
    params = json.loads(row["params_json"] or "{}")
    if not with_detail:
        params.pop("signal_code", None)
    d = {
        "id": row["id"],
        "strategy_id": row["strategy_id"],
        "strategy_name": row["strategy_name"],
        "session_id": row["session_id"],
        "status": row["status"],
        "progress": json.loads(row["progress_json"] or "{}"),
        "params": params,
        "metrics": json.loads(row["metrics_json"] or "{}"),
        "error": row["error"],
        "created_at": row["created_at"],
        "finished_at": row["finished_at"],
    }
    if with_detail:
        d["equity"] = json.loads(row["equity_json"] or "[]")
        d["trades"] = json.loads(row["trades_json"] or "[]")
        d["log"] = row["log_text"] or ""
    return d
