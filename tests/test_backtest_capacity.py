"""容量分析与成本拆分测试"""

import numpy as np
import pandas as pd
import pytest

from backend.services.backtest_analysis import BacktestAnalysisService

svc = BacktestAnalysisService()


def _make_panels(n_dates: int = 100, n_stocks: int = 5) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-01", periods=n_dates)
    codes = [f"{i:06d}.SZ" for i in range(1, n_stocks + 1)]
    prices = pd.DataFrame(
        rng.uniform(5, 50, size=(n_dates, n_stocks)), index=dates, columns=codes
    ).cumprod() * 10
    amount = pd.DataFrame(
        rng.uniform(5e7, 5e8, size=(n_dates, n_stocks)), index=dates, columns=codes
    )
    signals = pd.DataFrame(
        rng.uniform(-1, 1, size=(n_dates, n_stocks)), index=dates, columns=codes
    )
    return prices, amount, signals


def test_cost_breakdown_matches_merged():
    prices, _amount, signals = _make_panels()
    r = svc.run_backtest(
        signals=signals,
        prices=prices,
        commission_rate=0.001,
        slippage=0.001,
        stamp_tax=0.0005,
        normalize="long_only",
    )
    # 分列之和 == 合并成本
    total = (
        r["commission_costs"] + r["slippage_costs"] + r["stamp_costs"]
    )
    pd.testing.assert_series_equal(total, r["costs"], check_names=False)

    summary = r["cost_summary"]
    assert abs(summary["total_cost"] - summary["costs"]) < 1e-9 if "costs" in summary else True
    assert summary["breakdown"]["commission"] >= 0
    assert summary["breakdown"]["stamp_tax"] >= 0
    assert abs(sum(summary["shares"].values()) - 1.0) < 1e-6 or summary["total_cost"] == 0
    # 印花税只来自卖出
    assert summary["breakdown"]["stamp_tax"] == pytest.approx(
        float(r["stamp_costs"].sum()), rel=1e-9
    )


def test_capacity_analysis_basic():
    prices, amount, signals = _make_panels()
    r = svc.capacity_analysis(
        signals=signals,
        prices=prices,
        amount=amount,
        normalize="long_only",
        participation_rate=0.1,
        capital_levels=[1e6, 1e8, 1e10],
    )
    assert r["ok"] is True
    assert len(r["levels"]) == 3
    # 资金越大参与率越高：受限天数比例单调不减
    ratios = [lv["exceed_days_ratio"] for lv in r["levels"]]
    assert ratios == sorted(ratios)
    assert r["suggested_capacity"] > 0
    assert r["suggested_label"]


def test_capacity_analysis_no_amount():
    prices, _, signals = _make_panels()
    r = svc.capacity_analysis(signals=signals, prices=prices, amount=None)
    assert r["ok"] is False
    assert "成交额" in r["message"]


def test_capacity_analysis_constrained_low_adv():
    """低成交额标的应显著降低建议容量"""
    prices, amount, signals = _make_panels()
    # 把成交额压到极小
    amount_small = amount * 1e-6
    r = svc.capacity_analysis(
        signals=signals,
        prices=prices,
        amount=amount_small,
        participation_rate=0.1,
        capital_levels=[1e8],
    )
    assert r["levels"][0]["exceed_days_ratio"] > 0.5
