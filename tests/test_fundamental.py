"""基本面点(time-point-in-time) / 因子严谨性测试 — 合成数据，不依赖 QMT"""

import numpy as np
import pandas as pd
import pytest

from backend.services import fundamental
from backend.services.factor_research import factor_research


def _make_fund_file(code, anntimes, values, fund_dir):
    """写一只股票基本面 parquet：rows=公告日(ms epoch), col=eps"""
    df = pd.DataFrame(
        {
            "annt": (pd.to_datetime(anntimes).astype("int64") // 10**6),
            "eps": values,
        }
    )
    df.to_parquet(fund_dir / f"{code.replace('.', '_')}.parquet", index=False)


def test_fundamental_uses_announce_time_point_in_time(tmp_path):
    """公告日前不可用 → 不 ffill；公告日当天起值可用"""
    fund_dir = tmp_path / "fund"
    fund_dir.mkdir()
    _make_fund_file("000001.SZ", ["2023-06-15", "2023-07-01"], [2.0, 2.5], fund_dir)

    trade_dates = pd.bdate_range("2023-06-01", "2023-07-10")
    panels = fundamental.build_fundamental_panels(
        ["000001.SZ"], trade_dates, fund_dir=fund_dir
    )
    eps = panels["eps"]["000001.SZ"]
    # 首公告日(2023-06-15)之前为 NaN
    assert np.isnan(eps.loc["2023-06-14"])
    assert eps.loc["2023-06-15"] == pytest.approx(2.0)
    # 二公告日前仍是 2.0，之后 2.5
    assert eps.loc["2023-06-30"] == pytest.approx(2.0)
    assert eps.loc["2023-07-03"] == pytest.approx(2.5)


def test_ic_mask_excludes_untradeable():
    rng = np.random.default_rng(3)
    dates = pd.date_range("2023-01-03", periods=120, freq="B")
    stocks = [f"{i:06d}.SZ" for i in range(1, 31)]
    factor = pd.DataFrame(rng.normal(size=(len(dates), len(stocks))),
                          index=dates, columns=stocks)
    ret = pd.DataFrame(rng.normal(0, 0.01, size=(len(dates), len(stocks))),
                       index=dates, columns=stocks)
    # 第 3 只股票首日后全不可交易
    mask = pd.DataFrame(True, index=dates, columns=stocks)
    mask.iloc[1:, 2] = False
    full = factor_research.ic_analysis(factor, ret, periods=[1])
    masked = factor_research.ic_analysis(factor, ret, periods=[1], mask=mask)
    assert full["period_1"]["ic_series"] != masked["period_1"]["ic_series"]


def test_quantile_net_cost_penalizes_turnover():
    rng = np.random.default_rng(4)
    dates = pd.date_range("2023-01-03", periods=60, freq="B")
    stocks = [f"{i:06d}.SZ" for i in range(1, 41)]
    # 高换手因子（随机 0/1 → 分组轮换大）
    factor = pd.DataFrame(
        rng.choice([0, 1], size=(len(dates), len(stocks))),
        index=dates, columns=stocks,
    ).astype(float)
    ret = pd.DataFrame(
        0.001 * rng.normal(size=(len(dates), len(stocks))),
        index=dates, columns=stocks,
    )
    net = factor_research.quantile_analysis_net(factor, ret, n_groups=2, cost_rate=0.001)
    for info in net["by_group"].values():
        assert info["net_cum"] <= info["gross_cum"] + 1e-9


def test_fundamental_merge_keeps_fund_fields():
    frames = {
        "Pershareindex": pd.DataFrame(
            {"m_anntime": [pd.Timestamp("2023-01-01")] * 2, "eps": [1.0, 1.0]}
        )
    }
    m = fundamental._merge_frames(frames)
    assert "anntime" in m.columns
    assert "eps" in m.columns