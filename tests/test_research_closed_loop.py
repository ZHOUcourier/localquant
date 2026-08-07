"""研究闭环测试：除权事件检测 / 组合回测 / 参数敏感性（合成面板，不依赖 QMT）"""

import numpy as np
import pandas as pd
import pytest

from backend.services import market_data
from backend.services.backtest_analysis import BacktestAnalysisService

svc = BacktestAnalysisService()


def _make_panels(n_dates: int = 260, n_stocks: int = 40, seed: int = 3):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_dates)
    codes = [f"{600000 + i:06d}.SH" for i in range(n_stocks)]
    raw = pd.DataFrame(rng.normal(0, 1, size=(n_dates, n_stocks)), index=dates, columns=codes)
    factor = raw.rolling(20, min_periods=20).mean()
    noise = rng.normal(0, 0.02, size=(n_dates, n_stocks))
    ret = pd.DataFrame(noise, index=dates, columns=codes) + 0.03 * factor.shift(1)
    close = (1 + ret.fillna(0)).cumprod()
    volume = pd.DataFrame(rng.uniform(1e6, 1e7, size=(n_dates, n_stocks)), index=dates, columns=codes)
    amount = pd.DataFrame(rng.uniform(1e7, 5e8, size=(n_dates, n_stocks)), index=dates, columns=codes)
    return {"close": close, "volume": volume, "amount": amount}


def _monkeypatch_market(monkeypatch, panels):
    monkeypatch.setattr(market_data, "list_cached_codes", lambda *a, **k: list(panels["close"].columns))
    monkeypatch.setattr(market_data, "load_price_panels", lambda *a, **k: panels)
    monkeypatch.setattr(
        market_data,
        "load_reference_panels",
        lambda close, volume: {"tradable_mask": None, "up_limit": None,
                               "down_limit": None, "market_cap": None, "industry_map": {}, "assumptions": []},
    )


class TestDividendEvents:
    def test_detect_factor_jump(self, monkeypatch, tmp_path):
        """adjust_factor 跳变应被识别为除权事件（日期 + 比例）"""
        from backend.data.cache import DataCache

        cache_dir = tmp_path / "cache"
        (cache_dir / "1d").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(market_data, "_cache", DataCache(cache_dir=cache_dir))
        dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=60)
        factor = [1.0] * 30 + [1.5] * 30
        df = pd.DataFrame(
            {"close": np.linspace(10, 15, 60), "adjust_factor": factor}, index=dates
        )
        df.to_parquet(cache_dir / "1d" / "000001_SZ.parquet")
        events = market_data.dividend_events(days=365)
        assert len(events) == 1
        assert events[0]["code"] == "000001.SZ"
        assert events[0]["factor_ratio"] == pytest.approx(1.5)
        assert events[0]["date"] == str(dates[30].date())

    def test_no_events_constant_factor(self, monkeypatch, tmp_path):
        from backend.data.cache import DataCache

        cache_dir = tmp_path / "cache2"
        (cache_dir / "1d").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(market_data, "_cache", DataCache(cache_dir=cache_dir))
        dates = pd.bdate_range("2024-01-01", periods=20)
        df = pd.DataFrame(
            {"close": np.linspace(10, 15, 20), "adjust_factor": 1.0}, index=dates
        )
        df.to_parquet(cache_dir / "1d" / "000001_SZ.parquet")
        assert market_data.dividend_events(days=365) == []


class TestPortfolioBacktest:
    def _factors(self):
        # 两个同向动量因子（合成数据为动量驱动，避免方向抵消）
        return [
            {"factor_id": 1, "factor_name": "mom20", "formula": "RANK(CLOSE / DELAY(CLOSE, 20) - 1)"},
            {"factor_id": 2, "factor_name": "mom5", "formula": "RANK(CLOSE / DELAY(CLOSE, 5) - 1)"},
        ]

    def test_portfolio_equal_topn(self, monkeypatch):
        panels = _make_panels()
        _monkeypatch_market(monkeypatch, panels)
        res = svc.portfolio_backtest(
            self._factors(), start_date="", end_date="", combine_method="equal", top_n=10
        )
        assert res["ok"] is True
        assert res["n_factors"] == 2
        assert res["tear_sheet"]["total_return"] > -1
        assert len(res["equity_curve"]) > 100
        assert res["cost_summary"]["breakdown"]["commission"] >= 0
        # 动量合成组合应为正收益（合成数据为动量驱动）
        assert res["tear_sheet"]["total_return"] > 0

    def test_portfolio_ic_weighted(self, monkeypatch):
        panels = _make_panels()
        _monkeypatch_market(monkeypatch, panels)
        res = svc.portfolio_backtest(
            self._factors(), combine_method="ic_weighted", top_n=10
        )
        assert res["ok"] is True
        assert res["combine_method"] == "ic_weighted"
        assert set(res["factor_weights"].keys()) == {"mom20", "mom5"}
        assert res["tear_sheet"]["total_return"] > -1

    def test_portfolio_insufficient_universe(self, monkeypatch):
        panels = _make_panels(n_stocks=5)
        monkeypatch.setattr(market_data, "list_cached_codes", lambda *a, **k: list(panels["close"].columns))
        with pytest.raises(ValueError, match="至少 30 只"):
            svc.portfolio_backtest(self._factors())


class TestSensitivityScan:
    def test_scan_commissions(self, monkeypatch):
        panels = _make_panels()
        _monkeypatch_market(monkeypatch, panels)
        close = panels["close"]
        signals = pd.DataFrame(1.0, index=close.index, columns=close.columns)
        res = svc.sensitivity_scan(
            signals=signals,
            prices=close,
            param_grid={"commission_rate": [0.0, 0.001, 0.003]},
        )
        assert res["n_combos"] == 3
        assert len(res["rows"]) == 3
        # 成本越高收益越低
        returns = [r["total_return"] for r in res["rows"]]
        assert returns[0] >= returns[1] >= returns[2] - 1e-9

    def test_scan_combines_params(self):
        panels = _make_panels()
        close = panels["close"]
        signals = pd.DataFrame(1.0, index=close.index, columns=close.columns)
        res = svc.sensitivity_scan(
            signals=signals,
            prices=close,
            param_grid={"commission_rate": [0.001, 0.002], "stamp_tax": [0.0005, 0.001]},
        )
        assert res["n_combos"] == 4
        keys = {tuple(sorted(r["params"].keys())) for r in res["rows"]}
        assert keys == {("commission_rate", "stamp_tax")}
