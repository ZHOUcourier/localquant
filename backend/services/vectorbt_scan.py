"""vectorbt 快速参数扫描 — 因子分组组合的参数网格向量化模拟（Beta）

定位：研究阶段的「快扫」工具。用最简假设（日频调仓、等权目标仓位、
固定费率、无涨跌停/停牌成交约束）扫描 分组数 × 调仓周期 参数区域，
回答「参数敏感度 / 大致收益量级」；生产级口径（T+1 批次、停牌冻结、
成本拆分、容量分析）仍以自研回测引擎（backtest_analysis）为准，
两边数字不应直接互比。

引擎：vbt.Portfolio.from_orders(size_type='targetpercent')，
调仓日写入目标权重、非调仓日留 NaN（持仓不动），call_seq='auto'
先卖后买，现金共享为单一组合。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _target_weights(
    factor_df: pd.DataFrame,
    close_idx: pd.DatetimeIndex,
    groups: int,
    rebalance_days: int,
    direction: int = 1,
) -> pd.DataFrame:
    """每个调仓日：因子排序 → 头部 1/groups 等权目标仓位，非调仓日 NaN（持仓）"""
    weights = pd.DataFrame(np.nan, index=close_idx, columns=factor_df.columns)
    dates = factor_df.index
    for i, date in enumerate(dates):
        if i % rebalance_days != 0:
            continue
        row = factor_df.loc[date].dropna()
        if len(row) < groups:
            continue
        if direction < 0:
            row = -row
        n_top = max(1, len(row) // groups)
        top = set(row.nlargest(n_top).index)
        for code in factor_df.columns:
            if code in top:
                weights.loc[date, code] = 1.0 / n_top
            elif code in row.index:
                weights.loc[date, code] = 0.0  # 显式 0 → 调出
            # NaN（因子缺失）保持 NaN → 不主动交易
    return weights


def scan_quantile_portfolios(
    factor_df: pd.DataFrame,
    close_df: pd.DataFrame,
    group_list: list[int] | None = None,
    rebalance_list: list[int] | None = None,
    fee_rate: float = 0.0015,
    direction: int = 1,
    min_stocks: int = 10,
) -> dict:
    """参数网格扫描：group_list × rebalance_list 组合的向量化组合模拟

    Args:
        factor_df: 日频因子面板 (date × code)；direction=1 高值做多，-1 低值做多
        close_df: 日频收盘面板（与因子同构）
        fee_rate: 单边费率（含冲击的粗略值）
        min_stocks: 单调仓日有效因子股票数下限（低于则跳过该日，保护小样本）

    Returns:
        {ok, rows: [{groups, rebalance_days, total_return, annual_return,
        sharpe, max_drawdown, trades}], best: {...}, n_stocks, n_dates,
        assumptions: [...]}
    """
    group_list = group_list or [5, 10, 20]
    rebalance_list = rebalance_list or [1, 5, 10, 20]

    import vectorbt as vbt

    codes = [c for c in factor_df.columns if c in close_df.columns]
    if not codes:
        return {"ok": False, "message": "因子与行情无共同代码"}
    dates = factor_df.index.intersection(close_df.index)
    if len(dates) < 30:
        return {"ok": False, "message": f"重叠日期不足 30 个（当前 {len(dates)}）"}
    fac = factor_df.loc[dates, codes]
    close = close_df.loc[dates, codes]

    rows: list[dict] = []
    for groups in group_list:
        for reb in rebalance_list:
            weights = _target_weights(fac, close.index, groups, reb, direction)
            # 有效股票过少的调仓日整行清 NaN（跳过）
            valid_counts = fac.notna().sum(axis=1)
            for date in dates[::1]:
                if valid_counts.get(date, 0) < min_stocks:
                    weights.loc[date] = np.nan
            pf = vbt.Portfolio.from_orders(
                close,
                size=weights,
                size_type="targetpercent",
                group_by=True,
                cash_sharing=True,
                call_seq="auto",
                fees=fee_rate,
                freq="D",
            )
            ann = float(pf.annualized_return())
            rows.append(
                {
                    "groups": groups,
                    "rebalance_days": reb,
                    "total_return": round(float(pf.total_return()), 6),
                    "annual_return": round(ann, 6),
                    "sharpe": round(float(pf.sharpe_ratio()), 4),
                    "max_drawdown": round(float(pf.max_drawdown()), 6),
                    "trades": int(pf.trades.count()),
                }
            )
    rows.sort(key=lambda r: r["sharpe"], reverse=True)
    return {
        "ok": True,
        "rows": rows,
        "best": rows[0] if rows else None,
        "n_stocks": len(codes),
        "n_dates": len(dates),
        "assumptions": [
            "日频调仓、等权目标仓位、固定单边费率",
            "无 T+1 批次/涨跌停可成交性/停牌冻结约束（与自研引擎口径不同，不直接互比）",
            "factor NaN 的股票在调仓日不主动交易（保留原持仓）",
        ],
    }
