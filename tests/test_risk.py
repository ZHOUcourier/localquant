"""风险组合层测试 — 风格暴露/组合优化/绩效补充/压力测试（合成数据）"""

import numpy as np
import pandas as pd
import pytest

from backend.services import risk


def _panel(seed=0, n_stocks=40, n_days=260):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-03", periods=n_days, freq="B")
    stocks = [f"{i:06d}.SZ" for i in range(n_stocks)]
    close = pd.DataFrame(
        100 * rng.lognormal(0, 0.015, (n_days, n_stocks)), index=dates, columns=stocks
    )
    amount = pd.DataFrame(
        1e8 * rng.uniform(0.5, 2, (n_days, n_stocks)), index=dates, columns=stocks
    )
    mcap = pd.DataFrame(
        2e10 * rng.uniform(0.5, 3, (n_days, n_stocks)), index=dates, columns=stocks
    )
    return {"close": close, "amount": amount, "market_cap": mcap}


def test_style_exposures_cross_sectional_zscore():
    p = _panel()
    styles = risk.build_style_exposures(
        p["close"], amount=p["amount"], market_cap=p["market_cap"]
    )
    assert set(styles) >= {"SIZE", "MOMENTUM", "VOLATILITY"}
    # 每期截面大致 z-score（均值接近0，std接近1）
    e = styles["SIZE"].iloc[-1].dropna()
    assert abs(e.mean()) < 0.1
    assert abs(e.std() - 1.0) < 0.2


def test_portfolio_style_exposure_equal_weight_is_neutral():
    p = _panel()
    styles = risk.build_style_exposures(
        p["close"], amount=p["amount"], market_cap=p["market_cap"]
    )
    stocks = p["close"].columns
    w = pd.DataFrame(1 / len(stocks), index=p["close"].index, columns=stocks)
    exp = risk.portfolio_style_exposure(w, styles)
    # 等权组合对 z-score 风格暴露应约 0
    for name, ser in exp.items():
        val = float(ser.abs().mean())
        assert val < 0.05, name


def test_style_factor_returns_runs_and_summary():
    p = _panel()
    ret = p["close"].pct_change()
    styles = risk.build_style_exposures(p["close"], amount=p["amount"])
    res = risk.style_factor_returns(ret, styles)
    assert isinstance(res["cov"], pd.DataFrame)
    assert {s["style"] for s in res["summary"]} <= set(styles)


def test_optimize_weights_respects_constraints():
    p = _panel()
    stocks = p["close"].columns[:30]
    rng = np.random.default_rng(7)
    scores = pd.Series(rng.normal(size=len(stocks)), index=stocks)
    ind = {c: "A" if i % 2 == 0 else "B" for i, c in enumerate(stocks)}
    w = risk.optimize_weights(
        scores, industry_map=ind, max_position=0.2, max_industry_exposure=0.3
    )
    assert abs(float(w.sum()) - 1.0) < 0.02
    assert float(w.max()) <= 0.2 + 1e-6
    assert (w >= -1e-9).all()


def test_extended_metrics_beta_alpha():
    p = _panel(seed=1)
    r = p["close"].pct_change()
    ser = r.iloc[:, 0]
    bm = r.mean(axis=1)
    m = risk.extended_risk_metrics(ser, benchmark_returns=bm)
    assert "beta" in m and "alpha" in m
    assert "downside_capture" in m  # 有负收益日


def test_active_share():
    a = pd.Series({"x": 0.5, "y": 0.3, "z": 0.2})
    b = pd.Series({"x": 0.5, "y": 0.4, "z": 0.1})
    m = risk.extended_risk_metrics(
        returns=pd.Series(np.random.default_rng(0).normal(0, 0.01, 30)),
        weights=a, benchmark_weights=b,
    )
    assert m["active_share"] == pytest.approx(0.1, abs=1e-9)


def test_stress_test_impact():
    weights = pd.Series({"000001.SZ": 0.5, "000002.SZ": 0.5})
    out = risk.stress_test(pd.DataFrame(), weights, None)
    assert out["sharp_crash"]["impact_pct"] == pytest.approx(-0.09, abs=1e-9)


def test_covariance_shrinkage_shape():
    p = _panel(seed=2)
    sigma = risk.covariance_estimator(p["close"].pct_change(), shrinkage=0.2)
    assert sigma.shape == (p["close"].shape[1], p["close"].shape[1])