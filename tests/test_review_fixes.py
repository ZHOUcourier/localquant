"""评审整改回归测试：行业归因/事前风险/历史情景/事件研究/walk-forward/
空头过滤/执行时点/块自助蒙特卡洛/Cashflow 字段/滚动IC权重

全部使用合成数据，不依赖 QMT（与既有测试同约定）。
"""

import numpy as np
import pandas as pd
import pytest

from backend.services import event_study as es
from backend.services import risk
from backend.services.backtest_analysis import BacktestAnalysisService, backtest_analysis


def _make_panels(n_stocks=30, n_days=120, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    codes = [f"{600000 + i}.SH" for i in range(n_stocks)]
    ret = pd.DataFrame(rng.normal(0.0004, 0.02, (n_days, n_stocks)), index=dates, columns=codes)
    close = 20 * (1 + ret).cumprod()
    volume = pd.DataFrame(rng.integers(1e6, 1e7, (n_days, n_stocks)).astype(float), index=dates, columns=codes)
    amount = close * volume * 1e-2
    open_ = close * (1 + rng.normal(0, 0.004, (n_days, n_stocks)))
    high = pd.DataFrame(np.maximum(open_.to_numpy(), close.to_numpy()), index=dates, columns=codes)
    low = pd.DataFrame(np.minimum(open_.to_numpy(), close.to_numpy()), index=dates, columns=codes)
    return {"close": close, "volume": volume, "amount": amount, "open": open_, "high": high, "low": low}


# ── 行业因子收益与行业归因 ──────────────────────────────────────────


def test_industry_factor_returns_relative_to_market():
    panels = _make_panels(n_stocks=40, n_days=100, seed=3)
    codes = list(panels["close"].columns)
    ind = {c: ["银行", "食品饮料", "电子", "医药生物"][i % 4] for i, c in enumerate(codes)}
    # 注入：医药生物股票在窗口后半段系统性多涨 0.4%/日
    ret = panels["close"].pct_change()
    dates = ret.index
    for i, c in enumerate(codes):
        if ind[c] == "医药生物":
            ret.loc[dates[60:], c] = ret.loc[dates[60:], c] + 0.004
    res = risk.industry_factor_returns(ret, ind)
    flows = res["factor_returns"]
    assert "IND_医药生物" in flows
    med = pd.Series(flows["IND_医药生物"]).dropna()
    # 医药行业相对市场平均的超额应显著为正（注入 0.4%/日 × 40 日）
    assert med.mean() > 0.0003
    # 基准行业（银行）超额均值应小于医药
    bank = pd.Series(flows["IND_银行"]).dropna()
    assert bank.mean() < med.mean()


def test_industry_exposure_panel_structure():
    panels = _make_panels(n_stocks=20, n_days=10, seed=5)
    codes = list(panels["close"].columns)
    ind = {c: ["银行", "电子"][i % 2] for i, c in enumerate(codes)}
    exp = risk.build_industry_exposures(panels["close"].index, ind)
    assert exp.shape == (10, 20)
    # 均值偏离编码：每只股票的值 = 1 - 行业覆盖率（银行/电子各 10 只 → 0.5）
    assert np.allclose(exp.to_numpy(), 0.5, atol=1e-9)
    # 行业覆盖率 1/3 时值 = 2/3
    ind3 = {c: ["银行", "电子", "医药"][i % 3] for i, c in enumerate(codes[:9])}
    exp3 = risk.build_industry_exposures(panels["close"].index[:2], ind3)
    assert np.allclose(exp3.to_numpy(), 2 / 3, atol=1e-9)


def test_risk_forecast_positive_vol_and_decomposition():
    panels = _make_panels(n_stocks=30, n_days=150, seed=11)
    close, ret = panels["close"], panels["close"].pct_change()
    styles = risk.build_style_exposures(close, volume=panels["volume"], amount=panels["amount"])
    sres = risk.style_factor_returns(ret, styles)
    # 风格倾斜组合：权重与 MOMENTUM 暴露正相关（等权组合暴露≈0，分解无意义）
    mom = styles["MOMENTUM"].iloc[-1]
    w = (mom - mom.min()) / (mom.max() - mom.min()) + 0.5
    w = w / w.sum()
    wf = pd.DataFrame(
        np.tile(w.to_numpy(), (len(close.index), 1)), index=close.index, columns=close.columns
    )
    pstyles = risk.portfolio_style_exposure(wf, styles)
    out = risk.risk_forecast(w, sres["factor_returns"], portfolio_exposures=pstyles, returns=ret)
    assert out["forecast_vol_annual"] > 0
    assert out["idiosyncratic_pct"] >= 0
    assert out["factor_risk_contrib"]  # 至少一个因子有贡献
    assert abs(sum(out["factor_risk_contrib"].values()) + out["idiosyncratic_pct"] - 1) < 0.05


def test_historical_scenario_stress_uses_real_window():
    panels = _make_panels(n_stocks=20, n_days=200, seed=9)
    ret = panels["close"].pct_change()
    w = pd.Series(0.05, index=list(panels["close"].columns))
    out = risk.historical_scenario_stress(
        ret, w, scenario_windows={"危机窗口": (str(ret.index[50].date()), str(ret.index[80].date()))}
    )
    s = out["危机窗口"]
    assert s["n_days"] > 0
    assert s["cum_return_pct"] is not None
    assert isinstance(s["max_drawdown_pct"], float)


# ── 事件研究 ─────────────────────────────────────────────────────────


def test_event_study_detects_injected_abnormal_return():
    panels = _make_panels(n_stocks=30, n_days=120, seed=13)
    ret = panels["close"].pct_change()
    dates = ret.index
    # 10 只股票在第 60 日发生事件，事件后 10 天每日 +3% 异常收益（远高于日噪音）
    codes = list(ret.columns)[:10]
    for i in range(10):
        for c in codes:
            ret.loc[dates[61 + i], c] = ret.loc[dates[61 + i], c] + 0.03
    events = pd.DataFrame({"date": [dates[60]] * 10, "code": codes})
    res = es.event_study_analysis(ret, events, window_before=5, window_after=10)
    assert res["ok"]
    assert res["n_events"] == 10
    # 事件后 CAR 上升：期末均值 > 0 且 t 值 > 1
    assert res["car"][str(10)]["mean"] > 0.005
    assert res["car_end_t"] > 1.0
    assert res["bhar_mean"] > 0


def test_event_study_merges_close_duplicate_events():
    events = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-05"]), "code": ["600000.SH"] * 3}
    )
    merged = es._merge_duplicate_events(events, gap=3)
    # 1/2 与 1/3 间隔 1 天合并，1/5 间隔 2 天也合并 → 1 个事件
    assert len(merged) == 1


