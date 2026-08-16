"""因子研究服务 — 提供 IC 分析、分层收益、中性化、相关性等功能"""

import json
import re
import time
from typing import AsyncGenerator, Optional

import numpy as np
import pandas as pd
from loguru import logger

from backend.database import get_db

# ── 公式提取与 LaTeX 转换 ─────────────────────────────────────

_FORMULA_MARKERS = ["公式是：", "计算公式：", "公式：", "公式为："]


def _parse_metric_sample(raw) -> dict:
    """把 metric_sample_json 解析为 dict，兼容旧数据"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        import json as _json

        return _json.loads(raw)
    except Exception:
        return {}


def _sample_window_warning(start_date, data_date) -> str | None:
    """样本窗口警示：不足 2 年时提示统计量置信度（因子体检同类口径）"""
    try:
        if not start_date or not data_date:
            return None
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(data_date)
        years = (end - start).days / 365.25
        if years < 1:
            return (
                f"样本窗口仅 {years:.2f} 年（{start.date()} ~ {end.date()}）："
                "IC/ICIR 基于短样本，统计量置信度低，不宜作为长期结论"
            )
        if years < 2:
            return (
                f"样本窗口 {years:.2f} 年（{start.date()} ~ {end.date()}）："
                "IC 统计量基于 1-2 年样本，结论需谨慎（2 年以上更可靠）"
            )
    except Exception:
        pass
    return None

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
        mask: pd.DataFrame | None = None,
    ) -> dict:
        """IC 分析

        Args:
            factor_data: 因子值 DataFrame (index=date, columns=stocks)
            return_data: 收益率 DataFrame (index=date, columns=stocks)，
                r[T] 为 T-1→T 日收益（close.pct_change 口径）
            periods: 分析周期列表
            mask: 可选 每日可交易掩码（True=可交易，index=date, columns=stock）。
                传则每期截面只统计可交易标的（排除 ST/次新/一字/停牌，防污染 IC）。

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
                if mask is not None and date in mask.index:
                    tradable_types = mask.loc[date]
                    tradable = tradable_types[tradable_types.fillna(0).astype(float) > 0]
                    common = common.intersection(tradable.index)
                if len(common) < 10:
                    continue

                f = factor_values[common]
                r = future_returns[common]

                ic = f.corr(r)
                if ic is not None and np.isfinite(ic):
                    ic_series.append({"date": str(date), "ic": ic})

                rank_ic = f.rank().corr(r.rank())
                if rank_ic is not None and np.isfinite(rank_ic):
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
            # 样本标准差（ddof=1，与 pandas 系列 std() 口径一致），n<2 时无意义置 0
            ic_std = float(ic_arr.std(ddof=1)) if ic_arr.size > 1 else 0.0
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
                "rank_ic_ir": float(np.mean(rank_ic_values) / np.std(rank_ic_values, ddof=1))
                if len(rank_ic_values) > 1 and np.std(rank_ic_values, ddof=1) > 0
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
        mask: pd.DataFrame | None = None,
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
            if mask is not None and date in mask.index:
                mrow = mask.loc[date]
                tradable = mrow[mrow.fillna(0).astype(float) > 0]
                common = common.intersection(tradable.index)
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
        mask: pd.DataFrame | None = None,
    ) -> dict:
        """完整单因子分析报告（对齐官网因子分析节点）

        产出：数据卡指标、分组绩效表（含多空组合）、分组/超额累计收益曲线、
        IC 与 Rank_IC 的时序/累计/分布/自相关/衰减、最新一期因子值排名。
        为「因子分析」节点与因子研究页共用入口，全部基于 QMT 行情面板做截面计算。
        """
        periods = periods or [1, 5, 10, 20]
        ic = self.ic_analysis(factor_data, return_data, periods, mask=mask)

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
        gd, bench = self._group_daily_returns(
            factor_data, return_data, n_groups, mask=mask
        )
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
            # 单调性只奖励「组序号越高收益越高」的单调递增方向，避免反向因子也被打满分
            monotonicity = inc
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
        self, factor_data: pd.DataFrame, return_data: pd.DataFrame, n_groups: int,
        mask: pd.DataFrame | None = None,
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
            if mask is not None and date in mask.index:
                mrow = mask.loc[date]
                tradable = mrow[mrow.fillna(0).astype(float) > 0]
                common = common.intersection(tradable.index)
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
        """同时计算 IC(pearson) 与 RankIC(spearman) 随持有期的衰减序列

        与 ic_analysis 同口径：IC(period=p) 用 factor(T) 对 T→T+p 的复利收益，
        而非仅取第 p 日的单日收益，保证衰减曲线与 IC 汇总表可互相印证。
        """
        ic_decay, rank_decay = [], []
        dates = factor_data.index
        for period in range(1, max_period + 1):
            ics, rics = [], []
            for i in range(len(dates) - period):
                f = factor_data.loc[dates[i]].dropna()
                if dates[i + period] in return_data.index:
                    comp = (1.0 + return_data.loc[dates[i + 1]: dates[i + period]]).prod() - 1.0
                else:
                    comp = pd.Series(dtype=float)
                common = f.index.intersection(comp.index)
                if len(common) > 10:
                    fc, rc = f[common], comp[common]
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
                # 与 IC 汇总表同口径：取 T→T+p 复利收益而非第 p 日单日收益
                if dates[i + period] in return_data.index:
                    comp = (1.0 + return_data.loc[dates[i + 1]: dates[i + period]]).prod() - 1.0
                else:
                    comp = pd.Series(dtype=float)
                common = f.index.intersection(comp.index)
                if len(common) > 10:
                    ic_value = f[common].corr(comp[common])
                    if ic_value is not None and np.isfinite(ic_value):
                        ic_values.append(ic_value)

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
            # 先做横截面去均值再除以横截面标准差（z-score）：避免非零均值因子
            # 把「市场/水平」整体带进合成因子，导致多空方向被系统性偏置
            demeaned = df.sub(df.mean(axis=1), axis=0)
            std = demeaned.std(axis=1).replace(0, np.nan)
            standardized[name] = demeaned.div(std, axis=0) * weights.get(name, 0.0)

        combined = sum(standardized.values())
        return combined

    def _ic_weights(
        self,
        factors: dict[str, pd.DataFrame],
        return_data: pd.DataFrame,
        ic_window: int,
        as_of=None,
    ) -> dict[str, float]:
        """按各因子近 ic_window 期 RankIC 均值计算权重：|IC| 归一、符号对齐方向

        Args:
            as_of: 仅用 <= as_of 的截面计算权重（点-in-time）；None=用样本尾部。
                组合回测闭环请传入逐日 as_of（见 _rolling_ic_weights），
                避免用整段样本的 IC 给区间头部信号加权造成前视。
        """
        if return_data is None or return_data.empty:
            raise ValueError(
                "ic_weighted 合成需要 return_data（收益面板） — "
                "请连线上游因子构建节点的 return_data，或改用等权合成"
            )
        ics: dict[str, float] = {}
        for name, fac in factors.items():
            dates = fac.index
            if as_of is not None:
                dates = dates[dates <= as_of]
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

        return self._normalize_ic_weights(ics)

    def _normalize_ic_weights(self, ics: dict[str, float]) -> dict[str, float]:
        """|IC| 归一为权重、符号对齐方向；全部近 0 时回退等权（合理默认，非静默）"""
        total = sum(abs(v) for v in ics.values())
        if total < 1e-12:
            n = len(ics)
            return {name: 1.0 / n for name in ics}
        return {
            name: (abs(v) / total) * (1.0 if v >= 0 else -1.0)
            for name, v in ics.items()
        }

    def _rolling_ic_weights(
        self,
        factors: dict[str, pd.DataFrame],
        return_data: pd.DataFrame,
        ic_window: int,
        min_window: int = 20,
    ) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
        """逐日滚动 RankIC 权重（样本外口径，无前视）：T 日权重只用 (T-window, T) 的信息

        对每个因子先算逐日 RankIC（T 日因子 vs T+1 日收益），再做滚动均值；
        **IC[T] 需要 T+1 日收益才能算出，因此在 T 日不可得**——权重必须用
        IC 序列 shift(1) 后的滚动均值（只用 ≤ T-1 的 IC），否则当日权重会用上
        自己即将赚到的收益（1 日前视，组合收益虚高）。
        T 日截面权重 = |滚动IC| 归一、符号对齐方向；窗口样本不足时权重为 NaN。

        Returns:
            (weights, ic_series): {name: Series(index=date, 权重)} 与
            {name: Series(index=date, 滚动 RankIC, 仅展示用——含当日 IC，
            为样本内诊断量，不等同于可用权重)}
        """
        if return_data is None or return_data.empty:
            raise ValueError(
                "ic_weighted 合成需要 return_data（收益面板） — "
                "请连线上游因子构建节点的 return_data，或改用等权合成"
            )
        ics: dict[str, pd.Series] = {}
        for name, fac in factors.items():
            dates = fac.index
            vals: dict = {}
            for i in range(len(dates) - 1):
                f = fac.loc[dates[i]].dropna()
                nxt = dates[i + 1]
                if nxt not in return_data.index:
                    continue
                r = return_data.loc[nxt].dropna()
                common = f.index.intersection(r.index)
                if len(common) > 10:
                    vals[dates[i]] = f[common].rank().corr(r[common].rank())
            s = pd.Series(vals).sort_index()
            # 关键：shift(1) 剔除当日 IC（当日 IC 需要次日收益，T 日不可得）
            ics[name] = s.shift(1).rolling(
                ic_window, min_periods=min_window
            ).mean()

        out_w: dict[str, pd.Series] = {}
        out_ic: dict[str, pd.Series] = {}
        # 逐日截面：|IC| 矩阵 (date × factor) → 行归一为权重（同日因子间竞争）
        abs_ic = pd.DataFrame({name: s for name, s in ics.items()}).sort_index()
        total = abs_ic.abs().sum(axis=1).replace(0, np.nan)
        w = abs_ic.abs().div(total, axis=0) * np.sign(abs_ic)
        for name in ics:
            out_ic[name] = ics[name]
            out_w[name] = w[name].dropna()
        return out_w, out_ic

    def quantile_analysis_net(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        n_groups: int = 5,
        cost_rate: float = 0.001,
    ) -> dict:
        """分层收益的「扣费后」口径：分组日收益再扣掉因换手产生的双边交易成本。

        换手 = 相邻期成分股集合同侧变化占比，成本 = rspcost_rate × 换手 × 2。
        解决"换手率高但净收益被成本吃掉"的假象。
        """
        gd, _ = self._group_daily_returns(factor_data, return_data, n_groups)
        tov = self._turnover_by_group(factor_data, n_groups)

        out: dict[str, dict] = {}
        gross_total = self.quantile_analysis(factor_data, return_data, n_groups)
        mean_gross = gross_total.get("mean_return_by_group", {})
        for lab in gd.keys():
            label = lab[1:]  # G1 → 1
            turnover = float(tov.get(lab, 0.0))
            daily = gd[lab].dropna()
            net_daily = daily - cost_rate * turnover * 2.0
            net_cum = float(np.prod(1 + net_daily) - 1)
            gross_cum = float(np.prod(1 + daily) - 1)
            mean_net = float(net_daily.mean())
            out[label] = {
                "gross_cum": gross_cum,
                "net_cum": net_cum,
                "net_vs_gross": net_cum - gross_cum,
                "turnover": turnover,
                "cost_annual_est": cost_rate * turnover * 2.0 * 252,
                "mean_gross": float(mean_gross.get(label, 0.0)),
                "mean_net": mean_net,
            }
        return {"by_group": out, "cost_rate": cost_rate, "n_groups": n_groups}

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
            for f in items:
                f["metric_sample"] = _parse_metric_sample(f.get("metric_sample_json"))
                f["sample_warning"] = _sample_window_warning(
                    f.get("start_date"), f.get("data_date")
                )
                if f.get("metric_source") != "local_recalc" and f.get("ic_mean") is not None:
                    f["sample_warning"] = (
                        "指标为外部参考样本（非本地 QMT 重算），仅可用于公式参考；"
                        "入池/筛选前请先重算。"
                        + (f"；{f['sample_warning']}" if f.get("sample_warning") else "")
                    )

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
            factor["metric_sample"] = _parse_metric_sample(factor.get("metric_sample_json"))
            factor["sample_warning"] = _sample_window_warning(
                factor.get("start_date"), factor.get("data_date")
            )
            if factor.get("metric_source") != "local_recalc" and factor.get("ic_mean") is not None:
                factor["sample_warning"] = (
                    "指标为外部参考样本（非本地 QMT 重算），仅可用于公式参考；"
                    "入池/筛选前请先重算。"
                    + (f"；{factor['sample_warning']}" if factor.get("sample_warning") else "")
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
                sample_meta = {
                    "source": "local_qmt",
                    "n_stocks": recalc.get("n_stocks", 0),
                    "n_dates": recalc.get("n_dates", 0),
                    "start_date": recalc.get("start_date"),
                    "data_date": recalc.get("data_date"),
                }
                sets = ", ".join(f"{k} = ?" for k in metrics)
                await db.execute(
                    f"UPDATE preset_factors SET {sets}, start_date = ?, data_date = ?, "
                    "metric_source = 'local_recalc', metric_sample_json = ? WHERE id = ?",
                    (
                        *metrics.values(),
                        recalc.get("start_date"),
                        recalc["data_date"],
                        json.dumps(sample_meta, ensure_ascii=False),
                        factor_id,
                    ),
                )
                await db.commit()
                factor.update(metrics)
                factor["start_date"] = recalc.get("start_date")
                factor["data_date"] = recalc["data_date"]
                factor["metric_source"] = "local_recalc"
                factor["metric_sample_json"] = json.dumps(sample_meta, ensure_ascii=False)
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
            # 溯源：把本次重算的参数与指标写进 provenance，保证可复现
            try:
                from backend.services.provenance import record_provenance

                await record_provenance(
                    kind="factor",
                    entity_id=str(factor_id),
                    entity_name=factor.get("factor_name", ""),
                    params={
                        "factor_code": factor.get("factor_code", ""),
                        "formula": factor.get("formula", ""),
                        "universe_n": recalc.get("n_stocks", 0),
                        "n_dates": recalc.get("n_dates", 0),
                        "adj": "front",
                        "periods": [1, 5, 10, 20],
                        "stock_pool": factor.get("stock_pool", ""),
                    },
                    metrics=factor.get("recalc_mode") == "recomputed"
                    and recalc.get("metrics")
                    or {},
                    notes=factor.get("recalc_message", ""),
                    source="manual" if factor.get("recalc_mode") == "recomputed" else "noop",
                )
            except Exception as e:
                logger.warning(f"记录因子溯源失败: {e}")
            return factor
        finally:
            await db.close()

    async def _recompute_ic_from_local(self, factor: dict) -> dict:
        """用本地缓存行情面板真实重算单因子 IC 指标；数据不足返回 ok=False。

        仅对公式型因子重算（从 description 提取公式）；非公式型因子返回数据不足。
        """
        formula = extract_formula(factor.get("description"))
        return self.analyze_formula_on_local(formula)

    async def add_to_pool(self, factor_id: int) -> bool:
        """将因子加入因子池。

        入池门槛：指标必须来自本地 QMT 样本重算（metric_source=local_recalc），
        且样本规模达到方法验证下限。外部参考指标或小样本扫描结果不得直接入池，
        避免把未经验证的因子送进组合回测。
        """
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT id FROM factor_pool WHERE factor_id = ?", (factor_id,)
            )
            if await cursor.fetchone():
                return True  # 已存在，幂等
            cursor = await db.execute(
                "SELECT metric_source, metric_sample_json, factor_name "
                "FROM preset_factors WHERE id = ?",
                (factor_id,),
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError("因子不存在")
            source = row["metric_source"] or ""
            sample = _parse_metric_sample(row["metric_sample_json"])
            if source != "local_recalc":
                raise ValueError(
                    f"「{row['factor_name']}」的指标仍为外部参考值，未基于本地 QMT 样本重算；"
                    "请先在因子详情页点击「重算」再入池"
                )
            n_stocks = int(sample.get("n_stocks") or 0)
            n_dates = int(sample.get("n_dates") or 0)
            if n_stocks < 300 or n_dates < 252:
                raise ValueError(
                    f"「{row['factor_name']}」本地样本仅 {n_stocks} 只股票 / {n_dates} 个交易日，"
                    "未达到入池门槛（≥300 只、≥252 个交易日）；请先补全 QMT 行情后重算"
                )
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

    # ── 公式在本地行情上的求值（供单因子重算 / 批量扫描 / 样本外验证复用）──

    def eval_formula_on_local(
        self,
        formula: str,
        start_date: str = "",
        end_date: str = "",
    ) -> dict:
        """在本地缓存行情面板上对公式求值，返回因子面板与配套研究数据

        自动识别日内高频公式（含 m_ 字段 / ID_ / M_ 算子 / 现成高频函数）并路由
        到 5m 分钟面板求值（清洗后折叠为日频），否则走日频面板。

        Returns:
            {ok, factor_df, return_data, mask, data_date, n_stocks, n_dates, message}
            数据不足或公式报错时 ok=False（message 说明原因，不伪造数据）。
        """
        if not formula:
            return {"ok": False, "message": "无可解析公式，暂不支持本地分析"}
        if self._is_intraday_formula(formula):
            return self._eval_intraday_on_local(formula, start_date, end_date)
        try:
            from backend.services import market_data, reference_data
            from backend.services.factor_operators import build_operator_namespace

            codes = market_data.list_cached_codes("1d", exclude_indices=True)
            if len(codes) < 30:
                return {
                    "ok": False,
                    "message": f"本地仅 {len(codes)} 只股票缓存，不足以稳定估计 IC（至少 30 只）",
                }
            panels = market_data.load_price_panels(
                codes=codes, start_date=start_date, end_date=end_date
            )
            close = panels.get("close")
            if close is None or len(close.index) < 60:
                return {"ok": False, "message": "本地行情区间不足 60 个交易日"}
            ns = build_operator_namespace(
                panels, industry_map=reference_data.load_industry_map()
            )
            try:
                from backend.services.fundamental import build_fundamental_panels

                fund = build_fundamental_panels(codes, panels["close"].index)
                if fund:
                    ns.update({f"fund_{f}": p for f, p in fund.items()})
                    ns.update({f"FUND_{f.upper()}": p for f, p in fund.items()})
            except Exception:
                pass
            factor_df = eval(formula, {"__builtins__": {}}, ns)  # noqa: S307
            if isinstance(factor_df, pd.Series):
                factor_df = factor_df.to_frame()
            if not isinstance(factor_df, pd.DataFrame) or factor_df.empty:
                return {"ok": False, "message": "公式未产出有效因子面板"}
            return_data = market_data.build_return_panel(close)
            mask = None
            try:
                from backend.services.market_data import build_cross_section_mask

                mask = build_cross_section_mask(panels)
            except Exception:
                mask = None
            return {
                "ok": True,
                "factor_df": factor_df,
                "return_data": return_data,
                "mask": mask,
                "panels": panels,
                "data_date": str(close.index[-1])[:10],
                "n_stocks": len(close.columns),
                "n_dates": len(close.index),
            }
        except Exception as e:
            logger.warning(f"公式因子本地求值失败: {e}")
            return {"ok": False, "message": f"本地分析失败: {e}"}

    @staticmethod
    def _is_intraday_formula(formula: str) -> bool:
        """分钟语法检测：m_ 字段 / ID_ 聚合 / M_ 序列 / 现成高频函数名"""
        tokens = [
            "m_open", "m_high", "m_low", "m_close", "m_volume", "m_amount",
            "M_OPEN", "M_CLOSE", "M_HIGH", "M_LOW", "M_VOLUME", "M_AMOUNT",
            "ID_", "M_DELAY", "M_MA", "M_SUM", "M_STD", "M_CUMSUM",
            "TAIL_RET", "OPEN_RET", "JUMP_DAY", "AMIHUD5", "VWAP_DEV",
            "VOLUME_CLOCK", "AUC_VOL_RATIO", "LIMIT_UP_TIME",
            "OVERNIGHT_RET", "INTRADAY_RET", "RV(",
        ]
        return any(t in formula for t in tokens)

    def _eval_intraday_on_local(
        self, formula: str, start_date: str = "", end_date: str = ""
    ) -> dict:
        """分钟公式在本地 5m 分钟缓存上求值（清洗 → 求值 → 折叠日频）"""
        try:
            from backend.services import market_data
            from backend.services.intraday_cleaner import load_intraday_panels
            from backend.services.intraday_operators import (
                ID_LAST,
                build_intraday_namespace,
            )

            codes = market_data.list_cached_codes("5m")
            if len(codes) < 30:
                return {
                    "ok": False,
                    "message": (
                        f"本地仅 {len(codes)} 只股票有 5m 分钟缓存，不足以稳定估计 IC"
                        "（至少 30 只）— 请先在数据管理下载分钟行情"
                    ),
                }
            loaded = load_intraday_panels(
                codes=codes, period="5m", start_date=start_date, end_date=end_date
            )
            panels, meta = loaded["panels"], loaded["meta"]
            ns = build_intraday_namespace(panels, meta)
            factor_df = eval(formula, {"__builtins__": {}}, ns)  # noqa: S307
            if isinstance(factor_df, pd.Series):
                factor_df = factor_df.to_frame()
            if not isinstance(factor_df, pd.DataFrame) or factor_df.empty:
                return {"ok": False, "message": "分钟公式未产出有效因子面板"}
            idx = pd.to_datetime(factor_df.index)
            if (idx.normalize() != idx).any():
                factor_df = ID_LAST(factor_df, 0)
            factor_df = factor_df.sort_index()
            close = panels["close"]
            daily_close = (
                close.groupby(close.index.normalize()).last().sort_index()
            )
            daily_close = daily_close.reindex(factor_df.index, method="ffill").fillna(
                method="ffill"
            )
            return_data = market_data.build_return_panel(daily_close)
            mask = None
            return {
                "ok": True,
                "factor_df": factor_df,
                "return_data": return_data,
                "mask": mask,
                "panels": panels,
                "data_date": str(close.index[-1].date()),
                "n_stocks": len(factor_df.columns),
                "n_dates": len(factor_df.index),
                "intraday": True,
                "period": "5m",
                "cleaned": loaded["cleaned"],
            }
        except Exception as e:
            logger.warning(f"分钟公式本地求值失败: {e}")
            return {"ok": False, "message": f"分钟因子本地分析失败: {e}"}

    def analyze_formula_on_local(self, formula: str) -> dict:
        """在本地缓存行情面板上对公式因子跑完整分析，返回 {ok, metrics, ...}。

        供预置因子重算与自建因子注册时的指标快照复用；数据不足时 ok=False。
        """
        res = self.eval_formula_on_local(formula)
        if not res.get("ok"):
            return {"ok": False, "message": res.get("message", "")}
        report = self.full_factor_analysis(
            res["factor_df"].dropna(how="all"),
            res["return_data"],
            periods=[1, 5, 10, 20],
            mask=res.get("mask"),
        )
        s = report["summary"]
        turnover = float(
            self.turnover_analysis(res["factor_df"].dropna(how="all")).get(
                "avg_turnover", 0.0
            )
        )
        metrics = {
            "ic_mean": float(s.get("ic_mean", 0.0)),
            "rank_ic": float(s.get("rank_ic", 0.0)),
            "ic_ir": float(s.get("ic_ir", 0.0)),
            "ic_std": float(s.get("ic_std", 0.0)),
            "annualized_return": float(s.get("annual_return", 0.0)),
            "maximum_drawdown": float(s.get("max_drawdown", 0.0)),
            "sharpe_ratio": float(s.get("sharpe_ratio", 0.0)),
            "turnover_rate": turnover,
        }
        return {
            "ok": True,
            "metrics": metrics,
            "start_date": res.get("start_date"),
            "data_date": res["data_date"],
            "n_stocks": res["n_stocks"],
            "n_dates": res["n_dates"],
        }

    # ── 因子批量扫描（P1）─────────────────────────────────────

    @staticmethod
    def _scan_factor_metrics(
        factor_df: pd.DataFrame,
        return_data: pd.DataFrame,
        periods: list[int] | None = None,
        mask: pd.DataFrame | None = None,
    ) -> dict:
        """单因子的扫描指标：核心 IC 指标 + 分层多空（轻量，不做完整报告）

        与 ic_analysis / quantile_analysis 同口径，保证扫描结果与详情页一致。
        """
        periods = periods or [1, 5, 10, 20]
        ic = FactorResearchService().ic_analysis(
            factor_df, return_data, periods=[periods[0]], mask=mask
        )
        base = ic.get(f"period_{periods[0]}", {})
        quantile = FactorResearchService().quantile_analysis(
            factor_df, return_data, n_groups=5, mask=mask
        )
        ls_series = quantile.get("long_short_series", [])
        ls_cum = float(ls_series[-1]["cum_return"]) if ls_series else 0.0
        spreads = [float(x["spread"]) for x in ls_series if x.get("spread") is not None]
        n_ls = len(spreads)
        if n_ls:
            spread_arr = np.asarray(spreads, dtype=float)
            annual_return = float((1.0 + ls_cum) ** (252.0 / n_ls) - 1.0)
            vol = float(spread_arr.std(ddof=1) * np.sqrt(252)) if n_ls > 1 else 0.0
            sharpe = float(spread_arr.mean() / spread_arr.std(ddof=1) * np.sqrt(252)) if n_ls > 1 and spread_arr.std(ddof=1) > 0 else 0.0
            nav = 1.0 + np.asarray([x["cum_return"] for x in ls_series], dtype=float)
            max_dd = float((nav / np.maximum.accumulate(nav) - 1.0).min())
        else:
            annual_return = 0.0
            vol = 0.0
            sharpe = 0.0
            max_dd = 0.0
        return {
            "ic_mean": float(base.get("ic_mean", 0.0)),
            "rank_ic": float(base.get("rank_ic_mean", 0.0)),
            "ic_ir": float(base.get("ic_ir", 0.0)),
            "ic_std": float(base.get("ic_std", 0.0)),
            "t_stat": float(base.get("ic_tstat", 0.0)),
            "positive_ratio": float(base.get("ic_positive_ratio", 0.0)),
            "n_cross_sections": int(len(base.get("ic_series", []))),
            "long_short_cum": ls_cum,
            "monotonicity": float(quantile.get("monotonicity", 0.0)),
            "annualized_return": annual_return,
            "maximum_drawdown": max_dd,
            "sharpe_ratio": sharpe,
            "long_short_vol": vol,
        }

    async def scan_factors_stream(
        self,
        factor_ids: list[int] | None = None,
        category_codes: list[str] | None = None,
        limit: int = 100,
        start_date: str = "",
        end_date: str = "",
        periods: list[int] | None = None,
        max_workers: int = 4,
        stock_pool: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """批量扫描因子 IC（SSE 逐因子进度）

        事件类型：
          scan_start:  {total, factor_ids}
          factor_done: {index, factor_id, factor_name, ok, metrics|error}
          scan_done:   {ok_count, failed, failed_names, data_date,
                        n_stocks, n_dates, duration_ms}

        面板只加载一次、全因子共享；预置因子指标「覆盖更新」写入库并留存历史快照。
        """
        import asyncio
        import concurrent.futures
        import time

        from backend.services import market_data

        started = time.perf_counter()

        # 1. 取因子清单（按 id 或类别过滤），仅扫描公式型因子
        db = await get_db()
        try:
            clauses, params = [], []
            if factor_ids:
                marks = ",".join("?" * len(factor_ids))
                clauses.append(f"id IN ({marks})")
                params.extend(factor_ids)
            if category_codes:
                marks = ",".join("?" * len(category_codes))
                clauses.append(f"category_code IN ({marks})")
                params.extend(category_codes)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            cursor = await db.execute(
                f"SELECT * FROM preset_factors{where} ORDER BY id LIMIT ?",
                (*params, limit),
            )
            rows = [dict(r) for r in await cursor.fetchall()]
        finally:
            await db.close()

        targets = []
        for row in rows:
            formula = extract_formula(row.get("description"))
            if not formula:
                continue
            targets.append(
                {
                    "factor_id": row["id"],
                    "factor_name": row.get("factor_name", ""),
                    "category_name": row.get("category_name", ""),
                    "formula": formula,
                }
            )
        if not targets:
            yield _sse("scan_done", {"ok_count": 0, "failed": 0, "failed_names": [],
                                     "message": "所选因子均无可解析公式（仅支持公式型因子）"})
            return

        # 按公式语法分流：日内高频（分钟）公式走 5m 面板，其余走日频面板
        intraday_targets = [
            t for t in targets if self._is_intraday_formula(t["formula"])
        ]
        daily_targets = [t for t in targets if t not in intraday_targets]
        intraday_panels = None
        intraday_ns = None
        if intraday_targets:
            try:
                from backend.services.intraday_cleaner import load_intraday_panels
                from backend.services.intraday_operators import (
                    ID_LAST,
                    build_intraday_namespace,
                )

                loaded = await asyncio.to_thread(
                    load_intraday_panels, codes=[], period="5m",
                    start_date=start_date, end_date=end_date,
                )
                if loaded["panels"].get("close") is not None and not loaded["panels"]["close"].empty:
                    intraday_panels = {
                        "panels": loaded["panels"],
                        "meta": loaded["meta"],
                        "close": loaded["panels"]["close"].groupby(
                            loaded["panels"]["close"].index.normalize()
                        ).last().sort_index(),
                    }
                    intraday_ns = build_intraday_namespace(loaded["panels"], loaded["meta"])
            except Exception as e:  # noqa: BLE001
                logger.warning(f"批量扫描：分钟面板加载失败，日内因子将报错: {e}")

        # 2. 加载面板（一次）+ 构造求值命名空间。
        # 全市场扫描内存保护：按最大行数 × 股票数 × 5 个价格字段估算内存，
        # 超过可用内存的 65% 时提示分块/缩短区间，而不是把机器拖到 OOM。
        codes = list(stock_pool or []) or market_data.list_cached_codes(
            "1d", exclude_indices=True
        )
        try:
            import psutil

            coverage = market_data.cache_coverage("1d")
            rows_by_code = {e["code"]: int(e.get("rows") or 0) for e in coverage}
            max_rows = max(
                (rows_by_code.get(c, 0) for c in codes), default=0
            )
            if max_rows > 0 and len(codes) > 0:
                estimated = max_rows * len(codes) * 5 * 8 * 2.5
                available = psutil.virtual_memory().available
                if estimated > available * 0.65 and estimated > 512 * 1024 * 1024:
                    yield _sse(
                        "scan_done",
                        {
                            "ok_count": 0,
                            "failed": len(targets),
                            "failed_names": [t["factor_name"] for t in targets],
                            "message": (
                                f"预计面板内存约 {estimated / 1024**3:.1f} GB，"
                                f"超过可用内存 65%（可用 {available / 1024**3:.1f} GB）。"
                                "请缩小日期区间，或在请求中传入 stock_pool 分批扫描"
                            ),
                        },
                    )
                    return
        except Exception as e:  # noqa: BLE001
            logger.debug(f"扫描内存预估失败，继续执行: {e}")

        try:
            panels = await asyncio.to_thread(
                market_data.load_price_panels,
                codes=codes,
                start_date=start_date,
                end_date=end_date,
            )
        except ValueError as e:
            if intraday_panels is not None and intraday_panels.get("close") is not None:
                panels = {"close": intraday_panels["close"], "volume": None, "amount": None}
            else:
                yield _sse("scan_done", {"ok_count": 0, "failed": len(targets),
                                         "failed_names": [t["factor_name"] for t in targets],
                                         "message": str(e)})
                return

        from backend.services import reference_data
        from backend.services.factor_operators import build_operator_namespace

        ns = build_operator_namespace(
            panels, industry_map=reference_data.load_industry_map()
        )
        try:
            from backend.services.fundamental import build_fundamental_panels

            fund = build_fundamental_panels(
                list(panels["close"].columns), panels["close"].index
            )
            if fund:
                ns.update({f"fund_{f}": p for f, p in fund.items()})
                ns.update({f"FUND_{f.upper()}": p for f, p in fund.items()})
        except Exception:
            pass
        return_data = market_data.build_return_panel(panels["close"])
        mask = None
        try:
            mask = market_data.build_cross_section_mask(panels)
        except Exception:
            mask = None

        yield _sse("scan_start", {"total": len(targets), "factor_ids": [t["factor_id"] for t in targets]})

        def _eval_one(item: dict) -> dict:
            t0 = time.perf_counter()
            try:
                if item in intraday_targets:
                    if intraday_ns is None:
                        return {**item, "ok": False, "error": "分钟面板不可用（无 5m 缓存）"}
                    factor_df = eval(item["formula"], {"__builtins__": {}}, intraday_ns)  # noqa: S307
                    if isinstance(factor_df, pd.Series):
                        factor_df = factor_df.to_frame()
                    if isinstance(factor_df, pd.DataFrame) and not factor_df.empty:
                        idx = pd.to_datetime(factor_df.index)
                        if (idx.normalize() != idx).any():
                            from backend.services.intraday_operators import ID_LAST

                            factor_df = ID_LAST(factor_df, 0)
                        factor_df = factor_df.sort_index()
                    if not isinstance(factor_df, pd.DataFrame) or factor_df.empty:
                        return {**item, "ok": False, "error": "分钟公式未产出有效因子面板"}
                    daily_close = intraday_panels["close"].reindex(
                        factor_df.index, method="ffill"
                    ).ffill()
                    metrics = self._scan_factor_metrics(
                        factor_df.dropna(how="all"),
                        market_data.build_return_panel(daily_close),
                        periods,
                        None,
                    )
                    return {
                        **item,
                        "ok": True,
                        "metrics": metrics,
                        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                        "intraday": True,
                    }
                factor_df = eval(item["formula"], {"__builtins__": {}}, ns)  # noqa: S307
                if isinstance(factor_df, pd.Series):
                    factor_df = factor_df.to_frame()
                if not isinstance(factor_df, pd.DataFrame) or factor_df.empty:
                    return {**item, "ok": False, "error": "公式未产出有效因子面板"}
                metrics = self._scan_factor_metrics(
                    factor_df.dropna(how="all"), return_data, periods, mask
                )
                if int(metrics.get("n_cross_sections") or 0) == 0:
                    return {
                        **item,
                        "ok": False,
                        "error": "有效截面不足（股票数 < 10 或因子值全为空）",
                        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                    }
                return {
                    **item,
                    "ok": True,
                    "metrics": metrics,
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                    "n_stocks": int(factor_df.shape[1]),
                    "n_dates": int(factor_df.shape[0]),
                }
            except Exception as e:  # noqa: BLE001
                return {**item, "ok": False, "error": str(e)[:300]}

        ok_count = 0
        failed_names: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_eval_one, t): i for i, t in enumerate(targets)}
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                if res.get("ok"):
                    ok_count += 1
                    await self._persist_scan_result(res, return_data)
                else:
                    failed_names.append(res.get("factor_name", ""))
                yield _sse("factor_done", res)

        n_stocks = len(panels["close"].columns)
        n_dates = len(panels["close"].index)
        qmt_calendar = market_data._trading_calendar()
        date_unit = "交易日" if qmt_calendar else "观测日（QMT 未连接，未校验交易日历）"
        warnings: list[str] = []
        if n_stocks < 300:
            warnings.append(
                f"样本仅 {n_stocks} 只股票（建议 ≥300），IC/分层稳定性不足，"
                "结果仅用于方法验证，不宜直接入池"
            )
        if n_dates < 252:
            warnings.append(
                f"样本仅 {n_dates} 个{date_unit}（建议 ≥252/1 年），不足以覆盖完整牛熊"
            )
        n_tested = max(int(ok_count), 1)
        expected_fp_5pct = round(n_tested * 0.05, 1)
        warnings.append(
            f"批量扫描共检验 {ok_count} 个因子，按 5% 显著性水平期望产生约 "
            f"{expected_fp_5pct} 个假阳性；按扫描排名直接入池存在数据挖掘偏差，"
            "候选因子必须先通过样本外验证（walk-forward）再入池"
        )
        yield _sse(
            "scan_done",
            {
                "ok_count": ok_count,
                "failed": len(failed_names),
                "failed_names": failed_names,
                "data_date": str(panels["close"].index[-1])[:10],
                "n_stocks": n_stocks,
                "n_dates": n_dates,
                "calendar": "qmt" if qmt_calendar else "weekday_approx",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "warnings": warnings,
                "multiple_testing": {
                    "n_tested": n_tested,
                    "expected_false_positives_5pct": expected_fp_5pct,
                    "bonferroni_p_value": round(0.05 / n_tested, 6),
                    "note": "样本内扫描只用于粗筛；入池前请对候选因子运行样本外验证",
                },
            },
        )

    async def _persist_scan_result(self, res: dict, return_data: pd.DataFrame) -> None:
        """扫描结果写回预置因子（覆盖更新语义）+ 留存历史快照 + 溯源"""
        db = await get_db()
        try:
            await self._ensure_history_table(db)
            m = res["metrics"]
            factor_id = res["factor_id"]
            cursor = await db.execute(
                "SELECT ic_mean, rank_ic, ic_ir, ic_std, annualized_return, "
                "maximum_drawdown, sharpe_ratio, turnover_rate, data_date "
                "FROM preset_factors WHERE id = ?",
                (factor_id,),
            )
            row = await cursor.fetchone()
            old = dict(row) if row else {}
            await db.execute(
                "INSERT INTO preset_factor_ic_history "
                "(factor_id, ic_mean, rank_ic, ic_ir, ic_std, annualized_return, "
                " maximum_drawdown, sharpe_ratio, turnover_rate, data_date, snapshot_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    factor_id,
                    old.get("ic_mean"),
                    old.get("rank_ic"),
                    old.get("ic_ir"),
                    old.get("ic_std"),
                    old.get("annualized_return"),
                    old.get("maximum_drawdown"),
                    old.get("sharpe_ratio"),
                    old.get("turnover_rate"),
                    old.get("data_date"),
                    int(time.time()),
                ),
            )
            sample_meta = {
                "source": "local_qmt",
                "n_stocks": int(res.get("n_stocks") or return_data.shape[1]),
                "n_dates": int(res.get("n_dates") or return_data.shape[0]),
                "start_date": str(return_data.index[0])[:10],
                "data_date": str(return_data.index[-1])[:10],
                "updated_fields": [
                    "ic_mean",
                    "rank_ic",
                    "ic_ir",
                    "ic_std",
                    "annualized_return",
                    "maximum_drawdown",
                    "sharpe_ratio",
                    "start_date",
                    "data_date",
                ],
            }
            await db.execute(
                "UPDATE preset_factors SET ic_mean = ?, rank_ic = ?, ic_ir = ?, "
                "ic_std = ?, annualized_return = ?, maximum_drawdown = ?, "
                "sharpe_ratio = ?, turnover_rate = NULL, start_date = ?, data_date = ?, "
                "metric_source = 'local_recalc', metric_sample_json = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (
                    m["ic_mean"],
                    m["rank_ic"],
                    m["ic_ir"],
                    m["ic_std"],
                    m.get("annualized_return"),
                    m.get("maximum_drawdown"),
                    m.get("sharpe_ratio"),
                    str(return_data.index[0])[:10],
                    str(return_data.index[-1])[:10],
                    json.dumps(sample_meta, ensure_ascii=False),
                    factor_id,
                ),
            )
            await db.commit()
            try:
                from backend.services.provenance import record_provenance

                await record_provenance(
                    kind="factor",
                    entity_id=str(factor_id),
                    entity_name=res.get("factor_name", ""),
                    params={"action": "batch_scan", "formula": res.get("formula", "")},
                    metrics=m,
                    notes=f"批量扫描写入（覆盖更新），耗时 {res.get('elapsed_ms', 0)}ms",
                    source="scan",
                )
            except Exception:
                pass
        finally:
            await db.close()

    # ── 样本外验证（walk-forward）（P5）─────────────────────

    def _window_ic_metrics(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        period: int,
        i0: int,
        i1: int,
        mask: pd.DataFrame | None = None,
    ) -> dict:
        """窗口内 IC 指标（与 ic_analysis 同口径：T 日因子 vs T→T+p 前向累计收益）"""
        dates = factor_data.index[i0:i1]
        ics, rics = [], []
        for i in range(len(dates) - period):
            f = factor_data.loc[dates[i]].dropna()
            fwd = return_data.loc[dates[i + 1]:dates[i + period]]
            comp = ((1.0 + fwd).prod(min_count=1) - 1.0).dropna()
            common = f.index.intersection(comp.index)
            if mask is not None and dates[i] in mask.index:
                mrow = mask.loc[dates[i]]
                tradable = mrow[mrow.fillna(0).astype(float) > 0]
                common = common.intersection(tradable.index)
            if len(common) < 10:
                continue
            ics.append(f[common].corr(comp[common]))
            rics.append(f[common].rank().corr(comp[common].rank()))
        n = len(ics)
        arr = np.array(ics) if ics else np.array([])
        rarr = np.array(rics) if rics else np.array([])
        ic_mean = float(arr.mean()) if arr.size else 0.0
        ic_std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
        t_stat = ic_mean / (ic_std / np.sqrt(arr.size)) if ic_std > 0 and arr.size else 0.0
        return {
            "ic_mean": ic_mean,
            "rank_ic_mean": float(rarr.mean()) if rarr.size else 0.0,
            "ic_ir": ic_mean / ic_std if ic_std > 0 else 0.0,
            "t_stat": float(t_stat),
            "positive_ratio": float(sum(1 for x in ics if x > 0) / n) if n else 0.0,
            "n_cross_sections": n,
        }

    def _window_long_short(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        i0: int,
        i1: int,
        n_groups: int = 5,
        mask: pd.DataFrame | None = None,
    ) -> tuple[float, float]:
        """窗口内多空累计收益与日均多空收益（T 日分组 → T+1 日收益，无前视）"""
        dates = factor_data.index[i0:i1]
        spread = []
        for i in range(len(dates) - 1):
            f = factor_data.loc[dates[i]].dropna()
            nxt = dates[i + 1]
            if nxt not in return_data.index:
                continue
            r = return_data.loc[nxt].dropna()
            common = f.index.intersection(r.index)
            if mask is not None and dates[i] in mask.index:
                mrow = mask.loc[dates[i]]
                tradable = mrow[mrow.fillna(0).astype(float) > 0]
                common = common.intersection(tradable.index)
            if len(common) < n_groups * 2:
                continue
            try:
                groups = pd.qcut(f[common], q=n_groups, labels=False, duplicates="drop")
            except Exception:
                continue
            top = common[groups == n_groups - 1]
            bot = common[groups == 0]
            if len(top) and len(bot):
                spread.append(float(r[top].mean() - r[bot].mean()))
        if not spread:
            return 0.0, 0.0
        cum = float(np.prod([1 + s for s in spread]) - 1)
        return cum, float(np.mean(spread))

    def walk_forward_validation(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        train_days: int = 252,
        test_days: int = 63,
        n_splits: int = 3,
        period: int = 1,
        n_groups: int = 5,
        mask: pd.DataFrame | None = None,
    ) -> dict:
        """因子样本外（walk-forward）验证：滚动锚定分割，防过拟合

        每折：训练窗口 [0, t) 估 in-sample IC；测试窗口 [t, t+test) 估
        out-of-sample IC 与分层多空收益；窗口逐折后移（扩张式，无前视）。

        Returns:
            folds 明细 + aggregate（OOS IC 均值/t 值/同向一致性/多空累计/衰减）
        """
        factor_data = factor_data.dropna(how="all")
        dates = factor_data.index
        n_total = len(dates)
        if n_total < train_days + test_days:
            return {
                "ok": False,
                "message": f"样本不足：需至少 {train_days + test_days} 个交易日，当前 {n_total}",
            }

        folds = []
        oos_ics: list[float] = []
        oos_ls: list[float] = []
        t_end = train_days
        k = 0
        while t_end + test_days <= n_total and k < n_splits:
            t0, t1 = t_end, t_end + test_days
            ins = self._window_ic_metrics(factor_data, return_data, period, 0, t0, mask)
            oos = self._window_ic_metrics(factor_data, return_data, period, t0, t1, mask)
            ls_cum, ls_mean = self._window_long_short(
                factor_data, return_data, t0, t1, n_groups, mask
            )
            folds.append(
                {
                    "fold": k + 1,
                    "train_end": str(dates[t0 - 1])[:10],
                    "test_start": str(dates[t0])[:10],
                    "test_end": str(dates[t1 - 1])[:10],
                    "in_sample": ins,
                    "out_of_sample": oos,
                    "long_short_cum": round(ls_cum, 4),
                    "long_short_mean_daily": round(ls_mean, 6),
                }
            )
            oos_ics.append(oos["ic_mean"])
            oos_ls.append(ls_cum)
            t_end = t1
            k += 1

        if not folds:
            return {"ok": False, "message": "分割后无有效测试窗口"}

        # 同向一致性：in-sample 与 OOS 的 IC 符号一致比例
        sign_hits = sum(
            1 for fd in folds if fd["in_sample"]["ic_mean"] * fd["out_of_sample"]["ic_mean"] > 0
        )
        oos_arr = np.array(oos_ics)
        oos_mean = float(oos_arr.mean())
        oos_std = float(oos_arr.std(ddof=1)) if oos_arr.size > 1 else 0.0
        oos_t = oos_mean / (oos_std / np.sqrt(oos_arr.size)) if oos_std > 0 else 0.0

        # 全部测试区间的 IC 衰减（同口径 T→T+p 复利收益）
        test_end_final = t_end
        decay = []
        for p in [1, 5, 10, 20]:
            w = self._window_ic_metrics(
                factor_data, return_data, p, train_days, test_end_final, mask
            )
            decay.append({"period": p, "ic": round(w["ic_mean"], 4)})

        aggregate = {
            "oos_ic_mean": round(oos_mean, 4),
            "oos_ic_tstat": round(oos_t, 4),
            "oos_ic_ir": round(oos_mean / oos_std, 4) if oos_std > 0 else 0.0,
            "oos_sign_consistency": round(sign_hits / len(folds), 4),
            "oos_long_short_total": round(float(np.prod([1 + x for x in oos_ls]) - 1), 4),
            "oos_long_short_mean_fold": round(float(np.mean(oos_ls)), 4),
            "ic_decay_oos": decay,
        }
        return {
            "ok": True,
            "train_days": train_days,
            "test_days": test_days,
            "n_splits": len(folds),
            "period": period,
            "n_groups": n_groups,
            "folds": folds,
            "aggregate": aggregate,
        }

    # ── 因子生命周期 / 拥挤度（P2）──────────────────────────

    async def factor_health(
        self,
        category_code: str | None = None,
        min_snapshots: int = 2,
    ) -> list[dict]:
        """因子体检：基于 IC 历史快照判断生命周期阶段与 IC 趋势

        阶段判定（快照 ≥ min_snapshots 时）：
          失效: |最近 IC| < 0.01；  衰减: 最近 IC 显著低于历史均值；
          萌芽: 最近 IC 显著高于历史均值；  稳定: 其余且 |IC| ≥ 0.02；  观察: 其余。
        """
        db = await get_db()
        try:
            await self._ensure_history_table(db)
            where, params = "", []
            if category_code:
                where = " WHERE category_code = ?"
                params.append(category_code)
            cursor = await db.execute(
                f"SELECT id, factor_name, category_name, category_code, ic_mean, "
                f"rank_ic, data_date FROM preset_factors{where} ORDER BY id",
                params,
            )
            factors = [dict(r) for r in await cursor.fetchall()]

            cursor = await db.execute(
                "SELECT factor_id, ic_mean, ic_std, ic_ir, data_date, snapshot_at "
                "FROM preset_factor_ic_history ORDER BY factor_id, snapshot_at ASC"
            )
            hist: dict[int, list[dict]] = {}
            for r in await cursor.fetchall():
                hist.setdefault(r["factor_id"], []).append(dict(r))
        finally:
            await db.close()

        out: list[dict] = []
        for f in factors:
            snaps = [s for s in hist.get(f["id"], []) if s.get("ic_mean") is not None]
            item = {
                "factor_id": f["id"],
                "factor_name": f["factor_name"],
                "category_name": f["category_name"],
                "category_code": f["category_code"],
                "latest_ic_mean": f.get("ic_mean") or 0.0,
                "latest_rank_ic": f.get("rank_ic") or 0.0,
                "data_date": f.get("data_date"),
                "n_snapshots": len(snaps),
            }
            if len(snaps) < min_snapshots:
                item["stage"] = "样本不足"
                item["ic_trend"] = 0.0
                item["trend_label"] = "—"
                out.append(item)
                continue
            hist_ics = [s["ic_mean"] for s in snaps]
            hist_mean = float(np.mean(hist_ics))
            hist_std = float(np.std(hist_ics, ddof=1)) if len(hist_ics) > 1 else 0.0
            recent = hist_ics[-min(6, len(hist_ics)):]
            recent_mean = float(np.mean(recent))
            recent_last = float(hist_ics[-1])
            hist_var = max(hist_std * 0.5, 0.005)
            trend = recent_mean - hist_mean
            if abs(recent_last) < 0.01:
                stage = "失效"
            elif trend <= -hist_var and (abs(hist_mean) >= 0.03 or abs(recent_last) < 0.02):
                stage = "衰减"
            elif trend >= hist_var and abs(recent_last) >= 0.02:
                stage = "萌芽"
            elif abs(recent_last) >= 0.02:
                stage = "稳定"
            else:
                stage = "观察"
            item.update(
                {
                    "stage": stage,
                    "ic_trend": round(trend, 4),
                    "trend_label": "↑" if trend > 0 else ("↓" if trend < 0 else "→"),
                    "hist_ic_mean": round(hist_mean, 4),
                    "recent_ic_mean": round(recent_mean, 4),
                    "last_snapshot_at": snaps[-1].get("snapshot_at"),
                }
            )
            out.append(item)
        return out

    async def pool_crowding(self) -> dict:
        """因子池拥挤度：池内因子两两截面相关（均值 |ρ| 越高越拥挤）

        依赖本地行情面板；结果按 data_date 内存缓存（TTL 6h），避免重复计算。
        """
        import time as _time

        global _CROWDING_CACHE
        now = _time.time()
        if (
            _CROWDING_CACHE["data_date"]
            and now - _CROWDING_CACHE["ts"] < 6 * 3600
        ):
            return _CROWDING_CACHE["payload"]

        pool = await self.get_pool()
        formulas = []
        for f in pool:
            formula = extract_formula(f.get("description"))
            if formula:
                formulas.append({"factor_id": f["id"], "factor_name": f["factor_name"], "formula": formula})
        if len(formulas) < 2:
            payload = {"ok": False, "message": "因子池不足 2 个公式型因子，无法计算拥挤度",
                       "avg_abs_corr": 0.0, "pairs": []}
            _CROWDING_CACHE.update({"ts": now, "data_date": "", "payload": payload})
            return payload

        res = self.eval_formula_on_local(formulas[0]["formula"])
        if not res.get("ok"):
            payload = {"ok": False, "message": res.get("message", ""),
                       "avg_abs_corr": 0.0, "pairs": []}
            _CROWDING_CACHE.update({"ts": now, "data_date": "", "payload": payload})
            return payload
        factor_df = res["factor_df"]
        return_data = res["return_data"]
        mask = res.get("mask")
        dates = factor_df.index
        from backend.services import reference_data
        from backend.services.factor_operators import build_operator_namespace

        ns = build_operator_namespace(
            res["panels"], industry_map=reference_data.load_industry_map()
        )
        factors: dict[str, pd.DataFrame] = {formulas[0]["factor_name"]: factor_df}
        for item in formulas[1:]:
            try:
                fd = eval(item["formula"], {"__builtins__": {}}, ns)  # noqa: S307
                if isinstance(fd, pd.Series):
                    fd = fd.to_frame()
                if isinstance(fd, pd.DataFrame) and not fd.empty:
                    factors[item["factor_name"]] = fd.reindex(index=dates)
            except Exception:
                continue
        if len(factors) < 2:
            payload = {"ok": False, "message": "池内可求值因子不足 2 个", "avg_abs_corr": 0.0, "pairs": []}
            _CROWDING_CACHE.update({"ts": now, "data_date": "", "payload": payload})
            return payload
        corr = self.factor_correlation(factors)
        names = list(factors.keys())
        pairs, acc = [], []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                v = corr["matrix"][names[i]][names[j]]
                acc.append(abs(float(v)))
                pairs.append({"factor_a": names[i], "factor_b": names[j], "corr": round(float(v), 4)})
        pairs.sort(key=lambda p: abs(p["corr"]), reverse=True)
        payload = {
            "ok": True,
            "n_factors": len(names),
            "avg_abs_corr": round(float(np.mean(acc)), 4) if acc else 0.0,
            "max_abs_corr": round(float(max(acc)), 4) if acc else 0.0,
            "pairs": pairs[:30],
            "data_date": res["data_date"],
        }
        _CROWDING_CACHE.update({"ts": now, "data_date": res["data_date"], "payload": payload})
        return payload


# 因子池拥挤度缓存（按 data_date + TTL 6h）
_CROWDING_CACHE: dict = {"ts": 0.0, "data_date": "", "payload": {}}


def _sse(event_type: str, data: dict) -> str:
    """SSE 事件格式化（与批量下载服务同风格）"""
    import json
    from datetime import datetime

    data.setdefault("timestamp", datetime.now().isoformat())
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


# 全局单例
factor_research = FactorResearchService()
