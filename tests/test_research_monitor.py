"""纯监测接口回归；合成序列仅作为测试夹具，不代表真实研究成绩。"""

import json
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from backend import database
from backend.services import research_monitor as monitor


@pytest.fixture(scope="module", autouse=True)
def _init_db_session(tmp_path_factory):
    """覆盖 conftest 的建库 fixture：纯计算测试不访问业务库。"""
    original = database.DB_PATH
    database.DB_PATH = tmp_path_factory.mktemp("research-monitor") / "test.db"
    try:
        yield
    finally:
        database.DB_PATH = original


def _series(values, start="2024-01-02"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)))


def _empty():
    return pd.Series(index=pd.DatetimeIndex([]), dtype=float)


def _observations(n=200, mean=0.0002):
    # 确定性且非退化，避免把常数样本当成可信显著性。
    return _series(mean + 0.01 * np.sin(np.arange(n) * 1.7))


def _evidence(observations, baseline=None, **overrides):
    params = {
        "horizon": 5, "window": 60, "review_every": 20, "alpha": 0.05,
        "trial_budget": 4, "min_obs": 60,
    }
    params.update(overrides)
    return monitor.monitor_evidence(
        _empty() if baseline is None else baseline, observations, **params,
    )


def test_history_states_prefix_invariance_and_index():
    returns = 0.002 + 0.008 * np.sin(np.arange(250) * 0.8)
    close = _series(100 * np.exp(np.cumsum(returns)))
    original = close.copy(deep=True)
    states = monitor.history_states(close)
    assert states.index.equals(close.index)
    for length in (0, 20, 59, 60, 79, 80, 81, 105, 200, 250):
        assert_series_equal(monitor.history_states(close.iloc[:length]), states.iloc[:length])
    assert_series_equal(close, original)


def test_history_requires_sixty_prior_volatility_observations():
    close = _series(np.full(100, 100.0))
    states = monitor.history_states(close)
    assert all(value is None for value in states.iloc[:80])
    assert states.iloc[80] == "range_normal"
    assert states.iloc[80:].eq("range_normal").all()


@pytest.mark.parametrize("drift, expected", [(0.003, "up"), (-0.003, "down"), (0, "range")])
def test_history_trend_and_strictly_historical_volatility(drift, expected):
    close = _series(100 * np.exp(np.cumsum(drift + 0.0001 * np.sin(np.arange(150)))))
    states = monitor.history_states(close)
    assert states.iloc[-1].startswith(expected + "_")
    vol = np.log(close).diff().rolling(20).std() * np.sqrt(250)
    expected_vol = "high" if vol.iloc[-1] > vol.iloc[:-1].median() else "normal"
    assert states.iloc[-1] == expected + "_" + expected_vol


def test_history_volatility_spike_and_missing_prices_are_not_filled():
    close = _series(100 * np.exp(np.cumsum(0.002 + 0.0001 * np.sin(np.arange(180)))))
    close.iloc[100] *= 1.2
    assert monitor.history_states(close).iloc[100] == "up_high"
    close.iloc[120] = np.nan
    close.iloc[150] = np.inf
    close.iloc[160] = 0
    states = monitor.history_states(close)
    assert all(value is None for value in states.iloc[120:])


def test_conditional_alignment_finite_samples_and_shrinkage():
    values = _series([1.0, 3.0, -4.0, np.nan, np.inf, -np.inf, 10.0])
    states = pd.Series(
        ["up_normal", "down_high", "down_high", "up_normal", "up_normal", "down_high"],
        index=values.index[[0, 1, 2, 3, 4, 5]],
    )
    rows = monitor.conditional_summary(values, states, min_obs=2, prior_strength=2)
    by_state = {row["state"]: row for row in rows}
    # 全体有限值均值 2.5；未知状态的最后一个值仍进入整体先验，但不伪造 range。
    assert set(by_state) == {"up_normal", "down_high"}
    assert by_state["up_normal"] == {
        "state": "up_normal", "n_obs": 1, "mean": 1.0, "shrunk_mean": 2.0, "eligible": False,
    }
    assert by_state["down_high"] == {
        "state": "down_high", "n_obs": 2, "mean": -0.5, "shrunk_mean": 1.0, "eligible": True,
    }
    assert all("p_value" not in row and "ci_low" not in row for row in rows)


def test_conditional_missing_or_insufficient_states_remain_unknown():
    values = _series([-0.1] * 61)
    states = pd.Series([None] * 2 + ["down_high"] * 59, index=values.index)
    row = monitor.conditional_summary(values, states)[0]
    assert row["n_obs"] == 59 and row["eligible"] is False
    assert row["mean"] == pytest.approx(-0.1)
    assert monitor.conditional_summary(values, pd.Series(None, index=states.index, dtype=object)) == []
    assert monitor.conditional_summary(values * np.nan, states) == []
    assert monitor.conditional_summary(_empty(), _empty()) == []