# ── walk-forward 组合回测 ───────────────────────────────────────────


class _FakeMd:
    def __init__(self, panels):
        self.panels = panels
        self.codes = list(panels["close"].columns)

    def list_cached_codes(self, period="1d"):
        return self.codes

    def load_price_panels(self, codes=None, start_date="", end_date=""):
        return self.panels

    def load_reference_panels(self, close, volume=None):
        return {
            "tradable_mask": pd.DataFrame(True, index=close.index, columns=close.columns),
            "up_limit": pd.DataFrame(99.0, index=close.index, columns=close.columns),
            "down_limit": pd.DataFrame(0.01, index=close.index, columns=close.columns),
        }


def test_walk_forward_portfolio_stitches_folds(monkeypatch):
    import backend.services.market_data as md
    from backend.services.backtest_analysis import backtest_analysis as svc

    panels = _make_panels(n_stocks=30, n_days=300, seed=17)
    fake = _FakeMd(panels)
    monkeypatch.setattr(md, "list_cached_codes", fake.list_cached_codes)
    monkeypatch.setattr(md, "load_price_panels", fake.load_price_panels)
    monkeypatch.setattr(md, "load_reference_panels", fake.load_reference_panels)
    res = svc.walk_forward_portfolio(
        factors=[{"factor_name": "mom5", "formula": "RANK(close / DELAY(close, 5) - 1)"}],
        start_date="2023-01-02",
        top_n=10,
        train_days=120,
        test_days=60,
    )
    assert res["ok"]
    assert res["n_folds"] >= 2
    assert res["tear_sheet"]["trading_days"] > 0
    assert "in_sample_reference" in res
    assert any("样本外" in a for a in res["assumptions"])


# ── 空头可融券过滤 ───────────────────────────────────────────────────


