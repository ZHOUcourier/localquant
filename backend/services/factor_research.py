"""因子研究服务 — 提供 IC 分析、分层收益、中性化、相关性等功能"""

import re
import time
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from backend.database import get_db

# ── 公式提取与 LaTeX 转换 ─────────────────────────────────────

_FORMULA_MARKERS = ["公式是：", "计算公式：", "公式：", "公式为："]

# 函数名 → LaTeX 算子名（小写归一）
_LATEX_FUNCS = {
    "rank": "rank",
    "std": "std",
    "stddev": "std",
    "corr": "corr",
    "correlation": "corr",
    "delta": "\\Delta",
    "delay": "delay",
    "sum": "sum",
    "mean": "mean",
    "sma": "sma",
    "wma": "wma",
    "ema": "ema",
    "ts_min": "ts\\_min",
    "ts_max": "ts\\_max",
    "ts_rank": "ts\\_rank",
    "ts_argmax": "ts\\_argmax",
    "ts_argmin": "ts\\_argmin",
    "min": "min",
    "max": "max",
    "abs": "abs",
    "log": "log",
    "sign": "sign",
    "signedpower": "signedpower",
    "scale": "scale",
    "decay_linear": "decay\\_linear",
    "decaylinear": "decay\\_linear",
    "count": "count",
    "covariance": "cov",
    "cov": "cov",
    "prod": "prod",
    "regbeta": "regbeta",
    "regresi": "regresi",
    "sequence": "seq",
    "highday": "highday",
    "lowday": "lowday",
    "sumif": "sumif",
    "filter": "filter",
    "adv20": "adv20",
}


def extract_formula(description: Optional[str]) -> str:
    """从因子描述中提取公式文本"""
    if not description:
        return ""
    for marker in _FORMULA_MARKERS:
        if marker in description:
            return description.split(marker, 1)[1].strip()
    return ""


def formula_to_latex(formula: str) -> str:
    """将因子公式字符串转为 LaTeX 表达式（供前端 KaTeX 渲染）

    策略：逐 token 映射 —— 函数名转 \\operatorname，变量转 \\text，
    乘号转 \\cdot，保留括号结构；不做完整语法解析，保证鲁棒。
    """
    if not formula:
        return ""
    expr = formula.replace("**", "^")
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+\.?\d*|[^\sA-Za-z0-9_]", expr)
    out: list[str] = []
    for i, tok in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if re.match(r"[A-Za-z_]", tok):
            low = tok.lower()
            if nxt == "(":
                op_name = _LATEX_FUNCS.get(low, low.replace("_", "\\_"))
                if op_name.startswith("\\\\") or op_name.startswith("\\"):
                    out.append(op_name)
                else:
                    out.append(f"\\operatorname{{{op_name}}}")
            else:
                out.append(f"\\text{{{tok.lower().replace('_', chr(92) + '_')}}}")
        elif tok == "*":
            out.append("\\cdot")
        elif tok == "?":
            out.append("\\;?\\;")
        elif tok == ":":
            out.append("\\;:\\;")
        elif tok == "<" and nxt == "=":
            out.append("\\le")
        elif tok == ">" and nxt == "=":
            out.append("\\ge")
        elif tok == "=" and out and out[-1] in ("\\le", "\\ge"):
            continue
        elif tok == "&":
            out.append("\\land")
        elif tok == "|":
            out.append("\\lor")
        else:
            out.append(tok)
    # 去重连续逻辑符（&& / || 各产生两个 token）
    cleaned: list[str] = []
    for tok in out:
        if tok in ("\\land", "\\lor") and cleaned and cleaned[-1] == tok:
            continue
        cleaned.append(tok)
    return " ".join(cleaned)


def formula_to_code(formula: str, factor_code: str = "factor") -> str:
    """将公式包装为可直接运行的代码片段

    因子构建「代码/公式」节点的求值环境已注入全部量化算子（RANK/DELAY/CORR...）
    与基础字段（open/high/low/close/volume/amount/vwap），因此可直接赋值。
    """
    if not formula:
        return ""
    return (
        f"# {factor_code} — 基于量价面板数据计算\n"
        f"# 可用字段: open / high / low / close / volume / amount / vwap\n"
        f"# 可用算子: RANK/DELAY/DELTA/CORR/STD/TS_RANK/DECAYLINEAR 等（大小写均可）\n"
        f"factor_data = {formula}\n"
    )


# 因子类型判定：公式型 / 数据字段型 / 参数化指标型
_DATA_FIELD_CATEGORIES = {"估值因子", "财务指标衍生因子", "基础因子"}
_INDICATOR_CATEGORIES = {"均线类因子", "技术类因子", "超买超卖因子", "量能指标因子"}


def classify_factor(category_name, formula: str) -> str:
    """返回因子类型：'formula'（公式型）/ 'data_field'（直接调用底层字段）/ 'indicator'（参数化指标）"""
    if formula:
        return "formula"
    if category_name in _DATA_FIELD_CATEGORIES:
        return "data_field"
    if category_name in _INDICATOR_CATEGORIES:
        return "indicator"
    return "data_field"