def test_ic_requires_horizon_plus_one_and_sixty_mature_signal_observations():
    ic = _series([-0.1] * 100)
    states = pd.Series("down_high", index=ic.index)
    result = monitor.causal_state_multipliers(ic, states, horizon=5)
    assert result.iloc[:65].eq(1).all()  # 第 60 个信号在位置 59+5+1 才成熟。
    assert result.iloc[65:].eq(0).all()
    assert result.index.equals(ic.index)


def test_ic_future_changes_and_prefixes_cannot_change_past_allocations():
    ic = _series(np.sin(np.arange(150)) * 0.1 - 0.04)
    states = pd.Series(np.where(np.arange(150) % 3, "range_normal", "up_high"), index=ic.index)
    expected = monitor.causal_state_multipliers(ic, states, 3, min_obs=10)
    for length in (0, 20, 60, 100):
        actual = monitor.causal_state_multipliers(ic.iloc[:length], states.iloc[:length], 3, min_obs=10)
        assert_series_equal(actual, expected.iloc[:length])
    changed = ic.copy()
    changed.iloc[80:] = 1.0
    actual = monitor.causal_state_multipliers(changed, states, 3, min_obs=10)
    assert_series_equal(actual.iloc[:84], expected.iloc[:84])


def test_ic_missing_dates_are_reindexed_before_shifting():
    dates = pd.bdate_range("2024-01-02", periods=8)
    states = pd.Series("down_high", index=dates)
    sparse = pd.Series([-0.2, np.nan, -0.2], index=dates[[0, 2, 3]])
    result = monitor.causal_state_multipliers(sparse, states, 1, min_obs=2, prior_strength=0)
    assert result.tolist() == [1, 1, 1, 1, 1, 0, 0, 0]
    assert_series_equal(
        result,
        monitor.causal_state_multipliers(sparse.reindex(dates), states, 1, min_obs=2, prior_strength=0),
    )


def test_ic_uses_signal_state_not_maturity_state_and_keeps_unknown_state():
    ic = _series([-0.2, np.nan, np.nan, np.nan, np.nan])
    states = pd.Series(["down_high", "up_normal", "up_normal", "down_high", None], index=ic.index)
    result = monitor.causal_state_multipliers(ic, states, 1, min_obs=1, prior_strength=0)
    assert result.tolist() == [1, 1, 1, 0, 1]
    assert monitor.causal_state_multipliers(ic, pd.Series(None, index=states.index, dtype=object), 1).eq(1).all()


def test_ic_shrinkage_uses_only_mature_global_history():
    ic = _series([-0.1, -0.1, 0.9, 0.9, 0.0, 0.0, 0.0])
    states = pd.Series(["bad", "bad", "good", "good", "bad", "bad", "bad"], index=ic.index)
    raw = monitor.causal_state_multipliers(ic, states, 1, min_obs=2, prior_strength=0)
    shrunk = monitor.causal_state_multipliers(ic, states, 1, min_obs=2, prior_strength=60)
    assert raw.iloc[4] == 0 and shrunk.iloc[4] == 1
    # 未知信号状态的已成熟 IC 也进入整体先验，但不进入任一状态样本。
    states.iloc[2:4] = None
    assert monitor.causal_state_multipliers(ic, states, 1, min_obs=2).iloc[4] == 1


@pytest.mark.parametrize("n", [0, 1, 59])
def test_monitor_insufficient_new_data_never_retires(n):
    result = _evidence(_observations(n))
    assert result["status"] == "insufficient_data"
    assert result["recommendation"] is None
    assert result["review_number"] is None and result["review_date"] is None
    assert result["alpha_spent"] is None and result["mean_change"] is None
    assert result["n_new_observations"] == n and result["n_used"] == 0
    for key in ("mean", "se", "ci_low", "ci_high", "p_value", "lags"):
        assert result["current"][key] is None
    json.dumps(result, allow_nan=False)


def test_monitor_frozen_baseline_is_not_counted_as_new_evidence():
    baseline = _series(np.sin(np.arange(100)) * 0.01, start="2022-01-03")
    result = _evidence(_empty(), baseline)
    assert result["status"] == "insufficient_data"
    assert result["n_new_observations"] == 0 and result["review_number"] is None
    assert result["baseline"]["n_obs"] == 100
    assert result["mean_change"] is None


def test_monitor_waits_for_first_sufficient_grid_and_uses_last_completed_window():
    observations = _observations(140)
    before = _evidence(observations.iloc[:60], window=61)
    between = _evidence(observations.iloc[:79], window=61)
    assert before["review_number"] is None
    assert between["review_number"] is None
    first = _evidence(observations.iloc[:80], window=61)
    assert first["review_number"] == 1
    assert first["review_date"] == observations.index[79].isoformat()
    assert first["n_used"] == 61
    assert first["current"]["mean"] == pytest.approx(observations.iloc[19:80].mean())
    partial = observations.iloc[:99].copy()
    partial.iloc[80:] = -1000.0
    repeated = _evidence(partial, window=61)
    for key in ("review_number", "review_date", "alpha_spent", "current", "status", "mean_change"):
        assert repeated[key] == first[key]
    assert _evidence(observations.iloc[:100], window=61)["review_number"] == 2
    assert _evidence(observations.iloc[:80], window=61) == first


