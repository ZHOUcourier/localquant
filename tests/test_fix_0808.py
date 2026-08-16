"""2026-08-08 投研实用性评估后修复的回归测试

覆盖评估中实测出的 P0 缺陷：
- 因子 IC/衰减结果含 NaN 导致 JSONResponse 500
- 容量分析布尔 DataFrame 索引导致 mean_participation 恒为 NaN
- 工作流同步 run 返回含 numpy/NaN 导致序列化 500
- 回测后台并发信号量变量与函数同名，永远拿不到 Semaphore
"""

import asyncio
import json

import numpy as np
import pandas as pd

from backend.config import settings
from backend.routes.backtest import RunStrategyRequest, _backtest_sem
from backend.services.backtest_analysis import BacktestAnalysisService
from backend.services.factor_research import FactorResearchService
from backend.services.sandbox import _status_cache, sandbox_status
from backend.services.workflow_service import _jsonable

bt = BacktestAnalysisService()
fr = FactorResearchService()


def _panel(n_dates: int = 80, n_stocks: int = 12, seed: int = 11):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_dates)
    codes = [f"{i:06d}.SZ" for i in range(1, n_stocks + 1)]
    rets = pd.DataFrame(
        rng.normal(0.0, 0.02, size=(n_dates, n_stocks)),
        index=dates,
        columns=codes,
    )
    rets.iloc[0] = 0.0
    close = (1 + rets).cumprod() * 100
    return rets, close


def test_ic_and_decay_are_json_serializable():
    """常量因子会产生 NaN 相关系数：服务应跳过，响应可被 JSON 严格序列化"""
    rets, _ = _panel()
    factor = pd.DataFrame(0.0, index=rets.index, columns=rets.columns)

    ic = fr.ic_analysis(factor, rets, periods=[1, 5])
    json.dumps(ic, allow_nan=False)

    decay = fr.factor_decay(factor, rets, max_period=5)
    json.dumps(decay, allow_nan=False)
    assert all(np.isfinite(row["ic"]) for row in decay["decay_series"])


def test_capacity_mean_participation_finite():
    """容量分析各档 mean/p95 不能出现 NaN（布尔 DataFrame 索引陷阱）"""
    _rets, close = _panel()
    prices = close
    amount = pd.DataFrame(
        1e8, index=prices.index, columns=prices.columns
    )
    signals = (close / close.shift(5) - 1).fillna(0.0)

    result = bt.capacity_analysis(
        signals=signals,
        prices=prices,
        amount=amount,
        normalize="long_only",
        participation_rate=0.1,
        capital_levels=[1e6, 1e8],
    )
    json.dumps(result, allow_nan=False)
    assert all(np.isfinite(lv["mean_participation"]) for lv in result["levels"])
    assert all(np.isfinite(lv["p95_participation"]) for lv in result["levels"])


def test_workflow_jsonable_handles_numpy_and_nan():
    value = {
        "df": pd.DataFrame({"a": [1, np.nan], "b": np.array([2, 3], dtype="int64")}),
        "series": pd.Series([np.inf, -np.inf, 1.5]),
        "np_int": np.int64(4),
        "np_nan": np.float64(np.nan),
        "nested": [np.float64(2.5), pd.Timestamp("2024-01-02")],
    }
    out = _jsonable(value)
    json.dumps(out, allow_nan=False)
    assert out["df"]["data"][1][0] is None
    assert out["series"]["data"][:2] == [None, None]
    assert out["np_int"] == 4
    assert out["np_nan"] is None


def test_run_strategy_request_exposes_execute_at():
    req = RunStrategyRequest(signal_code="x", execute_at="next_open")
    assert req.execute_at == "next_open"


def test_backtest_semaphore_factory_returns_semaphore():
    # 变量与函数同名会让 def 把变量重绑为函数对象，这是历史 500 的根因
    sem = _backtest_sem()
    assert isinstance(sem, asyncio.Semaphore)


def test_capacity_assumptions_include_adv_window_and_lot_size():
    _rets, close = _panel()
    result = bt.capacity_analysis(
        signals=close.pct_change().fillna(0.0),
        prices=close,
        amount=pd.DataFrame(1e8, index=close.index, columns=close.columns),
        adv_window=10,
        lot_size=100,
    )
    assert result["adv_window"] == 10
    assert result["lot_size"] == 100
    assert any("整手" in a for a in result["assumptions"])


def test_sandbox_status_reports_unreachable_server(monkeypatch):
    monkeypatch.setattr(settings, "sandbox_enabled", True)
    monkeypatch.setattr(settings, "sandbox_server_domain", "127.0.0.1:1")
    _status_cache.update({"ts": 0.0, "server_reachable": True, "probe_error": ""})

    status = asyncio.run(sandbox_status())
    assert status["active"] is False
    assert status["server_reachable"] is False
    assert "不可达" in status["note"] or "端口" in status["note"]
