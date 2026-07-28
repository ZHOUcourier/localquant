"""回测相关内置工作流节点"""
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
    prices: dict   # DataFrame dict: {col: {index: value}}
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.001


@ui(
    signals={"input_type": "None"},
    prices={"input_type": "None"},
    initial_capital={"input_type": "number_field"},
    commission_rate={"input_type": "number_field"},
)
class BacktestInputUI(BacktestInput):
    pass


class BacktestOutput(BaseModel):
    """回测输出"""
    equity_curve: dict  # {index: value}
    strategy_returns: dict  # {index: value}
    positions: dict  # {index: value}
    initial_capital: float = 0.0


@work_node(name="回测", group="05-回测", box_color="red")
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
        )

        equity_curve = result["equity_curve"]
        strategy_returns = result["strategy_returns"]
        positions = result["positions"]

        return BacktestOutput(
            equity_curve={str(k): float(v) for k, v in equity_curve.items()},
            strategy_returns={str(k): float(v) for k, v in strategy_returns.items()},
            positions={
                str(k): {c: float(v) for c, v in row.items()}
                if hasattr(row, 'items') else float(row)
                for k, row in positions.items()
            },
            initial_capital=result["initial_capital"],
        )
