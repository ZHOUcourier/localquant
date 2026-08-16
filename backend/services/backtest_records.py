"""回测记录落库与溯源 — 供所有回测入口统一使用

QUBE 回测、因子池组合回测、/backtest/run 与 /backtest/run-strategy 都应把
参数、指标、净值与（尾部）交易明细写入 backtest_runs + provenance，
否则研究员无法在回测中心复现与比较结果。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from backend.database import get_db

_TRADE_TAIL = 1000


def _progress_done() -> dict:
    return {
        "stage": "done",
        "label": "完成",
        "percent": 100,
        "current": 8,
        "total": 8,
        "stages": [
            {"code": "task_start", "label": "任务开始", "status": "done"},
            {"code": "validation", "label": "参数校验", "status": "done"},
            {"code": "engine_start", "label": "回测引擎启动", "status": "done"},
            {"code": "market_data", "label": "行情加载", "status": "done"},
            {"code": "simulation", "label": "模拟撮合", "status": "done"},
            {"code": "summary", "label": "绩效汇总", "status": "done"},
            {"code": "save", "label": "结果落库", "status": "done"},
            {"code": "complete", "label": "完成", "status": "done"},
        ],
    }


def _equity_list(equity: pd.Series) -> list[dict]:
    return [
        {"ts": str(k.date() if hasattr(k, "date") else k), "equity": float(v)}
        for k, v in equity.items()
    ]


def _trade_tail(
    positions: pd.DataFrame,
    prices: pd.DataFrame,
    initial_capital: float,
    limit: int = _TRADE_TAIL,
) -> list[dict]:
    """由持仓权重变化生成交易明细（最多保留尾部 limit 条）。

    全市场回测的完整交易矩阵可能达到百万级，落库只保存最近 limit 条，
    trade_count 仍是完整统计数。
    """
    if positions.empty:
        return []
    dw = positions.diff().fillna(positions)
    rows, cols = np.nonzero(np.abs(dw.to_numpy(dtype=float)) > 1e-9)
    if len(rows) == 0:
        return []
    tail = slice(-limit, None)
    rows = rows[tail]
    cols = cols[tail]
    out: list[dict] = []
    for r, c in zip(rows, cols):
        ts = positions.index[r]
        code = positions.columns[c]
        w = float(dw.iloc[r, c])
        price = float(prices.iloc[r, c]) if prices.shape[0] > r and prices.shape[1] > c else 0.0
        if price <= 0:
            continue
        out.append(
            {
                "ts": str(ts.date() if hasattr(ts, "date") else ts),
                "symbol": str(code),
                "side": "买入" if w > 0 else "卖出",
                "weight": round(abs(w), 6),
                "price": round(price, 3),
            }
        )
    return out


async def persist_backtest_run(
    *,
    params: dict[str, Any],
    result: dict[str, Any],
    metrics: dict[str, Any],
    strategy_id: str = "",
    strategy_name: str = "",
    session_id: str = "",
    source: str = "direct_api",
    run_id: str = "",
    status: str = "done",
    error: str = "",
) -> str:
    """写入一条回测记录 + provenance，返回 run_id。

    params 必须已包含 signal_code（如适用）；metrics 为最终绩效字典。
    result 至少含 equity_curve / positions / prices / cost_summary / assumptions。
    """
    run_id = run_id or str(uuid.uuid4())
    now = int(time.time())
    equity = result.get("equity_curve")
    positions = result.get("positions")
    prices = result.get("prices", pd.DataFrame())

    equity_json = json.dumps(_equity_list(equity), ensure_ascii=False)
    trades = _trade_tail(
        positions, prices, float(result.get("initial_capital") or 0.0)
    )
    trades_json = json.dumps(trades, ensure_ascii=False)

    metrics_out = dict(metrics)
    if not metrics_out.get("trade_count") and positions is not None and not positions.empty:
        dw = positions.diff().fillna(positions)
        metrics_out["trade_count"] = int((dw.abs() > 1e-9).to_numpy().sum())
    metrics_out["trade_count"] = metrics_out.get("trade_count") or 0
    metrics_out["final_equity"] = metrics_out.get("final_equity") or (
        float(equity.iloc[-1]) if equity is not None and len(equity) else None
    )
    metrics_out["cost_summary"] = result.get("cost_summary", {})
    metrics_out["assumptions"] = result.get("assumptions", [])
    metrics_out["delisting_events"] = result.get("delisting_events", [])
    metrics_out["leverage_summary"] = result.get("leverage_summary", {})
    metrics_out["n_delisting"] = len(metrics_out.get("delisting_events") or [])

    logs = [f"[INFO] 回测 #{run_id[:8]} 完成，来源 {source}"]
    for a in metrics_out.get("assumptions", [])[:20]:
        logs.append(f"[WARN] 假设: {a}")
    if error:
        logs.append(f"[ERROR] {error}")

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO backtest_runs "
            "(id, strategy_id, strategy_name, session_id, status, progress_json, "
            "params_json, metrics_json, equity_json, trades_json, log_text, error, "
            "created_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                strategy_id,
                strategy_name,
                session_id,
                status,
                json.dumps(_progress_done() if status == "done" else {}, ensure_ascii=False),
                json.dumps(params, ensure_ascii=False, default=str),
                json.dumps(metrics_out, ensure_ascii=False, default=str),
                equity_json,
                trades_json,
                "\n".join(logs),
                error,
                now,
                now,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    # 自动写入实验记录：回测完成后可直接在实验页对比/检索
    try:
        from backend.models.experiment import ExperimentCreate
        from backend.services.experiment_service import experiment_service

        await experiment_service.create(
            ExperimentCreate(
                source="backtest",
                source_id=run_id,
                name=strategy_name or f"回测·{run_id[:8]}",
                note=f"由 {source} 自动创建",
                tags=["backtest", "auto"],
                params={
                    k: v
                    for k, v in params.items()
                    if k not in ("signal_code", "stock_pool")
                },
                metrics={
                    k: v
                    for k, v in metrics_out.items()
                    if isinstance(v, (int, float)) and k
                    not in ("assumptions", "delisting_events", "cost_summary", "leverage_summary")
                },
            )
        )
    except Exception:
        logger.debug("自动创建实验记录失败（非致命）", exc_info=True)

    try:
        from backend.services.provenance import record_provenance

        await record_provenance(
            kind="backtest",
            entity_id=run_id,
            entity_name=strategy_name or f"回测·{run_id[:8]}",
            params={
                k: v
                for k, v in params.items()
                if k
                not in (
                    "signal_code",
                    "stock_pool",
                    "period_start",
                    "period_end",
                    "start_date",
                    "end_date",
                )
            },
            metrics={
                "total_return": metrics_out.get("total_return"),
                "annual_return": metrics_out.get("annual_return"),
                "sharpe_ratio": metrics_out.get("sharpe_ratio"),
                "max_drawdown": metrics_out.get("max_drawdown"),
                "trade_count": metrics_out.get("trade_count"),
            },
            notes=f"回测完成（{source}）",
            source=source,
        )
    except Exception:
        pass
    return run_id
