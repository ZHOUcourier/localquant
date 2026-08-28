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
    """T+1 收盘成交：day0 信号 → day1 收盘建仓（当日仅付成本），day2 起赚持有收益"""
    idx = _dates(3)
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=idx)
    signals = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx)

    result = svc.run_backtest(
        signals, prices, commission_rate=0.001, slippage=0.0, stamp_tax=0.0
    )
    r = result["strategy_returns"]
    # day0: 无持仓；day1: T+1 建仓日仅付买入成本；day2: 持有收益 10%
    assert r.iloc[0] == pytest.approx(0.0)
    assert r.iloc[1] == pytest.approx(-0.001)
    assert r.iloc[2] == pytest.approx(0.10)
    expected_equity = 1_000_000 * (1 - 0.001) * (1 + 0.10)
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
    # T+1：day1 建仓日不计收益；day2 两票均涨 10% → 组合收益 10%（无杠杆）
    assert result["strategy_returns"].iloc[1] == pytest.approx(0.0)
    assert result["strategy_returns"].iloc[2] == pytest.approx(0.10)


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


def test_default_normalize_is_long_only():
    """默认 long_only：正信号按日归一，普通多头满仓且无杠杆"""
    idx = _dates(3)
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=idx)
    signals = pd.DataFrame({"A": [8.0, 8.0, 8.0]}, index=idx)
    result = svc.run_backtest(signals, prices, commission_rate=0.0, slippage=0.0)
    assert result["positions"].iloc[1]["A"] == pytest.approx(1.0)
    assert result["leverage_summary"]["gross_exposure_limit"] == 1.0


def test_short_signals_are_clipped_to_zero():
    """普通股票多头：负信号不产生空头仓位，只视为不买入"""
    idx = _dates(3)
    prices = pd.DataFrame(
        {"A": [100.0, 101.0, 102.0], "B": [100.0, 99.0, 98.0]}, index=idx
    )
    signals = pd.DataFrame({"A": [1.0, 1.0, 1.0], "B": [-1.0, -1.0, -1.0]}, index=idx)
    result = svc.run_backtest(signals, prices, commission_rate=0.0, slippage=0.0, stamp_tax=0.0)
    assert (result["positions"]["B"].abs() < 1e-12).all()
    assert any("不做空" in a for a in result["assumptions"])


def test_non_long_only_and_leverage_are_rejected():
    """普通股票投资边界：做空/多空/原始权重模式与 >100% 仓位全部拒绝"""
    idx = _dates(3)
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0]}, index=idx)
    signals = pd.DataFrame({"A": [1.0, 1.0, 1.0]}, index=idx)

    with pytest.raises(ValueError):
        svc.run_backtest(signals, prices, normalize="none")
    with pytest.raises(ValueError):
        svc.run_backtest(signals, prices, normalize="dollar_neutral")
    with pytest.raises(ValueError):
        svc.run_backtest(signals, prices, max_gross_exposure=2.0)


# ── T+1 执行口径与仓位硬约束（P0-1）──────────────────────────────


def test_t_plus_1_four_day_known_answer():
    """T+1 完整已知答案：day0 信号 → day1 收盘成交，day2 起赚收→收收益"""
    idx = _dates(4)
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0, 133.1]}, index=idx)
    signals = pd.DataFrame({"A": [1.0] * 4}, index=idx)

    result = svc.run_backtest(
        signals, prices, commission_rate=0.001, slippage=0.0, stamp_tax=0.0
    )
    r = result["strategy_returns"]
    assert r.tolist() == pytest.approx([0.0, -0.001, 0.10, 0.10])
    assert result["equity_curve"].iloc[-1] == pytest.approx(
        1_000_000 * (1 - 0.001) * 1.10 * 1.10
    )


def test_budget_constraint_blocks_over_full_position():
    """一字跌停冻结旧仓时买入按预算缩减：总仓位恒 ≤100%，不得 1.0+1.0=200%"""
    idx = _dates(5)
    close = pd.DataFrame(
        {"A": [100.0, 100.0, 100.0, 90.0, 90.0], "B": [50.0] * 5}, index=idx
    )
    signals = pd.DataFrame(
        {"A": [1.0, 1.0, 0.0, 0.0, 0.0], "B": [0.0, 0.0, 1.0, 1.0, 1.0]}, index=idx
    )
    # day3（T+1 换仓执行日）A 一字跌停：high==low==close==前收×0.9
    high = pd.DataFrame(
        {"A": [101.0, 101.0, 101.0, 90.0, 91.0], "B": [51.0] * 5}, index=idx
    )
    low = pd.DataFrame(
        {"A": [99.0, 99.0, 99.0, 90.0, 89.0], "B": [49.0] * 5}, index=idx
    )
    up_limit = close.shift(1) * 1.1
    down_limit = close.shift(1) * 0.9

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
    gross = pos.abs().sum(axis=1)
    assert (gross <= 1.0 + 1e-9).all()
    # 换仓日：A 冻结在 1.0，B 的买入被全额缩减（而不是越界到 2.0）
    assert pos.iloc[3]["A"] == pytest.approx(1.0)
    assert pos.iloc[3]["B"] == pytest.approx(0.0)
    assert result["leverage_summary"]["budget_shrink_days"] == 1
    assert result["leverage_summary"]["max_gross_exposure"] == pytest.approx(1.0)
    assert any("总仓位上限" in a for a in result["assumptions"])
    # 次日解冻：换仓正常完成
    assert pos.iloc[4]["A"] == pytest.approx(0.0)
    assert pos.iloc[4]["B"] == pytest.approx(1.0)


