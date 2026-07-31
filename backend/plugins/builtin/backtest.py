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
    volume: dict = {}  # 可选成交量面板（用于停牌推断）
    high: dict = {}  # 可选最高价面板（用于一字板判定）
    low: dict = {}  # 可选最低价面板（用于一字板判定）
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0008  # 默认佣金率（与官网一致）
    slippage: float = 0.0
    stamp_tax: float = 0.0005  # 卖出印花税
    normalize: str = "long_only"  # 权重归一方式
    frequency: str = "1d"  # 回测频率


@ui(
    signals={"input_type": "None"},
    prices={"input_type": "None"},
    benchmark={"input_type": "None"},
    volume={"input_type": "None"},
    high={"input_type": "None"},
    low={"input_type": "None"},
    initial_capital={"input_type": "number_field"},
    commission_rate={"input_type": "number_field"},
    slippage={"input_type": "number_field"},
    stamp_tax={"input_type": "number_field"},
    normalize={
        "input_type": "combobox",
        "options": ["long_only", "dollar_neutral", "none"],
    },
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
    assumptions: list = []  # 未能处理的假设清单（停牌/涨跌停等）
    report: dict = {}  # 回测综合报告（供工作流内弹窗可视化，与因子分析同构）
    initial_capital: float = 0.0


@work_node(
    name="回测",
    group="08-回测",
    box_color="red",
    description="基于信号与价格面板执行向量化回测，输出净值/回撤曲线与完整绩效指标（年化收益/波动/夏普/索提诺/卡玛/最大回撤/VaR/胜率/盈亏比/月度收益）",
    example="因子构建（信号） + QMT行情数据（价格） → 回测 → 输出",
    notes=[
        "signals / prices 均需连线提供（面板：index=日期, columns=股票）；benchmark 为可选基准收盘序列",
        "volume/high/low 为可选连线：提供后启用停牌冻结与一字板不可成交处理，未提供时不处理并在 assumptions 中明示",
        "normalize 默认 long_only（正信号按日归一 Σw=1，避免信号值直接作权重的隐性杠杆），可选 dollar_neutral / none",
        "佣金率默认 0.0008，滑点默认 0，卖出印花税默认 0.0005；T 日信号 T+1 执行；指标按 252 交易日年化",
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

        volume = pd.DataFrame(input.volume) if input.volume else None
        high = pd.DataFrame(input.high) if input.high else None
        low = pd.DataFrame(input.low) if input.low else None

        for df in (signals, prices, volume, high, low):
            if df is None:
                continue
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass

        # 参考面板：停牌掩码（需 volume）与涨跌停近似价（需参考数据快照）
        from backend.services import market_data

        reference = market_data.load_reference_panels(close=prices, volume=volume)

        result = backtest_analysis.run_backtest(
            signals=signals,
            prices=prices,
            initial_capital=input.initial_capital,
            commission_rate=input.commission_rate,
            slippage=input.slippage,
            stamp_tax=input.stamp_tax,
            normalize=input.normalize,
            tradable_mask=reference["tradable_mask"],
            up_limit=reference["up_limit"],
            down_limit=reference["down_limit"],
            high=high,
            low=low,
        )
        assumptions = result["assumptions"]
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

        equity_map = {str(k): float(v) for k, v in equity_curve.items()}
        # 净值归一（起点=1）供图表与基准同尺度对比
        init_cap = float(result["initial_capital"]) or 1.0
        nav_map = {k: v / init_cap for k, v in equity_map.items()}

        # 回测综合报告（与因子分析综合报告同构，供工作流内弹窗展示）
        report = {
            "summary": metrics,
            "nav_curve": nav_map,
            "benchmark_curve": benchmark_curve,
            "drawdown_curve": drawdown_curve,
            "monthly_returns": monthly_returns,
            "top_drawdowns": dd.get("top_drawdowns", []),
            "benchmark": metrics.get("benchmark"),
            "assumptions": assumptions,
            "initial_capital": init_cap,
            "trading_days": metrics.get("trading_days", 0),
        }

        return BacktestOutput(
            equity_curve=equity_map,
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
            assumptions=assumptions,
            report=report,
            initial_capital=result["initial_capital"],
        )