def test_shortable_mask_blocks_shorts():
    svc = BacktestAnalysisService()
    dates = pd.bdate_range("2023-01-02", periods=10)
    codes = ["600000.SH", "600001.SH"]
    close = pd.DataFrame(
        {c: 20 * (1.01 ** np.arange(10)) for c in codes}, index=dates
    )
    # 两只都做空，但 600001 不可融券
    signals = pd.DataFrame({c: -1.0 for c in codes}, index=dates)
    shortable = pd.DataFrame({"600000.SH": True, "600001.SH": False}, index=dates, columns=codes)
    res = svc.run_backtest(
        signals=signals, prices=close, normalize="dollar_neutral", shortable_mask=shortable
    )
    # 不可融券标的无空头仓位
    assert (res["positions"]["600001.SH"].abs() < 1e-12).all()
    assert (res["positions"]["600000.SH"] < 0).any()
    # 不传 shortable 时多空策略会给出假设警示
    res2 = svc.run_backtest(signals=signals, prices=close, normalize="dollar_neutral")
    assert any("未过滤" in a for a in res2["assumptions"])


# ── 执行时点（tail / next_open） ────────────────────────────────────


def test_execute_at_next_open_uses_intraday_returns():
    svc = BacktestAnalysisService()
    dates = pd.bdate_range("2023-01-02", periods=8)
    codes = ["600000.SH"]
    vals = [10, 10.2, 10.4, 10.6, 10.8, 11.0, 11.2, 11.4]
    close = pd.DataFrame({codes[0]: vals}, index=dates)
    # 开盘价显著低于收盘（每天 9:30 低开 5%，随后拉升）→ next_open 执行买到更低价
    open_ = pd.DataFrame({codes[0]: [v * 0.95 for v in vals]}, index=dates)
    signals = pd.DataFrame(1.0, index=dates, columns=codes)
    res_close = svc.run_backtest(signals=signals, prices=close, normalize="long_only", execute_at="next_close")
    res_open = svc.run_backtest(
        signals=signals, prices=close, normalize="long_only",
        execute_at="next_open", open_prices=open_,
    )
    # 低开买入 → 开盘执行的组合收益更高
    assert res_open["strategy_returns"].sum() > res_close["strategy_returns"].sum()


def test_execute_at_tail_shifts_return_attribution():
    svc = BacktestAnalysisService()
    dates = pd.bdate_range("2023-01-02", periods=6)
    close = pd.Series([10, 11, 12, 13, 14, 15], index=dates).to_frame("600000.SH")
    signals = pd.DataFrame({"600000.SH": [0, 1, 1, 1, 1, 1]}, index=dates)
    res = svc.run_backtest(signals=signals, prices=close, normalize="long_only", execute_at="tail")
    # 首日信号为 0 不建仓；第 2 日信号=1 当日收盘建仓 → 当日仅付买入成本（0.2%）
    assert res["strategy_returns"].iloc[0] == 0.0
    assert res["strategy_returns"].iloc[1] == pytest.approx(-0.002)
    # 第 3 日起赚持有收益（+1 天回报）
    assert res["strategy_returns"].iloc[2] > 0.05
    assert any("尾盘执行" in a for a in res["assumptions"])


# ── 块自助蒙特卡洛 ──────────────────────────────────────────────────


def test_monte_carlo_block_bootstrap():
    rng = np.random.default_rng(1)
    # 高度自相关的序列：块自助应保留收益分布形状（均值接近历史均值）
    rets = pd.Series(rng.normal(0.001, 0.02, 500))
    out = backtest_analysis.monte_carlo_simulation(rets, n_sims=200, n_days=250, method="block", block_size=25)
    assert out["method"] == "block"
    assert out["terminal_percentiles"]["p50"] > 0
    # 最大回撤均值为负（回撤口径）；块自助下与正态抽样量级接近
    assert -0.6 < out["max_drawdown_stats"]["mean"] < -0.01
    # 兼容旧接口（无 method 参数 → 默认 block）
    out2 = backtest_analysis.monte_carlo_simulation(rets, n_sims=50, n_days=100)
    assert out2["method"] == "block"


# ── Cashflow 字段与别名 ─────────────────────────────────────────────


def test_fundamental_merge_cashflow_aliases():
    from backend.services import fundamental

    frames = {
        "Cashflow": pd.DataFrame(
            {
                "m_anntime": [pd.Timestamp("2023-01-01")],
                "OperatingNetCashFlow": [123.0],
                "NetIncreaseInCash": [45.0],
            }
        )
    }
    m = fundamental._merge_frames(frames)
    assert "operating_cashflow" in m.columns
    assert "total_cashflow" in m.columns
    assert m["operating_cashflow"].iloc[0] == pytest.approx(123.0)


def test_fundamental_snapshot_tables_include_cashflow():
    from backend.services import fundamental

    import inspect

    src = inspect.getsource(fundamental.snapshot_fundamental)
    assert "Cashflow" in src