def test_random_signals_budget_invariant_all_modes():
    """不变量：随机信号 + 随机停牌/一字板下，任何一日 Σ|w| ≤ 100%（三种执行时点）"""
    rng = np.random.default_rng(42)
    n_days, n_assets = 250, 10
    idx = pd.bdate_range("2023-01-02", periods=n_days)
    cols = [f"S{i:02d}" for i in range(n_assets)]
    board = rng.random((n_days, n_assets)) < 0.03
    board_sign = rng.choice([-1.0, 1.0], size=(n_days, n_assets))
    rets = np.where(board, board_sign * 0.10, rng.normal(0.0, 0.02, size=(n_days, n_assets)))
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=cols
    )
    open_ = close.shift(1).fillna(100.0) * (
        1 + rng.normal(0.0, 0.005, size=(n_days, n_assets))
    )
    signals = pd.DataFrame(
        rng.uniform(-1.0, 1.0, size=(n_days, n_assets)), index=idx, columns=cols
    )
    tradable = pd.DataFrame(
        rng.random((n_days, n_assets)) > 0.05, index=idx, columns=cols
    )
    # 一字板：high==low==close，且当日涨跌幅恰为 ±10%（触及涨跌停近似价）
    high = (close * 1.01).where(~board, close)
    low = (close * 0.99).where(~board, close)
    up_limit = close.shift(1) * 1.1
    down_limit = close.shift(1) * 0.9

    for mode, extra in [
        ("next_close", {}),
        ("tail", {}),
        ("next_open", {"open_prices": open_}),
    ]:
        result = svc.run_backtest(
            signals,
            close,
            commission_rate=0.0,
            slippage=0.0,
            stamp_tax=0.0,
            tradable_mask=tradable,
            up_limit=up_limit,
            down_limit=down_limit,
            high=high,
            low=low,
            execute_at=mode,
            **extra,
        )
        gross = result["positions"].abs().sum(axis=1)
        assert (gross <= 1.0 + 1e-9).all(), f"{mode}: max gross = {gross.max()}"


def test_no_lookahead_future_price_change_irrelevant():
    """篡改末日价格：之前的持仓与收益完全不受影响（无前视）"""
    idx = _dates(6)
    prices = pd.DataFrame({"A": [100.0, 102.0, 101.0, 105.0, 104.0, 108.0]}, index=idx)
    signals = pd.DataFrame({"A": [1.0, 0.0, 1.0, 1.0, 0.0, 1.0]}, index=idx)
    base = svc.run_backtest(
        signals, prices, commission_rate=0.0, slippage=0.0, stamp_tax=0.0
    )

    tampered = prices.copy()
    tampered.loc[tampered.index[-1], "A"] = 55.0  # 末日价格被剧烈篡改
    out = svc.run_backtest(
        signals, tampered, commission_rate=0.0, slippage=0.0, stamp_tax=0.0
    )

    pd.testing.assert_frame_equal(base["positions"], out["positions"])
    pd.testing.assert_series_equal(
        base["strategy_returns"].iloc[:-1], out["strategy_returns"].iloc[:-1]
    )


def test_entry_day_move_not_counted_for_risk():
    """风控判别测试：建仓当日的大涨不得计入逐仓累计收益（旧实现会次日误触发止盈）"""
    idx = _dates(4)
    # day1 为 T+1 建仓日，当日大涨 +5%（超过 4% 止盈阈值）
    prices = pd.DataFrame({"A": [100.0, 105.0, 105.0, 104.0]}, index=idx)
    signals = pd.DataFrame({"A": [1.0] * 4}, index=idx)

    result = svc.run_backtest(
        signals,
        prices,
        commission_rate=0.0,
        slippage=0.0,
        stamp_tax=0.0,
        take_profit=0.04,
    )
    # 新口径：累计收益自建仓次日起算（105→105→104，从未 +4%），不触发止盈
    assert result["positions"].iloc[-1]["A"] == pytest.approx(1.0)
    assert any("共触发 0 次卖出" in a for a in result["assumptions"])
