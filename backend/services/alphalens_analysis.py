"""AlphaLens 因子分析 — 复用现成轮子 alphalens-reloaded 计算，前端 ECharts 重画

与自研 factor_research 的分工（用户确认）：
- factor_research：与因子研究页/工作流「因子分析」节点同源的自研 IC/分层/衰减流水线；
- 本模块：调用 alphalens-reloaded（业界标准）产出**行业分组 IC/分层收益**、因子加权
  多空组合收益、分位数换手率、因子秩自相关等 AlphaLens 特有口径，只取其计算结果
  （DataFrame），不使用其 matplotlib 绘图；报告以 JSON 返回，前端用 ECharts 渲染。

输入均为面板 DataFrame（index=交易日, columns=股票代码）：
- factor_data：因子值面板
- return_data：日收益面板（用于合成价格供 alphalens 计算前瞻收益）
- sector_map：{股票代码: 行业名}（可选；无则不做分组分析，自动降级）
"""

from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


def _synth_prices(return_data: pd.DataFrame) -> pd.DataFrame:
    """由日收益面板合成价格序列（(1+r) 累乘）；alphalens 据此算前瞻收益，口径一致"""
    r = return_data.sort_index().fillna(0.0)
    return (1.0 + r).cumprod() * 100.0


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame → [{列: 值}]（NaN 转 None），供 JSON 序列化"""
    return df.replace({np.nan: None}).reset_index().to_dict("records")


def full_alphalens_analysis(
    factor_data: pd.DataFrame,
    return_data: pd.DataFrame,
    periods: Optional[list[int]] = None,
    quantiles: int = 5,
    sector_map: Optional[dict] = None,
) -> dict:
    """AlphaLens 式因子分析报告（JSON），字段供前端 ECharts 渲染

    Returns 结构：
      periods / quantiles / has_group
      ic_summary: [{period, ic_mean, ic_std, ic_ir, risk_adjusted, t_stat, p_value}]
      ic_series: {period: {date: ic}}          # Rank IC 时序（含移动均值由前端算）
      ic_by_group: [{group, period, ic_mean}]   # 行业分组 IC（has_group 时）
      mean_return_by_quantile: [{factor_quantile, period, mean_return}]
      mean_return_by_quantile_group: [{group, factor_quantile, period, mean_return}]
      cumulative_return_by_quantile: {period: {quantile: {date: cum}}}
      factor_weighted_cumulative: {period: {date: cum}}   # 因子加权多空组合累计
      quantile_turnover: {period: {date: turnover}}
      rank_autocorrelation: {period: {date: acf}}
    """
    from alphalens import performance, utils

    periods = periods or [1, 5, 10]
    prices = _synth_prices(return_data)

    # 因子面板 → MultiIndex Series (date, asset)
    factor = factor_data.sort_index().stack()
    factor.index = factor.index.set_names(["date", "asset"])

    groupby = None
    has_group = False
    if sector_map:
        # 仅保留有行业标签的股票，且需覆盖足够标的才做分组
        valid = {k: v for k, v in sector_map.items() if v}
        if valid and len(set(valid.values())) >= 2:
            groupby = valid
            has_group = True

    try:
        fd = utils.get_clean_factor_and_forward_returns(
            factor,
            prices,
            groupby=groupby,
            quantiles=quantiles,
            periods=tuple(periods),
            max_loss=0.5,
        )
    except Exception as e:
        raise ValueError(f"AlphaLens 数据准备失败（因子/收益样本不足或对齐失败）: {e}")

    period_cols = [
        c for c in fd.columns if c not in ("factor", "group", "factor_quantile")
    ]

    # ── IC（Rank IC）时序与汇总 ────────────────────────────────
    ic = performance.factor_information_coefficient(fd)
    ic_summary = []
    ic_series: dict = {}
    for col in period_cols:
        s = ic[col].dropna()
        mean, std = float(s.mean()), float(s.std())
        n = int(s.size)
        t_stat = mean / (std / np.sqrt(n)) if std > 0 and n else 0.0
        # 双尾 p 值
        from scipy import stats as _st

        p_value = (
            float(2 * (1 - _st.t.cdf(abs(t_stat), df=max(n - 1, 1)))) if n > 1 else 1.0
        )
        ic_summary.append(
            {
                "period": col,
                "ic_mean": round(mean, 4),
                "ic_std": round(std, 4),
                "ic_ir": round(mean / std, 4) if std > 0 else 0.0,
                "risk_adjusted": round(mean / std, 4) if std > 0 else 0.0,
                "t_stat": round(float(t_stat), 4),
                "p_value": round(p_value, 4),
                "positive_ratio": round(float((s > 0).mean()), 4) if n else 0.0,
            }
        )
        ic_series[col] = {str(idx.date()): round(float(v), 4) for idx, v in s.items()}

    # ── 行业分组 IC ────────────────────────────────────────────
    ic_by_group = []
    if has_group:
        icg = performance.factor_information_coefficient(fd, by_group=True)
        grouped = icg.groupby(level="group").mean()
        for grp, row in grouped.iterrows():
            for col in period_cols:
                ic_by_group.append(
                    {
                        "group": str(grp),
                        "period": col,
                        "ic_mean": round(float(row[col]), 4),
                    }
                )

    # ── 分层平均收益 ───────────────────────────────────────────
    mrq, _ = performance.mean_return_by_quantile(fd, by_group=False)
    mean_return_by_quantile = []
    for q, row in mrq.iterrows():
        for col in period_cols:
            mean_return_by_quantile.append(
                {
                    "factor_quantile": int(q),
                    "period": col,
                    "mean_return": round(float(row[col]), 6),
                }
            )

    mean_return_by_quantile_group = []
    if has_group:
        mrqg, _ = performance.mean_return_by_quantile(fd, by_group=True)
        # 索引为 (factor_quantile, group)，用列名取值避免位置解包出错
        mrqg_r = mrqg.reset_index()
        for _, row in mrqg_r.iterrows():
            for col in period_cols:
                mean_return_by_quantile_group.append(
                    {
                        "group": str(row["group"]),
                        "factor_quantile": int(row["factor_quantile"]),
                        "period": col,
                        "mean_return": round(float(row[col]), 6),
                    }
                )

    # ── 各分位数累计收益曲线（按日均值后累乘）──────────────────
    mrq_bydate, _ = performance.mean_return_by_quantile(fd, by_date=True)
    cumulative_return_by_quantile: dict = {}
    for col in period_cols:
        by_q: dict = {}
        sub = mrq_bydate[col].unstack("factor_quantile")
        # 前瞻 period 收益近似按持有期折算为日度再累乘，直接对日度均值累乘展示走势
        cum = (1.0 + sub.fillna(0.0)).cumprod() - 1.0
        for q in cum.columns:
            by_q[str(int(q))] = {
                str(idx.date()): round(float(v), 4) for idx, v in cum[q].items()
            }
        cumulative_return_by_quantile[col] = by_q

    # ── 因子加权多空组合累计收益 ───────────────────────────────
    fr = performance.factor_returns(fd)
    factor_weighted_cumulative: dict = {}
    for col in period_cols:
        cum = (1.0 + fr[col].fillna(0.0)).cumprod() - 1.0
        factor_weighted_cumulative[col] = {
            str(idx.date()): round(float(v), 4) for idx, v in cum.items()
        }

    # ── 分位数换手率 + 因子秩自相关 ────────────────────────────
    quantile_turnover: dict = {}
    rank_autocorrelation: dict = {}
    top_q = int(fd["factor_quantile"].max())
    for p in periods:
        try:
            to = performance.quantile_turnover(fd["factor_quantile"], top_q, p).dropna()
            quantile_turnover[f"{p}D"] = {
                str(idx.date()): round(float(v), 4) for idx, v in to.items()
            }
        except Exception:
            pass
        try:
            ac = performance.factor_rank_autocorrelation(fd, p).dropna()
            rank_autocorrelation[f"{p}D"] = {
                str(idx.date()): round(float(v), 4) for idx, v in ac.items()
            }
        except Exception:
            pass

    return {
        "periods": [f"{p}D" for p in periods],
        "quantiles": quantiles,
        "has_group": has_group,
        "ic_summary": ic_summary,
        "ic_series": ic_series,
        "ic_by_group": ic_by_group,
        "mean_return_by_quantile": mean_return_by_quantile,
        "mean_return_by_quantile_group": mean_return_by_quantile_group,
        "cumulative_return_by_quantile": cumulative_return_by_quantile,
        "factor_weighted_cumulative": factor_weighted_cumulative,
        "quantile_turnover": quantile_turnover,
        "rank_autocorrelation": rank_autocorrelation,
    }
