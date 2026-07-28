"""回测分析服务"""
import numpy as np
import pandas as pd
from loguru import logger


class BacktestAnalysisService:
    """向量化回测与绩效分析服务"""

    # ── 回测引擎 ─────────────────────────────────────────────

    def run_backtest(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.001,
        slippage: float = 0.001,
    ) -> dict:
        """
        向量化回测。

        Parameters
        ----------
        signals : DataFrame
            每列为一只标的的信号值（正=做多, 负=做空, 0=空仓），index 为日期。
        prices : DataFrame
            每列为一只标的的收盘价，index 与 signals 对齐。
        """
        # 对齐
        common_idx = signals.index.intersection(prices.index)
        common_cols = signals.columns.intersection(prices.columns)
        signals = signals.loc[common_idx, common_cols]
        prices = prices.loc[common_idx, common_cols]

        # 收益率
        price_returns = prices.pct_change().fillna(0.0)

        # 信号延迟一天执行（T 日信号 → T+1 持仓）
        positions = signals.shift(1).fillna(0.0)

        # 换手 → 交易成本
        trades = positions.diff().abs().fillna(0.0)
        cost = trades * (commission_rate + slippage)

        # 策略日收益
        strategy_returns = (positions * price_returns - cost).sum(axis=1)

        # 净值曲线
        equity_curve = (1 + strategy_returns).cumprod() * initial_capital

        return {
            "strategy_returns": strategy_returns,
            "equity_curve": equity_curve,
            "positions": positions,
            "trades": trades,
            "initial_capital": initial_capital,
        }

    # ── 绩效报告 ─────────────────────────────────────────────

    def performance_tear_sheet(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series | None = None,
        risk_free_rate: float = 0.03,
    ) -> dict:
        """完整绩效指标"""
        returns = returns.dropna()
        n_days = len(returns)
        if n_days == 0:
            return {"error": "no data"}

        ann_factor = 252 / n_days

        # 基本统计
        total_return = float((1 + returns).prod() - 1)
        annual_return = float((1 + total_return) ** ann_factor - 1)
        volatility = float(returns.std() * np.sqrt(252))

        # Sharpe
        daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
        excess = returns - daily_rf
        sharpe = float(excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0.0

        # Sortino
        downside = excess[excess < 0]
        downside_std = float(downside.std() * np.sqrt(252)) if len(downside) > 0 else 1e-9
        sortino = float((annual_return - risk_free_rate) / downside_std) if downside_std > 0 else 0.0

        # 回撤 & Calmar
        dd_info = self.drawdown_analysis(returns)
        max_dd = dd_info["max_drawdown"]
        calmar = float(annual_return / abs(max_dd)) if max_dd != 0 else 0.0

        # VaR / CVaR (95%)
        var_95 = float(np.percentile(returns, 5))
        cvar_95 = float(returns[returns <= var_95].mean()) if (returns <= var_95).any() else var_95

        # 胜率 & 盈亏比
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        win_rate = float(len(wins) / n_days)
        avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
        avg_loss = float(abs(losses.mean())) if len(losses) > 0 else 1e-9
        profit_loss_ratio = float(avg_win / avg_loss) if avg_loss > 0 else 0.0

        # 月度收益
        monthly = self.monthly_returns(returns)

        result = {
            "total_return": total_return,
            "annual_return": annual_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown": max_dd,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "trading_days": n_days,
            "monthly_returns": monthly,
        }

        # 相对基准指标
        if benchmark_returns is not None:
            bm = benchmark_returns.reindex(returns.index).dropna()
            if len(bm) > 0:
                bm_total = float((1 + bm).prod() - 1)
                bm_annual = float((1 + bm_total) ** (252 / len(bm)) - 1)
                active = returns - bm
                tracking_error = float(active.std() * np.sqrt(252))
                info_ratio = float(active.mean() / active.std() * np.sqrt(252)) if active.std() > 0 else 0.0
                result["benchmark"] = {
                    "total_return": bm_total,
                    "annual_return": bm_annual,
                    "tracking_error": tracking_error,
                    "information_ratio": info_ratio,
                }

        return result

    # ── 月度收益 ─────────────────────────────────────────────

    def monthly_returns(self, returns: pd.Series) -> dict:
        """按年月组织月度收益"""
        if returns.empty:
            return {}
        grouped = returns.groupby([returns.index.year, returns.index.month])
        monthly: dict = {}
        for (year, month), group in grouped:
            ret = float((1 + group).prod() - 1)
            monthly.setdefault(str(year), {})[str(month).zfill(2)] = ret
        return monthly

    # ── 回撤分析 ─────────────────────────────────────────────

    def drawdown_analysis(self, returns: pd.Series) -> dict:
        """回撤序列 + 前 5 大回撤"""
        cum = (1 + returns).cumprod()
        running_max = cum.cummax()
        drawdown = cum / running_max - 1

        max_dd = float(drawdown.min())

        # 提取前 5 大回撤区间
        top_drawdowns = []
        dd_sorted = drawdown.sort_values()
        seen_dates: set = set()
        for date, dd_val in dd_sorted.items():
            if len(top_drawdowns) >= 5:
                break
            # 跳过已收录回撤附近（±10 天）的点
            if any(abs((date - d).days) < 10 for d in seen_dates):
                continue
            seen_dates.add(date)
            # 找回撤起点（前高）
            prior = cum.loc[:date]
            peak_date = prior.idxmax()
            # 找恢复点
            after = cum.loc[date:]
            recovery_candidates = after[after >= cum.loc[peak_date]]
            recovery_date = recovery_candidates.index[0] if len(recovery_candidates) > 0 else None
            top_drawdowns.append({
                "trough_date": str(date.date()) if hasattr(date, "date") else str(date),
                "drawdown": float(dd_val),
                "peak_date": str(peak_date.date()) if hasattr(peak_date, "date") else str(peak_date),
                "recovery_date": str(recovery_date.date()) if recovery_date is not None and hasattr(recovery_date, "date") else (str(recovery_date) if recovery_date is not None else None),
            })

        return {
            "drawdown_series": drawdown,
            "max_drawdown": max_dd,
            "top_drawdowns": top_drawdowns,
        }

    # ── 蒙特卡洛模拟 ────────────────────────────────────────

    def monte_carlo_simulation(
        self,
        returns: pd.Series,
        n_sims: int = 1000,
        n_days: int = 252,
    ) -> dict:
        """基于历史收益分布的蒙特卡洛模拟"""
        returns = returns.dropna()
        mu = float(returns.mean())
        sigma = float(returns.std())

        rng = np.random.default_rng(42)
        sim_returns = rng.normal(mu, sigma, size=(n_sims, n_days))

        # 累计净值
        cum = np.cumprod(1 + sim_returns, axis=1)
        terminal = cum[:, -1]

        # 各分位数
        percentiles = {
            "p5": float(np.percentile(terminal, 5)),
            "p25": float(np.percentile(terminal, 25)),
            "p50": float(np.percentile(terminal, 50)),
            "p75": float(np.percentile(terminal, 75)),
            "p95": float(np.percentile(terminal, 95)),
        }

        # 最大回撤分布
        running_max = np.maximum.accumulate(cum, axis=1)
        dd = cum / running_max - 1
        max_dds = dd.min(axis=1)
        max_dd_stats = {
            "mean": float(max_dds.mean()),
            "p5": float(np.percentile(max_dds, 5)),
            "worst": float(max_dds.min()),
        }

        # 路径示例（取前 20 条）
        sample_paths = cum[:20].tolist()

        return {
            "n_sims": n_sims,
            "n_days": n_days,
            "terminal_percentiles": percentiles,
            "max_drawdown_stats": max_dd_stats,
            "sample_paths": sample_paths,
            "mean_terminal": float(terminal.mean()),
            "median_terminal": float(np.median(terminal)),
        }


# 全局单例
backtest_analysis = BacktestAnalysisService()
