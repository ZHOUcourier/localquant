"""回测相关内置工作流节点"""

import numpy as np
import pandas as pd
from pydantic import BaseModel

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui
from backend.services.backtest_analysis import backtest_analysis

# ────────────────────────────────────────────────────────────
# 1. 回测节点
# ────────────────────────────────────────────────────────────


class BacktestInput(BaseModel):
    """回测输入"""

    signals: dict  # DataFrame dict: {col: {index: value}}
    prices: dict  # DataFrame dict: {col: {index: value}}
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.001
    slippage: float = 0.001


@ui(
    signals={"input_type": "None"},
    prices={"input_type": "None"},
    initial_capital={"input_type": "number_field"},
    commission_rate={"input_type": "number_field"},
    slippage={"input_type": "number_field"},
)
class BacktestInputUI(BacktestInput):
    pass


class BacktestOutput(BaseModel):
    """回测输出"""

    equity_curve: dict  # {index: value}
    strategy_returns: dict  # {index: value}
    positions: dict  # {index: value}
    metrics: dict = {}  # 绩效指标: 总收益/年化/波动/夏普/最大回撤
    initial_capital: float = 0.0


@work_node(
    name="回测",
    group="05-回测",
    box_color="red",
    description="执行策略回测，模拟交易并生成绩效报告",
)
class BacktestNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return BacktestInputUI

    @classmethod
    def output_model(cls):
        return BacktestOutput

    def run(self, input: BacktestInputUI) -> BacktestOutput:
        signals = pd.DataFrame(input.signals)
        prices = pd.DataFrame(input.prices)

        # 尝试将 index 转为 datetime
        for df in (signals, prices):
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass

        result = backtest_analysis.run_backtest(
            signals=signals,
            prices=prices,
            initial_capital=input.initial_capital,
            commission_rate=input.commission_rate,
            slippage=input.slippage,
        )

        equity_curve = result["equity_curve"]
        strategy_returns = result["strategy_returns"]
        positions = result["positions"]

        # 绩效指标
        ret_series = pd.Series(strategy_returns)
        metrics: dict = {}
        if len(ret_series) > 1:
            metrics["total_return"] = float((1 + ret_series).prod() - 1)
            metrics["annual_return"] = float(ret_series.mean() * 252)
            metrics["annual_volatility"] = float(ret_series.std() * np.sqrt(252))
            metrics["sharpe_ratio"] = (
                float(metrics["annual_return"] / metrics["annual_volatility"])
                if metrics["annual_volatility"] != 0
                else 0.0
            )
            cum_nav = (1 + ret_series).cumprod()
            metrics["max_drawdown"] = float((cum_nav / cum_nav.cummax() - 1).min())

        return BacktestOutput(
            equity_curve={str(k): float(v) for k, v in equity_curve.items()},
            strategy_returns={str(k): float(v) for k, v in strategy_returns.items()},
            positions={
                str(k): {c: float(v) for c, v in row.items()}
                if hasattr(row, "items")
                else float(row)
                for k, row in positions.items()
            },
            metrics=metrics,
            initial_capital=result["initial_capital"],
        )