class FactorResearchService:
    """因子研究服务"""

    def ic_analysis(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        periods: list[int] = None,
    ) -> dict:
        """IC 分析

        Args:
            factor_data: 因子值 DataFrame (index=date, columns=stocks)
            return_data: 收益率 DataFrame (index=date, columns=stocks)，
                r[T] 为 T-1→T 日收益（close.pct_change 口径）
            periods: 分析周期列表

        Returns:
            IC 时序、IC 均值、IC_IR、RankIC 等

        对齐约定：T 日因子 vs T→T+p 前向累计收益（取 r[T+1..T+p] 累乘），
        p=1 时即次日收益，无前视。
        """
        periods = periods or [1, 5, 10, 20]
        results = {}

        for period in periods:
            ic_series = []
            rank_ic_series = []
            dates = factor_data.index

            for i in range(len(dates) - period):
                date = dates[i]

                factor_values = factor_data.loc[date].dropna()
                # T→T+p 前向累计收益：r[t] 为 t-1→t，故取 (T, T+p] 区间累乘
                fwd_rows = return_data.reindex(dates[i + 1 : i + period + 1])
                future_returns = ((1.0 + fwd_rows).prod(min_count=1) - 1.0).dropna()

                common = factor_values.index.intersection(future_returns.index)
                if len(common) < 10:
                    continue

                f = factor_values[common]
                r = future_returns[common]

                ic = f.corr(r)
                ic_series.append({"date": str(date), "ic": ic})

                rank_ic = f.rank().corr(r.rank())
                rank_ic_series.append({"date": str(date), "rank_ic": rank_ic})

            ic_values = [
                x["ic"]
                for x in ic_series
                if x["ic"] is not None and not np.isnan(x["ic"])
            ]
            rank_ic_values = [
                x["rank_ic"]
                for x in rank_ic_series
                if x["rank_ic"] is not None and not np.isnan(x["rank_ic"])
            ]

            ic_arr = np.array(ic_values) if ic_values else np.array([])
            ic_mean = float(ic_arr.mean()) if ic_arr.size else 0.0
            ic_std = float(ic_arr.std()) if ic_arr.size else 0.0
            # t 值 = IC均值 / (IC标准差 / sqrt(N))（AlphaLens 同口径）
            ic_tstat = (
                ic_mean / (ic_std / np.sqrt(ic_arr.size))
                if ic_std > 0 and ic_arr.size
                else 0.0
            )

            results[f"period_{period}"] = {
                "ic_series": ic_series,
                "rank_ic_series": rank_ic_series,
                "ic_mean": ic_mean,
                "ic_std": ic_std,
                "ic_ir": float(ic_mean / ic_std) if ic_std > 0 else 0,
                "ic_tstat": float(ic_tstat),
                "ic_skew": float(pd.Series(ic_arr).skew()) if ic_arr.size > 2 else 0.0,
                "ic_kurtosis": float(pd.Series(ic_arr).kurtosis())
                if ic_arr.size > 3
                else 0.0,
                "rank_ic_mean": float(np.mean(rank_ic_values)) if rank_ic_values else 0,
                "rank_ic_ir": float(np.mean(rank_ic_values) / np.std(rank_ic_values))
                if rank_ic_values and np.std(rank_ic_values) > 0
                else 0,
                "ic_positive_ratio": float(
                    sum(1 for x in ic_values if x > 0) / len(ic_values)
                )
                if ic_values
                else 0,
            }

        return results

    def quantile_analysis(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        n_groups: int = 5,
    ) -> dict:
        """分层收益分析

        对齐约定：T 日因子分组 → T+1 日收益计入该组（r[T+1] 为 T→T+1 收益），
        避免用因子形成时已实现的当日收益（前视）。
        """
        group_returns = {f"group_{i + 1}": [] for i in range(n_groups)}
        dates = factor_data.index

        for i in range(len(dates) - 1):
            date, nxt = dates[i], dates[i + 1]
            factor_values = factor_data.loc[date].dropna()
            returns = (
                return_data.loc[nxt].dropna()
                if nxt in return_data.index
                else pd.Series(dtype=float)
            )

            common = factor_values.index.intersection(returns.index)
            if len(common) < n_groups * 2:
                continue

            f = factor_values[common]
            r = returns[common]

            groups = pd.qcut(f, q=n_groups, labels=False, duplicates="drop")
            for g in range(n_groups):
                mask = groups == g
                if mask.sum() > 0:
                    group_returns[f"group_{g + 1}"].append(
                        {
                            "date": str(nxt),
                            "return": float(r[mask].mean()),
                            "count": int(mask.sum()),
                        }
                    )

        cumulative = {}
        cumulative_series = {}
        for key, values in group_returns.items():
            if values:
                rets = [v["return"] for v in values]
                cumulative[key] = float(np.prod([1 + r for r in rets]) - 1)
                # 逐日累计收益曲线（AlphaLens 风格分层净值）
                nav = 1.0
                series = []
                for v in values:
                    nav *= 1 + v["return"]
                    series.append({"date": v["date"], "cum_return": float(nav - 1)})
                cumulative_series[key] = series

        # 多空价差曲线（最高组 - 最低组）
        long_short_series = []
        top_key, bottom_key = f"group_{n_groups}", "group_1"
        top = {v["date"]: v["return"] for v in group_returns.get(top_key, [])}
        bottom = {v["date"]: v["return"] for v in group_returns.get(bottom_key, [])}
        nav = 1.0
        for date in sorted(set(top) & set(bottom)):
            spread = top[date] - bottom[date]
            nav *= 1 + spread
            long_short_series.append(
                {"date": date, "spread": float(spread), "cum_return": float(nav - 1)}
            )

        # 各分组平均单期收益（AlphaLens 的 mean return by quantile）
        mean_return_by_group = {}
        for key, values in group_returns.items():
            label = key.replace("group_", "")
            rets = [v["return"] for v in values]
            mean_return_by_group[label] = float(np.mean(rets)) if rets else 0.0

        return {
            "group_returns": group_returns,
            "cumulative_returns": cumulative,
            "cumulative_series": cumulative_series,
            "mean_return_by_group": mean_return_by_group,
            "long_short_series": long_short_series,
            "n_groups": n_groups,
            "monotonicity": self._check_monotonicity(cumulative),
        }

    def _check_monotonicity(self, cumulative: dict) -> float:
        """检查分层收益单调性"""
        values = list(cumulative.values())
        if len(values) < 2:
            return 0
        increases = sum(1 for i in range(len(values) - 1) if values[i] >= values[i + 1])
        return increases / (len(values) - 1)

    def full_factor_analysis(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        periods: list[int] = None,
        n_groups: int = 5,
        method: str = "rank_ic",
    ) -> dict:
        """完整单因子分析报告（对齐官网因子分析节点）

        产出：数据卡指标、分组绩效表（含多空组合）、分组/超额累计收益曲线、
        IC 与 Rank_IC 的时序/累计/分布/自相关/衰减、最新一期因子值排名。
        为「因子分析」节点与因子研究页共用入口，全部基于 QMT 行情面板做截面计算。
        """
        periods = periods or [1, 5, 10, 20]
        ic = self.ic_analysis(factor_data, return_data, periods)

        # 各周期 IC 汇总表
        use_rank = method == "rank_ic"
        ic_summary: list[dict] = []
        for p in periods:
            item = ic.get(f"period_{p}")
            if not item:
                continue
            ic_summary.append(
                {
                    "period": p,
                    "ic_mean": item.get("rank_ic_mean" if use_rank else "ic_mean", 0.0),
                    "ic_std": item.get("ic_std", 0.0),
                    "ic_ir": item.get("rank_ic_ir" if use_rank else "ic_ir", 0.0),
                    "ic_tstat": item.get("ic_tstat", 0.0),
                    "positive_ratio": item.get("ic_positive_ratio", 0.0),
                }
            )

        # 首周期 IC / RankIC 逐日序列（用于分布/自相关/时序/累计）
        base = ic.get(f"period_{periods[0]}", {})
        ic_ser = pd.Series(
            {
                r["date"][:10]: r["ic"]
                for r in base.get("ic_series", [])
                if r.get("ic") is not None
            }
        ).sort_index()
        ric_ser = pd.Series(
            {
                r["date"][:10]: r["rank_ic"]
                for r in base.get("rank_ic_series", [])
                if r.get("rank_ic") is not None
            }
        ).sort_index()

        # 分组日收益 + 基准（全体等权）
        gd, bench = self._group_daily_returns(factor_data, return_data, n_groups)
        labels = sorted(gd.keys(), key=lambda x: int(x[1:]))
        tov = self._turnover_by_group(factor_data, n_groups)

        # 多空组合（最高组 - 最低组）
        ls = pd.Series(dtype=float)
        if len(labels) >= 2:
            idx = gd[labels[-1]].index.intersection(gd[labels[0]].index)
            ls = gd[labels[-1]].reindex(idx) - gd[labels[0]].reindex(idx)

        # 分组绩效表（各组 + 多空组合）
        group_perf: list[dict] = []
        for lab in labels:
            m = self._perf(gd[lab], bench)
            m.update({"group": f"分组{lab[1:]}", "turnoverRate": tov.get(lab, 0.0)})
            group_perf.append(m)
        if not ls.empty:
            m = self._perf(ls, None)
            m.update({"group": "多空组合", "turnoverRate": 0.0})
            group_perf.append(m)

        def _cum(s: pd.Series) -> dict:
            s = s.dropna()
            return {str(k): float(v) for k, v in ((1 + s).cumprod() - 1).items()}

        group_cumulative = {f"分组{lab[1:]}": _cum(gd[lab]) for lab in labels}
        group_excess_cumulative = {
            f"分组{lab[1:]}": _cum(gd[lab] - bench.reindex(gd[lab].index).fillna(0.0))
            for lab in labels
        }
        long_short_cumulative = _cum(ls) if not ls.empty else {}

        # IC / RankIC 报告（时序/累计/分布/自相关）
        ic_decay, rank_ic_decay = self._ic_decay_both(
            factor_data, return_data, min(20, max(len(factor_data.index) // 2, 1))
        )
        ic_report = self._ic_report(ic_ser, ic_decay)
        rank_ic_report = self._ic_report(ric_ser, rank_ic_decay)

        # 最新一期因子值排名
        latest: list[dict] = []
        if not factor_data.empty:
            last = factor_data.iloc[-1].dropna().sort_values(ascending=False)
            dt = str(factor_data.index[-1])[:10]
            latest = [
                {"date": dt, "symbol": str(s), "factor_value": float(v)}
                for s, v in last.head(50).items()
            ]

        # 数据卡指标（对齐官网：因子收益/年化/夏普/回撤 取最高组）
        top_perf = self._perf(gd[labels[-1]], bench) if labels else {}
        top_total = float((1 + gd[labels[-1]].dropna()).prod() - 1) if labels else 0.0
        ic_mean = ic_report["mean"]
        ic_std = float(ic_ser.std()) if len(ic_ser) > 1 else 0.0
        n_ic = len(ic_ser)
        t_stat = ic_mean / (ic_std / np.sqrt(n_ic)) if ic_std and n_ic else 0.0
        # 分组年化收益单调性
        ann = [
            p["annualizedReturn"] for p in group_perf if p["group"].startswith("分组")
        ]
        if len(ann) >= 2:
            inc = sum(1 for i in range(len(ann) - 1) if ann[i + 1] >= ann[i]) / (
                len(ann) - 1
            )
            monotonicity = max(inc, 1 - inc)
        else:
            monotonicity = 0.0
        summary = {
            "factor_return": top_total,
            "annual_return": top_perf.get("annualizedReturn", 0.0),
            "sharpe_ratio": top_perf.get("sharpeRatio", 0.0),
            "max_drawdown": top_perf.get("maxDrawdown", 0.0),
            "ic_mean": ic_mean,
            "rank_ic": rank_ic_report["mean"],
            "ic_std": ic_std,
            "ic_ir": ic_report["ir"],
            "ir": float(ic_report["ir"] * np.sqrt(252)) if ic_report["ir"] else 0.0,
            "p_ic_lt_neg": float((ic_ser < -0.02).mean()) if n_ic else 0.0,
            "p_ic_gt_pos": float((ic_ser > 0.02).mean()) if n_ic else 0.0,
            "t_stat": float(t_stat),
            "p_value": self._t_pvalue(t_stat),
            "monotonicity": float(monotonicity),
        }

        return {
            "summary": summary,
            "ic_summary": ic_summary,
            "group_perf": group_perf,
            "group_cumulative": group_cumulative,
            "group_excess_cumulative": group_excess_cumulative,
            "long_short_cumulative": long_short_cumulative,
            "mean_return_by_group": {lab[1:]: float(gd[lab].mean()) for lab in labels},
            "ic": ic_report,
            "rank_ic": rank_ic_report,
            "latest": latest,
            "periods": periods,
            "n_groups": n_groups,
        }

    # ── full_factor_analysis 辅助方法 ──────────────────────────

    def _group_daily_returns(
        self, factor_data: pd.DataFrame, return_data: pd.DataFrame, n_groups: int
    ) -> tuple[dict, pd.Series]:
        """按截面分位数分组，返回 {组标签: 日收益Series} 与 基准(全体等权)日收益

        对齐约定：T 日因子分组 → T+1 日收益（避免前视），收益记在 T+1 日。
        """
        group_daily: dict[str, dict] = {f"G{i + 1}": {} for i in range(n_groups)}
        bench: dict = {}
        dates = factor_data.index
        for i in range(len(dates) - 1):
            date, nxt = dates[i], dates[i + 1]
            fv = factor_data.loc[date].dropna()
            if nxt not in return_data.index:
                continue
            rv = return_data.loc[nxt].dropna()
            common = fv.index.intersection(rv.index)
            if len(common) < n_groups * 2:
                continue
            f = fv[common]
            r = rv[common]
            bench[nxt] = float(r.mean())
            try:
                groups = pd.qcut(f, q=n_groups, labels=False, duplicates="drop")
            except Exception:
                continue
            for g in range(n_groups):
                mask = groups == g
                if mask.sum() > 0:
                    group_daily[f"G{g + 1}"][nxt] = float(r[mask].mean())
        gd = {k: pd.Series(v).sort_index() for k, v in group_daily.items() if v}
        return gd, pd.Series(bench).sort_index()

    def _perf(self, daily: pd.Series, bench: pd.Series | None = None) -> dict:
        """单条日收益序列的绩效指标（含相对基准）"""
        daily = daily.dropna()
        if daily.empty:
            return {}
        n = len(daily)
        ann_factor = 252 / n
        total = float((1 + daily).prod() - 1)
        annual = float((1 + total) ** ann_factor - 1) if total > -1 else -1.0
        vol = float(daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
        sharpe = (
            float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
        )
        cum = (1 + daily).cumprod()
        mdd = float((cum / cum.cummax() - 1).min())
        mwr = self._monthly_win_rate(daily)
        res = {
            "annualizedReturn": annual,
            "maxDrawdown": mdd,
            "annualizedVolatility": vol,
            "sharpeRatio": sharpe,
            "monthlyWinRate": mwr,
        }
        if bench is not None:
            b = bench.reindex(daily.index).fillna(0.0)
            active = daily - b
            b_total = float((1 + b).prod() - 1)
            b_annual = float((1 + b_total) ** ann_factor - 1) if b_total > -1 else -1.0
            a_cum = (1 + active).cumprod()
            res.update(
                {
                    "excessAnnualized": annual - b_annual,
                    "excessMaxDrawdown": float((a_cum / a_cum.cummax() - 1).min()),
                    "excessAnnualizedVolatility": float(active.std() * np.sqrt(252))
                    if active.std() > 0
                    else 0.0,
                    "excessMonthlyWinRate": self._monthly_win_rate(active),
                    "trackingError": float(active.std() * np.sqrt(252))
                    if active.std() > 0
                    else 0.0,
                    "informationRatio": float(
                        active.mean() / active.std() * np.sqrt(252)
                    )
                    if active.std() > 0
                    else 0.0,
                }
            )
        return res

    def _monthly_win_rate(self, daily: pd.Series) -> float:
        """月度胜率"""
        daily = daily.dropna()
        if daily.empty or not hasattr(daily.index, "year"):
            return 0.0
        monthly = daily.groupby([daily.index.year, daily.index.month]).apply(
            lambda g: (1 + g).prod() - 1
        )
        return float((monthly > 0).mean()) if len(monthly) else 0.0

    def _turnover_by_group(self, factor_data: pd.DataFrame, n_groups: int) -> dict:
        """各分组换手率（相邻期成分股变动比例均值）"""
        prev: dict = {g: None for g in range(n_groups)}
        acc: dict = {g: [] for g in range(n_groups)}
        for date in factor_data.index:
            fv = factor_data.loc[date].dropna()
            if len(fv) < n_groups * 2:
                continue
            try:
                groups = pd.qcut(fv, q=n_groups, labels=False, duplicates="drop")
            except Exception:
                continue
            for g in range(n_groups):
                cur = set(fv.index[groups == g])
                if prev[g]:
                    acc[g].append(len(cur ^ prev[g]) / (2 * len(prev[g])))
                prev[g] = cur
        return {
            f"G{g + 1}": float(np.mean(acc[g])) if acc[g] else 0.0
            for g in range(n_groups)
        }

    def _ic_decay_both(
        self, factor_data: pd.DataFrame, return_data: pd.DataFrame, max_period: int
    ) -> tuple[list, list]:
        """同时计算 IC(pearson) 与 RankIC(spearman) 随持有期的衰减序列"""
        ic_decay, rank_decay = [], []
        dates = factor_data.index
        for period in range(1, max_period + 1):
            ics, rics = [], []
            for i in range(len(dates) - period):
                f = factor_data.loc[dates[i]].dropna()
                r = (
                    return_data.loc[dates[i + period]].dropna()
                    if dates[i + period] in return_data.index
                    else pd.Series(dtype=float)
                )
                common = f.index.intersection(r.index)
                if len(common) > 10:
                    fc, rc = f[common], r[common]
                    ics.append(fc.corr(rc))
                    rics.append(fc.rank().corr(rc.rank()))
            ic_decay.append(
                {"period": period, "ic": float(np.nanmean(ics)) if ics else 0.0}
            )
            rank_decay.append(
                {"period": period, "ic": float(np.nanmean(rics)) if rics else 0.0}
            )
        return ic_decay, rank_decay

    def _ic_report(self, series: pd.Series, decay: list) -> dict:
        """IC/RankIC 完整报告：时序/累计/分布(含偏峰度)/自相关/衰减/均值/IR"""
        s = series.dropna()
        to_map = lambda x: {str(k): float(v) for k, v in x.items()}

        def _hist_range(vals: pd.Series) -> tuple[float, float] | None:
            """当序列近乎恒定（如完美因子 IC≡1）时给直方图一个非零区间，避免报错"""
            lo, hi = float(vals.min()), float(vals.max())
            if hi - lo < 1e-9:
                return lo - 0.5, hi + 0.5
            return None

        if s.empty:
            return {
                "series": {},
                "cumulative": {},
                "distribution": {"centers": [], "counts": [], "skew": 0.0, "kurt": 0.0},
                "autocorr": [],
                "decay": decay,
                "mean": 0.0,
                "ir": 0.0,
            }
        counts, edges = np.histogram(
            s.values, bins=min(30, max(len(s) // 2, 5)), range=_hist_range(s)
        )
        centers = [
            round(float((edges[i] + edges[i + 1]) / 2), 4) for i in range(len(counts))
        ]
        autocorr = [
            {"lag": lag, "acf": float(s.autocorr(lag)) if len(s) > lag else 0.0}
            for lag in range(1, min(21, len(s)))
        ]
        mean = float(s.mean())
        std = float(s.std())
        return {
            "series": to_map(s),
            "cumulative": to_map(s.cumsum()),
            "distribution": {
                "centers": centers,
                "counts": [int(c) for c in counts],
                "skew": float(s.skew()),
                "kurt": float(s.kurt()),
            },
            "autocorr": autocorr,
            "decay": decay,
            "mean": mean,
            "ir": mean / std if std else 0.0,
        }

    def _t_pvalue(self, t_stat: float) -> float:
        """由 t 统计量求双尾 p 值（正态近似，无需 scipy）"""
        import math

        return float(2 * (1 - 0.5 * (1 + math.erf(abs(t_stat) / math.sqrt(2)))))

    def turnover_analysis(self, factor_data: pd.DataFrame) -> dict:
        """因子换手率分析"""
        dates = factor_data.index
        turnovers = []

        for i in range(1, len(dates)):
            prev = factor_data.loc[dates[i - 1]].dropna()
            curr = factor_data.loc[dates[i]].dropna()
            common = prev.index.intersection(curr.index)
            if len(common) < 10:
                continue

            prev_rank = prev[common].rank(pct=True)
            curr_rank = curr[common].rank(pct=True)
            turnover = float((curr_rank - prev_rank).abs().mean())
            turnovers.append({"date": str(dates[i]), "turnover": turnover})

        return {
            "turnover_series": turnovers,
            "avg_turnover": float(np.mean([t["turnover"] for t in turnovers]))
            if turnovers
            else 0,
        }

    def neutralize(
        self,
        factor_data: pd.DataFrame,
        industry_data: pd.DataFrame,
        market_cap_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """因子中性化（对市值和行业做回归取残差）"""
        neutralized = factor_data.copy()
        dates = factor_data.index

        for date in dates:
            if date not in industry_data.index or date not in market_cap_data.index:
                continue

            factor_values = factor_data.loc[date].dropna()
            industry = industry_data.loc[date]
            market_cap = market_cap_data.loc[date]

            common = factor_values.index.intersection(
                industry.dropna().index
            ).intersection(market_cap.dropna().index)
            if len(common) < 30:
                continue

            y = factor_values[common].values
            ind = industry[common]
            dummies = pd.get_dummies(ind).values.astype(float)
            log_cap = np.log(market_cap[common].values).reshape(-1, 1)

            X = np.hstack([dummies, log_cap])
            X = np.hstack([np.ones((len(X), 1)), X])

            try:
                beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
                residual = y - X @ beta
                neutralized.loc[date, common] = residual
            except Exception:
                pass

        return neutralized

    def factor_correlation(self, factors: dict[str, pd.DataFrame]) -> dict:
        """多因子相关性矩阵"""
        factor_names = list(factors.keys())
        n = len(factor_names)
        corr_matrix = pd.DataFrame(np.eye(n), index=factor_names, columns=factor_names)

        for i in range(n):
            for j in range(i + 1, n):
                f1 = factors[factor_names[i]]
                f2 = factors[factor_names[j]]
                common_dates = f1.index.intersection(f2.index)

                cors = []
                for date in common_dates:
                    v1 = f1.loc[date].dropna()
                    v2 = f2.loc[date].dropna()
                    common = v1.index.intersection(v2.index)
                    if len(common) > 10:
                        cors.append(v1[common].corr(v2[common]))

                mean_corr = float(np.mean(cors)) if cors else 0
                corr_matrix.iloc[i, j] = mean_corr
                corr_matrix.iloc[j, i] = mean_corr

        return {
            "matrix": corr_matrix.to_dict(),
            "factor_names": factor_names,
        }

    def factor_decay(
        self, factor_data: pd.DataFrame, return_data: pd.DataFrame, max_period: int = 30
    ) -> dict:
        """因子衰减分析"""
        decay = []
        for period in range(1, max_period + 1):
            ic_values = []
            dates = factor_data.index
            for i in range(len(dates) - period):
                f = factor_data.loc[dates[i]].dropna()
                r = return_data.loc[dates[i + period]].dropna()
                common = f.index.intersection(r.index)
                if len(common) > 10:
                    ic_values.append(f[common].corr(r[common]))

            avg_ic = float(np.mean(ic_values)) if ic_values else 0
            decay.append({"period": period, "ic": avg_ic})

        return {"decay_series": decay}

    def multi_factor_combine(
        self,
        factors: dict[str, pd.DataFrame],
        weights: dict[str, float] = None,
        method: str = "equal",
        return_data: pd.DataFrame = None,
        ic_window: int = 120,
    ) -> pd.DataFrame:
        """多因子合成

        method:
          - equal: 等权
          - ic_weighted: 按各因子滚动窗口 RankIC 均值加权（绝对值归一为权重，
            符号对齐方向）；需传入 return_data，否则报错而非静默退化等权。
        显式传入 weights 时优先使用 weights。
        """
        factor_names = list(factors.keys())
        if not factor_names:
            raise ValueError("多因子合成：未提供任何因子")

        if weights is None:
            if method == "ic_weighted":
                weights = self._ic_weights(factors, return_data, ic_window)
            else:
                weights = {name: 1.0 / len(factor_names) for name in factor_names}

        standardized = {}
        for name, df in factors.items():
            std = df.std(axis=1).replace(0, np.nan)
            standardized[name] = df.div(std, axis=0) * weights.get(name, 0.0)

        combined = sum(standardized.values())
        return combined

    def _ic_weights(
        self,
        factors: dict[str, pd.DataFrame],
        return_data: pd.DataFrame,
        ic_window: int,
    ) -> dict[str, float]:
        """按各因子近 ic_window 期 RankIC 均值计算权重：|IC| 归一、符号对齐方向"""
        if return_data is None or return_data.empty:
            raise ValueError(
                "ic_weighted 合成需要 return_data（收益面板） — "
                "请连线上游因子构建节点的 return_data，或改用等权合成"
            )
        ics: dict[str, float] = {}
        for name, fac in factors.items():
            dates = fac.index
            # 仅取窗口内最近的截面对，T 日因子 vs T+1 日收益（无前视）
            vals: list[float] = []
            recent = dates[-(ic_window + 1) :] if len(dates) > ic_window else dates
            for i in range(len(recent) - 1):
                f = fac.loc[recent[i]].dropna()
                nxt = recent[i + 1]
                if nxt not in return_data.index:
                    continue
                r = return_data.loc[nxt].dropna()
                common = f.index.intersection(r.index)
                if len(common) > 10:
                    vals.append(f[common].rank().corr(r[common].rank()))
            ics[name] = float(np.nanmean(vals)) if vals else 0.0

        total = sum(abs(v) for v in ics.values())
        if total < 1e-12:
            # 全部因子 IC 近 0，回退等权（不再是静默退化：这是无信息的合理默认）
            n = len(factors)
            return {name: 1.0 / n for name in factors}
        # 权重 = |IC|/Σ|IC|，符号对齐 IC 方向
        return {
            name: (abs(v) / total) * (1.0 if v >= 0 else -1.0)
            for name, v in ics.items()
        }

    # ── 预置因子相关方法 ─────────────────────────────────────────────

    async def list_preset_factors(
        self,
        page: int = 1,
        page_size: int = 30,
        category_code: Optional[str] = None,
        sort_field: Optional[str] = None,
        sort_order: str = "desc",
        search: Optional[str] = None,
    ) -> dict:
        """分页查询预置因子列表"""
        db = await get_db()
        try:
            where_clauses = []
            params = []

            if category_code:
                where_clauses.append("category_code = ?")
                params.append(category_code)

            if search:
                where_clauses.append("(factor_name LIKE ? OR description LIKE ?)")
                params.extend([f"%{search}%", f"%{search}%"])

            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            # 排序
            allowed_sort = {
                "rank_ic",
                "ic_mean",
                "ic_ir",
                "annualized_return",
                "factor_name",
                "created_at",
            }
            if sort_field and sort_field in allowed_sort:
                order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"
                order_sql = f" ORDER BY {sort_field} {order_dir}"
            else:
                order_sql = " ORDER BY id DESC"

            # 总数
            count_sql = f"SELECT COUNT(*) FROM preset_factors{where_sql}"
            cursor = await db.execute(count_sql, params)
            total = (await cursor.fetchone())[0]

            # 分页数据
            offset = (page - 1) * page_size
            data_sql = (
                f"SELECT * FROM preset_factors{where_sql}{order_sql} LIMIT ? OFFSET ?"
            )
            cursor = await db.execute(data_sql, params + [page_size, offset])
            rows = await cursor.fetchall()
            items = [dict(row) for row in rows]

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        finally:
            await db.close()

    async def get_preset_factor_categories(self) -> list[dict]:
        """获取所有预置因子分类"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM preset_factor_categories ORDER BY id"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await db.close()

    async def get_preset_factor_detail(self, factor_id: int) -> Optional[dict]:
        """获取单个预置因子详情（附公式文本/LaTeX/代码三种形式）"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM preset_factors WHERE id = ?", (factor_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            factor = dict(row)
            formula = extract_formula(factor.get("description"))
            factor["formula"] = formula
            factor["formula_latex"] = formula_to_latex(formula)
            factor["formula_code"] = formula_to_code(
                formula, factor.get("factor_code", "factor")
            )
            factor["factor_type"] = classify_factor(
                factor.get("category_name"), formula
            )
            return factor
        finally:
            await db.close()

    async def _ensure_history_table(self, db) -> None:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS preset_factor_ic_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id INTEGER NOT NULL,
                ic_mean REAL, rank_ic REAL, ic_ir REAL, ic_std REAL,
                annualized_return REAL, maximum_drawdown REAL,
                sharpe_ratio REAL, turnover_rate REAL,
                data_date TEXT,
                snapshot_at INTEGER
            )"""
        )

    async def get_factor_ic_history(self, factor_id: int) -> list[dict]:
        """因子 IC 指标的历史快照列表（每次重算前自动留存）"""
        db = await get_db()
        try:
            await self._ensure_history_table(db)
            cursor = await db.execute(
                "SELECT * FROM preset_factor_ic_history WHERE factor_id = ? "
                "ORDER BY snapshot_at DESC LIMIT 50",
                (factor_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await db.close()

    async def recalculate_preset_factor(self, factor_id: int) -> Optional[dict]:
        """手动重算因子 IC 指标 — 采用「覆盖更新」语义

        行为约定（前端会明确标注）：
        - 新指标直接写回该因子记录（覆盖，不新增因子条目）；
        - 覆盖前旧值自动存入 preset_factor_ic_history 历史快照，可随时回溯；
        - 当前无实时行情数据源时，指标维持库内数值（不伪造数据）。
        """
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM preset_factors WHERE id = ?", (factor_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            factor = dict(row)

            # 覆盖前留存历史快照
            await self._ensure_history_table(db)
            await db.execute(
                "INSERT INTO preset_factor_ic_history "
                "(factor_id, ic_mean, rank_ic, ic_ir, ic_std, annualized_return, "
                " maximum_drawdown, sharpe_ratio, turnover_rate, data_date, snapshot_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    factor_id,
                    factor.get("ic_mean"),
                    factor.get("rank_ic"),
                    factor.get("ic_ir"),
                    factor.get("ic_std"),
                    factor.get("annualized_return"),
                    factor.get("maximum_drawdown"),
                    factor.get("sharpe_ratio"),
                    factor.get("turnover_rate"),
                    factor.get("data_date"),
                    int(time.time()),
                ),
            )
            await db.execute(
                "UPDATE preset_factors SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (factor_id,),
            )
            await db.commit()

            # 基于本地缓存行情真实重算 IC（数据充足时）；数据不足时明确告知，不伪造
            recalc = await self._recompute_ic_from_local(factor)
            if recalc.get("ok"):
                metrics = recalc["metrics"]
                sets = ", ".join(f"{k} = ?" for k in metrics)
                await db.execute(
                    f"UPDATE preset_factors SET {sets}, data_date = ? WHERE id = ?",
                    (*metrics.values(), recalc["data_date"], factor_id),
                )
                await db.commit()
                factor.update(metrics)
                factor["data_date"] = recalc["data_date"]
                factor["recalc_mode"] = "recomputed"
                factor["recalc_message"] = (
                    f"已基于本地 {recalc['n_stocks']} 只股票、"
                    f"{recalc['n_dates']} 个交易日的行情真实重算 IC 指标，旧值已存入历史快照。"
                )
            else:
                factor["recalc_mode"] = "insufficient_data"
                factor["recalc_message"] = recalc.get(
                    "message",
                    "本地行情数据不足，未重算 — 请先在数据管理页下载足够的股票与区间数据。",
                )
            return factor
        finally:
            await db.close()

    async def _recompute_ic_from_local(self, factor: dict) -> dict:
        """用本地缓存行情面板真实重算单因子 IC 指标；数据不足返回 ok=False。

        仅对公式型因子重算（从 description 提取公式）；非公式型因子返回数据不足。
        """
        formula = extract_formula(factor.get("description"))
        return self.analyze_formula_on_local(formula)

    def analyze_formula_on_local(self, formula: str) -> dict:
        """在本地缓存行情面板上对公式因子跑完整分析，返回 {ok, metrics, ...}。

        供预置因子重算与自建因子注册时的指标快照复用；数据不足时 ok=False。
        """
        if not formula:
            return {"ok": False, "message": "无可解析公式，暂不支持本地分析"}
        try:
            from backend.services import market_data, reference_data
            from backend.services.factor_operators import build_operator_namespace

            codes = market_data.list_cached_codes("1d")
            if len(codes) < 30:
                return {
                    "ok": False,
                    "message": f"本地仅 {len(codes)} 只股票缓存，不足以稳定估计 IC（至少 30 只）",
                }
            panels = market_data.load_price_panels(codes=codes)
            close = panels.get("close")
            if close is None or len(close.index) < 60:
                return {"ok": False, "message": "本地行情区间不足 60 个交易日"}
            ns = build_operator_namespace(
                panels, industry_map=reference_data.load_industry_map()
            )
            factor_df = eval(formula, {"__builtins__": {}}, ns)  # noqa: S307
            if isinstance(factor_df, pd.Series):
                factor_df = factor_df.to_frame()
            if not isinstance(factor_df, pd.DataFrame) or factor_df.empty:
                return {"ok": False, "message": "公式未产出有效因子面板"}
            return_data = close.pct_change()
            report = self.full_factor_analysis(
                factor_df.dropna(how="all"), return_data, periods=[1, 5, 10, 20]
            )
            s = report["summary"]
            metrics = {
                "ic_mean": float(s.get("ic_mean", 0.0)),
                "rank_ic": float(s.get("rank_ic", 0.0)),
                "ic_ir": float(s.get("ic_ir", 0.0)),
                "ic_std": float(s.get("ic_std", 0.0)),
                "annualized_return": float(s.get("annual_return", 0.0)),
                "maximum_drawdown": float(s.get("max_drawdown", 0.0)),
                "sharpe_ratio": float(s.get("sharpe_ratio", 0.0)),
            }
            return {
                "ok": True,
                "metrics": metrics,
                "data_date": str(close.index[-1])[:10],
                "n_stocks": len(close.columns),
                "n_dates": len(close.index),
            }
        except Exception as e:
            logger.warning(f"公式因子本地分析失败: {e}")
            return {"ok": False, "message": f"本地分析失败: {e}"}

    async def add_to_pool(self, factor_id: int) -> bool:
        """将因子加入因子池"""
        db = await get_db()
        try:
            # 检查是否已存在
            cursor = await db.execute(
                "SELECT id FROM factor_pool WHERE factor_id = ?", (factor_id,)
            )
            if await cursor.fetchone():
                return True  # 已存在，幂等
            await db.execute(
                "INSERT INTO factor_pool (factor_id) VALUES (?)", (factor_id,)
            )
            await db.commit()
            return True
        finally:
            await db.close()

    async def get_pool(self) -> list[dict]:
        """获取因子池列表"""
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT pf.* FROM preset_factors pf "
                "INNER JOIN factor_pool fp ON fp.factor_id = pf.id "
                "ORDER BY fp.added_at DESC"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            await db.close()

    async def remove_from_pool(self, factor_id: int) -> bool:
        """从因子池移除因子"""
        db = await get_db()
        try:
            await db.execute(
                "DELETE FROM factor_pool WHERE factor_id = ?", (factor_id,)
            )
            await db.commit()
            return True
        finally:
            await db.close()


# 全局单例
factor_research = FactorResearchService()
