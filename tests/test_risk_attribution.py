"""回测风格归因（回归法）测试：合成风格因子收益 + 组合收益"""

import numpy as np
import pandas as pd

from backend.services import risk as risk_svc


def _synthetic(n_dates: int = 252, seed: int = 11):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_dates)
    # 三个正交风格因子日收益
    f1 = rng.normal(0.0005, 0.01, n_dates)
    f2 = rng.normal(0.0, 0.008, n_dates)
    f3 = rng.normal(0.0, 0.006, n_dates)
    style_returns = {
        "SIZE": pd.DataFrame({"SIZE": f1}, index=dates),
        "MOMENTUM": pd.DataFrame({"MOMENTUM": f2}, index=dates),
        "VOLATILITY": pd.DataFrame({"VOLATILITY": f3}, index=dates),
    }
    # 组合 = 1.2×SIZE - 0.5×MOMENTUM + 真 alpha（0.0004/日，约 10%/年）
    alpha_daily = 0.0004
    noise = rng.normal(0, 0.005, n_dates)
    port = 1.2 * f1 - 0.5 * f2 + alpha_daily + noise
    returns = pd.Series(port, index=dates)
    return returns, style_returns, alpha_daily


def test_regression_attribution_recovers_betas():
    returns, style_returns, alpha_daily = _synthetic()
    res = risk_svc.strategy_regression_attribution(returns, style_returns)
    assert res["ok"] is True
    # β 恢复（回归估计在 ±0.3 内）
    assert abs(res["beta"]["SIZE"] - 1.2) < 0.3
    assert abs(res["beta"]["MOMENTUM"] - (-0.5)) < 0.3
    # alpha 年化接近 10%（0.0004×252 ≈ 10.6%），容差 ±4%
    assert abs(res["alpha_annual"] - alpha_daily * 252) < 0.04
    # R² 高（噪声小）
    assert res["r2"] > 0.3


def test_regression_attribution_insufficient_samples():
    returns, style_returns, _ = _synthetic(n_dates=20)
    res = risk_svc.strategy_regression_attribution(returns, style_returns)
    assert res["ok"] is False
    assert "样本不足" in res["message"]


def test_regression_attribution_no_alpha():
    """纯风格暴露（无 alpha）的组合：alpha 应接近 0"""
    rng = np.random.default_rng(5)
    dates = pd.bdate_range("2024-01-02", periods=252)
    f1 = rng.normal(0.0005, 0.01, 252)
    style_returns = {"SIZE": pd.DataFrame({"SIZE": f1}, index=dates)}
    returns = pd.Series(0.8 * f1, index=dates)
    res = risk_svc.strategy_regression_attribution(returns, style_returns)
    assert res["ok"] is True
    assert abs(res["alpha_annual"]) < 0.03
    assert abs(res["beta"]["SIZE"] - 0.8) < 0.3


def test_attribution_run_endpoint_missing_run():
    """attribution-run 对不存在的 run 返回 404"""
    import asyncio
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/risk/attribution-run",
        data=json.dumps({"run_id": "no-such-run"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req)
        assert False, "应返回 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404