def test_monitor_nan_dates_do_not_create_new_reviews_and_gaps_remain_visible():
    observations = _observations(90)
    observations.iloc[[5, 8, 10]] = [np.nan, np.inf, -np.inf]
    # 63 个日期恰有 60 个有效新观察；日期缺失保留到 HAC 报告。
    result = _evidence(observations.iloc[:63])
    assert result["review_number"] == 1
    assert result["review_date"] == observations.index[62].isoformat()
    assert result["n_new_observations"] == 60
    assert result["current"]["n_missing"] == 3
    assert result["current"]["n_gaps"] == 3
    missing_tail = observations.copy()
    missing_tail.iloc[63:] = np.nan
    assert _evidence(missing_tail) == result
    assert _evidence(observations.iloc[:62])["review_number"] is None


def test_monitor_alpha_spending_decreases_and_respects_trial_budget():
    observations = _observations(500)
    spending = []
    for j, n in enumerate(range(60, 501, 20), start=1):
        result = _evidence(observations.iloc[:n])
        assert result["review_number"] == j
        assert result["alpha_spent"] == pytest.approx(0.05 / (4 * j * (j + 1)))
        spending.append(result["alpha_spent"])
    assert all(a > b for a, b in pairwise(spending))
    assert sum(spending) < 0.05 / 4


def test_monitor_hac_receives_horizon_spent_alpha_and_effect(monkeypatch):
    from backend.services import research_statistics

    original = research_statistics.hac_mean
    calls = []

    def record(series, **kwargs):
        calls.append((series.copy(), kwargs))
        return original(series, **kwargs)

    monkeypatch.setattr(research_statistics, "hac_mean", record)
    observations = _observations(75)
    result = _evidence(observations, horizon=12, minimum_effect=0.001)
    assert len(calls) == 1
    selected, params = calls[0]
    assert_series_equal(selected, observations.iloc[:60])
    assert params == {"max_lags": 12, "alpha": 0.05 / 8, "null_mean": 0.001, "min_obs": 60}
    assert result["current"]["lags"] >= 12
    assert "HAC" in result["note"] and "近似" in result["note"]


def test_monitor_only_upper_interval_below_effect_requests_manual_watch():
    negative = _evidence(_observations(60, mean=-0.1))
    assert negative["current"]["ci_high"] < 0
    assert negative["status"] == "review_needed" and negative["recommendation"] == "watch"
    inconclusive = _evidence(_observations(60, mean=0))
    assert inconclusive["current"]["p_value"] > 0.05
    assert inconclusive["status"] == "monitoring" and inconclusive["recommendation"] is None
    positive = _evidence(_observations(60, mean=0.1))
    assert positive["status"] == "monitoring" and positive["recommendation"] is None
    below_minimum = _evidence(_observations(60, mean=0.01), minimum_effect=0.1)
    assert below_minimum["status"] == "review_needed"
    assert "registry.review" in negative["note"]


def test_monitor_baseline_change_is_descriptive_and_frozen():
    baseline = _series(0.03 + np.sin(np.arange(100)) * 0.01, start="2022-01-03")
    observations = _observations(80)
    first = _evidence(observations.iloc[:60], baseline)
    second = _evidence(observations, baseline)
    assert first["baseline"] == second["baseline"]
    assert second["mean_change"] == pytest.approx(observations.iloc[20:80].mean() - baseline.mean())
    assert "描述" in second["note"] and "不构成因果" in second["note"]
    json.dumps(second, allow_nan=False)


@pytest.mark.parametrize("overrides", [{"window": 20}, {"horizon": 60}])
def test_monitor_unsupported_window_or_hac_lags_never_produce_watch(overrides):
    result = _evidence(_observations(100, mean=-0.1), **overrides)
    assert result["status"] == "insufficient_data" and result["recommendation"] is None
    assert result["current"]["ci_high"] is None


def test_monitor_rejects_duplicate_unordered_or_non_new_dates():
    observations = _observations(100)
    with pytest.raises(ValueError, match="unique"):
        _evidence(pd.concat([observations.iloc[:1], observations]))
    with pytest.raises(ValueError, match="ordered"):
        _evidence(observations.iloc[::-1])
    with pytest.raises(ValueError, match="after the frozen holdout"):
        _evidence(observations, observations.iloc[:60])
    with pytest.raises(ValueError, match="unique"):
        _evidence(observations, pd.Series([1.0], index=[pd.NaT]))


@pytest.mark.parametrize("overrides", [
    {"review_every": 0}, {"trial_budget": 0}, {"window": 0}, {"min_obs": 0},
    {"horizon": -1}, {"alpha": 0}, {"alpha": 1}, {"alpha": np.nan},
    {"minimum_effect": np.inf}, {"window": 1.5}, {"trial_budget": True},
])
def test_monitor_rejects_invalid_review_protocol(overrides):
    with pytest.raises(ValueError):
        _evidence(_empty(), **overrides)
