"""因子研究服务 — 提供 IC 分析、分层收益、中性化、相关性等功能"""
import pandas as pd
import numpy as np
from typing import Optional
from loguru import logger


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
            return_data: 收益率 DataFrame (index=date, columns=stocks)
            periods: 分析周期列表

        Returns:
            IC 时序、IC 均值、IC_IR、RankIC 等
        """
        periods = periods or [1, 5, 10, 20]
        results = {}

        for period in periods:
            ic_series = []
            rank_ic_series = []
            dates = factor_data.index

            for i in range(len(dates) - period):
                date = dates[i]
                future_date = dates[i + period] if i + period < len(dates) else None
                if future_date is None:
                    break

                factor_values = factor_data.loc[date].dropna()
                future_returns = return_data.loc[future_date].dropna()

                common = factor_values.index.intersection(future_returns.index)
                if len(common) < 10:
                    continue

                f = factor_values[common]
                r = future_returns[common]

                ic = f.corr(r)
                ic_series.append({"date": str(date), "ic": ic})

                rank_ic = f.rank().corr(r.rank())
                rank_ic_series.append({"date": str(date), "rank_ic": rank_ic})

            ic_values = [x["ic"] for x in ic_series if x["ic"] is not None and not np.isnan(x["ic"])]
            rank_ic_values = [x["rank_ic"] for x in rank_ic_series if x["rank_ic"] is not None and not np.isnan(x["rank_ic"])]

            results[f"period_{period}"] = {
                "ic_series": ic_series,
                "rank_ic_series": rank_ic_series,
                "ic_mean": float(np.mean(ic_values)) if ic_values else 0,
                "ic_std": float(np.std(ic_values)) if ic_values else 0,
                "ic_ir": float(np.mean(ic_values) / np.std(ic_values)) if ic_values and np.std(ic_values) > 0 else 0,
                "rank_ic_mean": float(np.mean(rank_ic_values)) if rank_ic_values else 0,
                "rank_ic_ir": float(np.mean(rank_ic_values) / np.std(rank_ic_values)) if rank_ic_values and np.std(rank_ic_values) > 0 else 0,
                "ic_positive_ratio": float(sum(1 for x in ic_values if x > 0) / len(ic_values)) if ic_values else 0,
            }

        return results

    def quantile_analysis(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        n_groups: int = 5,
    ) -> dict:
        """分层收益分析"""
        group_returns = {f"group_{i+1}": [] for i in range(n_groups)}
        dates = factor_data.index

        for date in dates:
            factor_values = factor_data.loc[date].dropna()
            returns = return_data.loc[date].dropna() if date in return_data.index else pd.Series(dtype=float)

            common = factor_values.index.intersection(returns.index)
            if len(common) < n_groups * 2:
                continue

            f = factor_values[common]
            r = returns[common]

            groups = pd.qcut(f, q=n_groups, labels=False, duplicates='drop')
            for g in range(n_groups):
                mask = groups == g
                if mask.sum() > 0:
                    group_returns[f"group_{g+1}"].append({
                        "date": str(date),
                        "return": float(r[mask].mean()),
                        "count": int(mask.sum()),
                    })

        cumulative = {}
        for key, values in group_returns.items():
            if values:
                rets = [v["return"] for v in values]
                cumulative[key] = float(np.prod([1 + r for r in rets]) - 1)

        return {
            "group_returns": group_returns,
            "cumulative_returns": cumulative,
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
            "avg_turnover": float(np.mean([t["turnover"] for t in turnovers])) if turnovers else 0,
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

            common = factor_values.index.intersection(industry.dropna().index).intersection(market_cap.dropna().index)
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

    def factor_decay(self, factor_data: pd.DataFrame, return_data: pd.DataFrame, max_period: int = 30) -> dict:
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
    ) -> pd.DataFrame:
        """多因子合成"""
        factor_names = list(factors.keys())

        if weights is None:
            if method == "equal":
                weights = {name: 1.0 / len(factor_names) for name in factor_names}
            elif method == "ic_weighted":
                weights = {name: 1.0 / len(factor_names) for name in factor_names}

        standardized = {}
        for name, df in factors.items():
            standardized[name] = df.div(df.std(axis=1), axis=0) * weights.get(name, 0)

        combined = sum(standardized.values())
        return combined


# 全局单例
factor_research = FactorResearchService()
