"""回测节点 report 可视化数据回归测试

验证 BacktestNode 输出的 report 结构完整（供工作流内综合报告弹窗渲染）。
不依赖 QMT——直接构造 signals/prices 面板 dict 喂给节点。
"""

import numpy as np
import pandas as pd

from backend.plugins.builtin.backtest import BacktestInputUI, BacktestNode


def _panels(n_days=90, n_stocks=5, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    codes = [f"S{i}" for i in range(n_stocks)]
    rets = rng.normal(0.0005, 0.02, size=(n_days, n_stocks))
    close = pd.DataFrame(20 * np.cumprod(1 + rets, axis=0), index=dates, columns=codes)
    # 简单动量信号：过去 5 日涨幅为正则持有
    signal = (close / close.shift(5) - 1).clip(lower=0)
    # 面板 dict：{col: {index: value}}
    to_map = lambda df: {
        c: {str(k): float(v) for k, v in df[c].items()} for c in df.columns
    }
    return to_map(signal.fillna(0.0)), to_map(close)


def test_backtest_node_emits_report():
    sig, prc = _panels()
    node = BacktestNode()
    out = node.run(BacktestInputUI(signals=sig, prices=prc, normalize="long_only"))
    assert out.report, "回测节点应产出 report"
    rep = out.report
    # 关键区块齐全
    for key in (
        "summary",
        "nav_curve",
        "drawdown_curve",
        "monthly_returns",
        "top_drawdowns",
        "assumptions",
    ):
        assert key in rep, f"report 缺少 {key}"
    # 指标含核心项
    for m in ("total_return", "annual_return", "sharpe_ratio", "max_drawdown"):
        assert m in rep["summary"]
    # 净值曲线非空、起点归一约为 1
    nav = rep["nav_curve"]
    assert len(nav) > 0
    first = nav[min(nav)]  # ISO 日期字符串最小键即最早日
    assert abs(first - 1.0) < 0.5  # 归一后起点在 1 附近


def test_backtest_report_monthly_shape():
    """月度收益为 {year: {month: ret}}，供热力图渲染"""
    sig, prc = _panels(n_days=150)
    out = BacktestNode().run(BacktestInputUI(signals=sig, prices=prc))
    monthly = out.report["monthly_returns"]
    assert isinstance(monthly, dict) and monthly
    any_year = next(iter(monthly.values()))
    assert isinstance(any_year, dict)
    # 月份键形如 "01".."12"
    assert all(len(mk) == 2 for mk in any_year)


def test_backtest_report_assumptions_present():
    """无参考数据时 report.assumptions 明示未处理项（停牌/一字板等）"""
    sig, prc = _panels()
    out = BacktestNode().run(BacktestInputUI(signals=sig, prices=prc))
    joined = "；".join(out.report["assumptions"])
    assert "停牌" in joined or "一字板" in joined
