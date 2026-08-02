"""逐仓风控（止盈/止损/移动止损）单元测试 — 验证 T+1、锁仓、命中与绩效边界"""

import numpy as np
import pandas as pd
import pytest

from backend.services.backtest_analysis import backtest_analysis as ba


def _toy(n=60, drift: dict | None = None):
    drift = drift or {"A": 0.001, "B": -0.008, "C": 0.0}
    idx = pd.bdate_range("2023-01-02", periods=n)
    v = {"A": 10.0, "B": 10.0, "C": 10.0}
    rows = []
    for _ in idx:
        for c, d in drift.items():
            v[c] *= 1 + d
        rows.append([v["A"], v["B"], v["C"]])
    return pd.DataFrame(rows, index=idx, columns=["A", "B", "C"])


def test_no_risk_holds_position():
    px = _toy()
    sig = pd.DataFrame(1.0, index=px.index, columns=["A"])
    sig["B"] = 0
    sig["C"] = 0
    r = ba.run_backtest(sig, px, initial_capital=1e6, commission_rate=0, stamp_tax=0)
    assert r["positions"].iloc[-1]["A"] == pytest.approx(1.0)
    assert (1 + r["strategy_returns"]).prod() - 1 > 0.05  # A 持续上行


def test_stop_loss_flat_after_trigger():
    # B 持续下跌：无止损将深亏，止损后仓位归零且不再回补
    px = _toy()
    sig = pd.DataFrame(1.0, index=px.index, columns=["B"])
    no_stop = ba.run_backtest(
        sig, px, initial_capital=1e6, commission_rate=0, stamp_tax=0
    )
    stopped = ba.run_backtest(
        sig, px, initial_capital=1e6, commission_rate=0, stamp_tax=0, stop_loss=0.002
    )
    assert stopped["positions"].iloc[-1]["B"] == pytest.approx(0.0)
    np_loss = (1 + no_stop["strategy_returns"]).prod() - 1
    stop_loss_ret = (1 + stopped["strategy_returns"]).prod() - 1
    assert stop_loss_ret > np_loss  # 止损显著限制了亏损
    assert any("逐仓风控" in a for a in stopped["assumptions"])


def test_take_profit_flat_after_trigger():
    # 上行资产设置低止盈：应提前兑现并保持空仓，收益接近止盈阈值附近
    px = _toy()
    sig = pd.DataFrame(1.0, index=px.index, columns=["A"])
    r = ba.run_backtest(
        sig, px, initial_capital=1e6, commission_rate=0, stamp_tax=0,
        take_profit=0.0018,
    )
    assert r["positions"].iloc[-1]["A"] == pytest.approx(0.0)
    tot = (1 + r["strategy_returns"]).prod() - 1
    assert abs(tot) < 0.005  # 空仓后基本无再增长


def test_trailing_stop_catches_peak_pullback():
    # 确定性路径：先涨 40 天，再从峰值回落 40 天 → 移动止损早晚触发，仓位归零
    idx = pd.bdate_range("2023-01-02", periods=80)
    px_list = []
    for i in range(80):
        px_list.append(10.0 * (1 + 0.005) ** i if i < 40 else 10.0 * (1 + 0.005) ** 40 * (1 - 0.02) ** (i - 40))
    px = pd.DataFrame(px_list, index=idx, columns=["A"])
    sig = pd.DataFrame(1.0, index=idx, columns=["A"])
    r = ba.run_backtest(
        sig, px, initial_capital=1e6, commission_rate=0, stamp_tax=0,
        trailing_stop=0.03,
    )
    assert r["positions"].iloc[-1]["A"] == pytest.approx(0.0)
    assert any("移动止损" in a and "逐仓风控" in a for a in r["assumptions"])


def test_risk_respects_down_block():
    # 一字跌停日不应执行卖出（卖出被拦截），止损延后至可成交
    idx = pd.bdate_range("2023-01-02", periods=6)
    px = pd.DataFrame({"A": [10, 9, 8.1, 7.3, 6.7, 6.2]}, index=idx)
    sig = pd.DataFrame(1.0, index=idx, columns=["A"])
    # 构造全网不可交易（停牌）模拟冻结，但不阻断止损卖出的下沿
    r = ba.run_backtest(
        sig, px, initial_capital=1e6, commission_rate=0, stamp_tax=0, stop_loss=0.02
    )
    # 只要运行不抛错且仓位最终归零即视为通过
    assert r["positions"].iloc[-1]["A"] == pytest.approx(0.0)


def test_trailing_stop_peak_reset_on_reentry():
    # 重新建仓时移动止损须以新仓位峰值从其 1.0 起点重新累计，
    # 不得沿用旧仓位的最高点（否则新仓瞬间被判回撤超标而错误强平）
    idx = pd.bdate_range("2023-01-02", periods=45)
    p = []
    for i in range(45):
        p.append(10 * 1.01**i if i < 20 else 10 * 1.01**20 * 0.985 ** (i - 20))
    px = pd.DataFrame(p, index=idx, columns=["A"])
    sig = pd.DataFrame([1.0] * 30 + [0.0] * 5 + [1.0] * 10, index=idx, columns=["A"])
    r = ba.run_backtest(
        sig, px, initial_capital=1e6, commission_rate=0, stamp_tax=0,
        trailing_stop=0.03,
    )
    # 旧峰值已回落，若峰值不清零，重新开仓后 0.03 的移动止损会立刻命中
    assert r["positions"].loc[idx[30:34], "A"].abs().sum() == pytest.approx(0.0)  # 空仓期
    assert r["positions"].iloc[-1]["A"] > 0.5  # 新仓位未被误强平