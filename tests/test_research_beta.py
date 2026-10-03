"""Beta 研究工具测试：QuantZone 对拍服务 + vectorbt 参数扫描

全部离线：QZ 网络侧用 monkeypatch 替身；vectorbt 用合成面板真跑。
不依赖 .env 密钥（对拍测试不触网）。
"""

import numpy as np
import pandas as pd
import pytest

from backend.services import quantzone_service as qz_svc
from backend.services import vectorbt_scan as vbt_scan

# ── ukey 映射 ────────────────────────────────────────────────────


def test_to_qz_ukey_mapping():
    assert qz_svc.to_qz_ukey("600519.SH") == "600519.XSHG"
    assert qz_svc.to_qz_ukey("000858.SZ") == "000858.XSHE"
    assert qz_svc.to_qz_ukey("300750.SZ") == "300750.XSHE"
    assert qz_svc.to_qz_ukey("600519") == "600519.XSHG"
    assert qz_svc.to_qz_ukey("830799.BJ") is None


# ── 对拍（monkeypatch QZ 拉取，本地走合成分钟缓存） ─────────────────


@pytest.fixture
def minute_cache(tmp_path):
    from test_intraday import _make_minute_cache

    import backend.services.intraday_cleaner as ic
    from backend.data.cache import DataCache

    cache, codes = _make_minute_cache(tmp_path, n_stocks=5, days=25)
    ic._cache = DataCache(tmp_path)
    yield cache, codes
    ic._cache = None


def test_reconcile_match_with_self(monkeypatch, minute_cache):
    """本地熵因子 vs 自身（替身 QZ 返回同一面板）→ match"""
    from backend.services.intraday_cleaner import load_intraday_panels
    from backend.services.intraday_operators import ID_PV_ENTROPY

    _cache, codes = minute_cache
    loaded = load_intraday_panels(codes, "5m")
    local = ID_PV_ENTROPY(loaded["panels"]["close"], loaded["panels"]["volume"], 30)
    qz_wide = local.copy()
    qz_wide.columns = [c.split(".")[0] for c in qz_wide.columns]
    monkeypatch.setattr(qz_svc, "get_factor_wide", lambda *a, **k: qz_wide)

    report = qz_svc.reconcile(
        qz_factor="feat_single_amt_ratio_entropy_30m",
        local_formula="ID_PV_ENTROPY(m_close, m_volume, 30)",
        codes=codes,
        start_date="2024-01-02",
        end_date="2024-02-10",
    )
    assert report["ok"] and report["verdict"] == "match"
    assert report["metrics"]["corr"] > 0.999
    assert report["metrics"]["match_ratio_rel1pct"] > 0.95
    assert report["sample"]


def test_reconcile_scale_mismatch_is_direction_match(monkeypatch, minute_cache):
    """QZ 值整体缩放 2 倍 → 排序一致但量级不符 → direction_match"""
    from backend.services.intraday_cleaner import load_intraday_panels
    from backend.services.intraday_operators import ID_PV_ENTROPY

    _cache, codes = minute_cache
    loaded = load_intraday_panels(codes, "5m")
    local = ID_PV_ENTROPY(loaded["panels"]["close"], loaded["panels"]["volume"], 30)
    qz_wide = (local * 2.0)
    qz_wide.columns = [c.split(".")[0] for c in qz_wide.columns]
    monkeypatch.setattr(qz_svc, "get_factor_wide", lambda *a, **k: qz_wide)

    report = qz_svc.reconcile(
        qz_factor="feat_single_amt_ratio_entropy_30m",
        local_formula="ID_PV_ENTROPY(m_close, m_volume, 30)",
        codes=codes,
    )
    assert report["ok"] and report["verdict"] == "direction_match"
    assert report["metrics"]["match_ratio_rel1pct"] < 0.95


