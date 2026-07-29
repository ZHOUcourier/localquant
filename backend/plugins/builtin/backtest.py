"""回测相关内置工作流节点"""

import pandas as pd
from pydantic import BaseModel, ConfigDict

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui
from backend.services.backtest_analysis import backtest_analysis

# ────────────────────────────────────────────────────────────
# 1. 回测节点
# ────────────────────────────────────────────────────────────


class BacktestInput(BaseModel):
    """回测输入"""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    signals: dict = {}  # 信号面板 dict: {col: {index: value}}
    prices: dict = {}  # 价格面板 dict: {col: {index: value}}
    benchmark: dict = {}  # 可选基准收益/收盘序列 {index: value}
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0008  # 默认佣金率（与官网一致）
    slippage: float = 0.0
    frequency: str = "1d"  # 回测频率


@ui(
    signals={"input_type": "None"},
    prices={"input_type": "None"},
    benchmark={"input_type": "None"},
    initial_capital={"input_type": "number_field"},
    commission_rate={"input_type": "number_field"},
    slippage={"input_type": "number_field"},
    frequency={"input_type": "combobox", "options": ["1d", "1w", "1mon"]},
)
class BacktestInputUI(BacktestInput):
    pass


class BacktestOutput(BaseModel):
    """回测输出"""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    equity_curve: dict = {}  # {index: value}
    strategy_returns: dict = {}  # {index: value}
    drawdown_curve: dict = {}  # {index: value} 回撤曲线
    positions: dict = {}  # {index: value}
    metrics: dict = {}  # 完整绩效指标
    monthly_returns: dict = {}  # 月度收益
    benchmark_curve: dict = {}  # 基准净值曲线（如提供基准）
    initial_capital: float = 0.0


@work_node(
    name="回测",
    group="08-回测",
    box_color="red",
    description="基于信号与价格面板执行向量化回测，输出净值/回撤曲线与完整绩效指标（年化收益/波动/夏普/索提诺/卡玛/最大回撤/VaR/胜率/盈亏比/月度收益）",
    example="因子构建（信号） + QMT行情数据（价格） → 回测 → 输出",
    notes=[
        "signals / prices 均需连线提供（面板：index=日期, columns=股票）；benchmark 为可选基准收盘序列",
        "佣金率默认 0.0008，滑点默认 0；T 日信号 T+1 执行；指标按 252 交易日年化",
        "提供 benchmark 时额外输出跟踪误差/信息比率等相对基准指标",
    ],
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
        if signals.empty or prices.empty:
            raise ValueError("回测：需要连线提供 signals（信号）与 prices（价格）面板")

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
        strategy_returns = pd.Series(result["strategy_returns"])
        positions = result["positions"]

        # 基准收益（可选）：benchmark 为收盘序列则转收益率，否则当作收益率
        benchmark_returns = None
        benchmark_curve: dict = {}
        if input.benchmark:
            bm = pd.Series(input.benchmark)
            try:
                bm.index = pd.to_datetime(bm.index)
            except Exception:
                pass
            bm = bm.sort_index().astype(float)
            # 启发式：值普遍 > 1 视为价格，转收益率；否则视为收益率
            benchmark_returns = (
                bm.pct_change().fillna(0.0) if bm.abs().mean() > 1 else bm
            )
            bm_nav = (1 + benchmark_returns).cumprod()
            benchmark_curve = {str(k): float(v) for k, v in bm_nav.items()}

        # 完整绩效指标 + 回撤曲线（复用 backtest_analysis 服务）
        metrics = backtest_analysis.performance_tear_sheet(
            strategy_returns, benchmark_returns=benchmark_returns
        )
        monthly_returns = metrics.pop("monthly_returns", {})
        dd = backtest_analysis.drawdown_analysis(strategy_returns.dropna())
        drawdown_curve = {str(k): float(v) for k, v in dd["drawdown_series"].items()}

        return BacktestOutput(
            equity_curve={str(k): float(v) for k, v in equity_curve.items()},
            strategy_returns={str(k): float(v) for k, v in strategy_returns.items()},
            drawdown_curve=drawdown_curve,
            positions={
                str(k): {c: float(v) for c, v in row.items()}
                if hasattr(row, "items")
                else float(row)
                for k, row in positions.items()
            },
            metrics=metrics,
            monthly_returns=monthly_returns,
            benchmark_curve=benchmark_curve,
            initial_capital=result["initial_capital"],
        )
