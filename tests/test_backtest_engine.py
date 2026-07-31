"""回测引擎已知答案回归测试

覆盖：买入持有成本口径、long_only 归一、停牌冻结、一字板不可成交、卖出印花税。
全部使用手工构造的小面板，不依赖 QMT。
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.backtest_analysis import BacktestAnalysisService

svc = BacktestAnalysisService()


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-02", periods=n)


def test_buy_and_hold_known_answer():
    """单票满仓买入持有 = 价格收益 − 一次买入成本"""
    idx = _dates(3)
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=idx)
    signals = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx)

    result = svc.run_backtest(
        signals, prices, commission_rate=0.001, slippage=0.0, stamp_tax=0.0
    )
    r = result["strategy_returns"]
    # day0: 无持仓；day1: 建仓（成本 0.001）+ 收益 10%；day2: 持有收益 10%
    assert r.iloc[0] == pytest.approx(0.0)
    assert r.iloc[1] == pytest.approx(0.10 - 0.001)
    assert r.iloc[2] == pytest.approx(0.10)
    expected_equity = 1_000_000 * (1 + r.iloc[1]) * (1 + r.iloc[2])
    assert result["equity_curve"].iloc[-1] == pytest.approx(expected_equity)


def test_sell_pays_stamp_tax():
    """卖出成本 = 佣金 + 滑点 + 印花税；买入不含印花税"""
    idx = _dates(4)
    prices = pd.DataFrame({"A": [100.0] * 4}, index=idx)  # 价格不动，只看成本
    signals = pd.DataFrame({"A": [1.0, 0.0, 0.0, 0.0]}, index=idx)

    result = svc.run_backtest(
        signals, prices, commission_rate=0.001, slippage=0.0005, stamp_tax=0.0005
    )
    r = result["strategy_returns"]
    # day1 买入 1.0：成本 = 1×(0.001+0.0005)
    assert r.iloc[1] == pytest.approx(-(0.001 + 0.0005))
    # day2 卖出 1.0：成本 = 1×(0.001+0.0005+0.0005)
    assert r.iloc[2] == pytest.approx(-(0.001 + 0.0005 + 0.0005))


def test_long_only_normalization_removes_leverage():
    """long_only：信号值再大也按日归一 Σw=1"""
    idx = _dates(3)
    prices = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0], "B": [50.0, 55.0, 60.5]}, index=idx
    )
    signals = pd.DataFrame({"A": [8.0, 8.0, 8.0], "B": [2.0, 2.0, 2.0]}, index=idx)

    result = svc.run_backtest(
        signals,
        prices,
        commission_rate=0.0,
        slippage=0.0,
        stamp_tax=0.0,
        normalize="long_only",
    )
    pos = result["positions"]
    assert pos.iloc[1].sum() == pytest.approx(1.0)
    assert pos.iloc[1]["A"] == pytest.approx(0.8)
    # 两票日收益均 10% → 组合日收益应为 10%（无杠杆）
    assert result["strategy_returns"].iloc[1] == pytest.approx(0.10)


def test_suspension_freezes_position():
    """停牌日冻结持仓：不调仓、不计成本"""
    idx = _dates(4)
    prices = pd.DataFrame({"A": [100.0, 100.0, 100.0, 100.0]}, index=idx)
    # day1 建仓；day2 想清仓但停牌 → 冻结；day3 复牌卖出
    signals = pd.DataFrame({"A": [1.0, 0.0, 0.0, 0.0]}, index=idx)
    tradable = pd.DataFrame({"A": [True, True, False, True]}, index=idx)

    result = svc.run_backtest(
        signals,
        prices,
        commission_rate=0.001,
        slippage=0.0,
        stamp_tax=0.0,
        tradable_mask=tradable,
    )
    pos = result["positions"]
    assert pos.iloc[2]["A"] == pytest.approx(1.0)  # 停牌日冻结在 1.0
    assert result["strategy_returns"].iloc[2] == pytest.approx(0.0)  # 无成本
    assert pos.iloc[3]["A"] == pytest.approx(0.0)  # 复牌后卖出
    assert result["strategy_returns"].iloc[3] == pytest.approx(-0.001)


def test_limit_up_board_blocks_buy():
    """一字涨停日买入意图被顺延，非一字日照常成交"""
    idx = _dates(4)
    close = pd.DataFrame({"A": [100.0, 110.0, 121.0, 133.1]}, index=idx)
    # day1 为一字涨停（high==low==close 且 close 触及涨停价）
    high = pd.DataFrame({"A": [100.0, 110.0, 122.0, 134.0]}, index=idx)
    low = pd.DataFrame({"A": [100.0, 110.0, 120.0, 132.0]}, index=idx)
    up_limit = close.shift(1) * 1.10
    down_limit = close.shift(1) * 0.90
    signals = pd.DataFrame({"A": [1.0, 1.0, 1.0, 1.0]}, index=idx)

    result = svc.run_backtest(
        signals,
        close,
        commission_rate=0.0,
        slippage=0.0,
        stamp_tax=0.0,
        up_limit=up_limit,
        down_limit=down_limit,
        high=high,
        low=low,
    )
    pos = result["positions"]
    assert pos.iloc[1]["A"] == pytest.approx(0.0)  # 一字涨停买不进
    assert pos.iloc[2]["A"] == pytest.approx(1.0)  # 次日非一字，成交


def test_assumptions_reported_when_reference_missing():
    """无参考数据时明确报告假设，而不是静默假装处理过"""
    idx = _dates(3)
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=idx)
    signals = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx)

    result = svc.run_backtest(signals, prices)
    joined = "；".join(result["assumptions"])
    assert "停牌" in joined
    assert "一字板" in joined
    assert "杠杆" in joined  # normalize=none 的提示


def test_dollar_neutral_gross_exposure():
    """dollar_neutral：多空各 0.5，净暴露 0"""
    idx = _dates(3)
    prices = pd.DataFrame(
        {"A": [100.0, 101.0, 102.0], "B": [100.0, 99.0, 98.0]}, index=idx
    )
    signals = pd.DataFrame({"A": [3.0, 3.0, 3.0], "B": [-1.0, -1.0, -1.0]}, index=idx)

    result = svc.run_backtest(
        signals,
        prices,
        commission_rate=0.0,
        slippage=0.0,
        stamp_tax=0.0,
        normalize="dollar_neutral",
    )
    pos = result["positions"].iloc[1]
    assert pos["A"] == pytest.approx(0.5)
    assert pos["B"] == pytest.approx(-0.5)
    assert np.isclose(pos.sum(), 0.0)