def test_reconcile_empty_qz_returns_message(monkeypatch):
    monkeypatch.setattr(qz_svc, "get_factor_wide", lambda *a, **k: pd.DataFrame())
    report = qz_svc.reconcile(
        qz_factor="foo",
        local_formula="ID_PV_ENTROPY(m_close, m_volume, 30)",
        codes=["600000.SH"],
    )
    assert not report["ok"] and "未返回" in report["message"]


def test_reconcile_amt_hint_in_notes(monkeypatch, minute_cache):
    """mismatch 且 QZ 因子名含 amt → 提示 volume/amount 口径"""
    from backend.services.intraday_cleaner import load_intraday_panels
    from backend.services.intraday_operators import ID_PV_ENTROPY

    _cache, codes = minute_cache
    loaded = load_intraday_panels(codes, "5m")
    local = ID_PV_ENTROPY(loaded["panels"]["close"], loaded["panels"]["volume"], 30)
    rng = np.random.default_rng(7)
    noise = pd.DataFrame(
        rng.normal(0, 0.05, local.shape), index=local.index, columns=local.columns
    )
    qz_wide = (local + noise)
    qz_wide.columns = [c.split(".")[0] for c in qz_wide.columns]
    monkeypatch.setattr(qz_svc, "get_factor_wide", lambda *a, **k: qz_wide)

    report = qz_svc.reconcile(
        qz_factor="feat_single_amt_ratio_entropy_30m",
        local_formula="ID_PV_ENTROPY(m_close, m_volume, 30)",
        codes=codes,
    )
    assert report["verdict"] == "mismatch"
    assert any("m_amount" in n for n in report["notes"])


# ── vectorbt 参数扫描（合成面板真跑） ─────────────────────────────


def _synthetic_factor_close(n_stocks=8, n_days=60, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    codes = [f"{600000 + i}.SH" for i in range(n_stocks)]
    # 因子 = 股票固定强度 + 噪声 → 高因子股票趋势更强
    strength = rng.uniform(0.0002, 0.003, n_stocks)
    rets = pd.DataFrame(
        rng.normal(0, 0.01, (n_days, n_stocks)) + strength, index=dates, columns=codes
    )
    close = 20 * (1 + rets).cumprod()
    factor = pd.DataFrame(
        rng.normal(0, 1, (n_days, n_stocks)), index=dates, columns=codes
    )
    factor = factor + np.linspace(0, 1, n_days)[:, None] * rng.normal(1, 0.1, (1, n_stocks))
    return factor, close


def test_scan_quantile_runs_and_ranks():
    factor, close = _synthetic_factor_close()
    res = vbt_scan.scan_quantile_portfolios(
        factor,
        close,
        group_list=[2, 4],
        rebalance_list=[5, 10],
        fee_rate=0.0,
        min_stocks=5,
    )
    assert res["ok"]
    assert len(res["rows"]) == 4
    assert all(
        set(r) >= {"groups", "rebalance_days", "annual_return", "sharpe", "max_drawdown", "trades"}
        for r in res["rows"]
    )
    assert res["rows"] == sorted(res["rows"], key=lambda r: r["sharpe"], reverse=True)
    assert res["best"] == res["rows"][0]
    assert any(r["trades"] > 0 for r in res["rows"])


def test_scan_direction_flag_changes_result():
    """direction=-1（低值做多）与 1 的最优组收益方向应不同"""
    factor, close = _synthetic_factor_close()
    res_long = vbt_scan.scan_quantile_portfolios(
        factor, close, group_list=[2], rebalance_list=[10], fee_rate=0.0, direction=1, min_stocks=5
    )
    res_short = vbt_scan.scan_quantile_portfolios(
        factor, close, group_list=[2], rebalance_list=[10], fee_rate=0.0, direction=-1, min_stocks=5
    )
    assert res_long["ok"] and res_short["ok"]
    assert res_long["rows"][0]["annual_return"] != res_short["rows"][0]["annual_return"]


def test_scan_insufficient_dates():
    factor, close = _synthetic_factor_close(n_days=10)
    res = vbt_scan.scan_quantile_portfolios(factor, close, group_list=[2], rebalance_list=[5])
    assert not res["ok"] and "不足" in res["message"]
