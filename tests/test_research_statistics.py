"""Isolated, synthetic pytest panels; no production data or execution services."""

import json

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from statsmodels.regression.linear_model import OLS

from backend.services.research_statistics import (
    block_mean_interval,
    decay_summary,
    forward_returns,
    hac_mean,
    rank_ic,
    residualize,
    score_to_signal,
)


@pytest.fixture(scope="module", autouse=True)
def _init_db_session(tmp_path_factory):
    # Shadow tests/conftest.py's DB-initializing fixture for this pure test module.
    # Even accidental DB use is redirected to a disposable path, never real data.
    from backend import database

    original = database.DB_PATH
    database.DB_PATH = tmp_path_factory.mktemp("research-statistics") / "isolated.db"
    try:
        yield
    finally:
        database.DB_PATH = original


def _json_safe(report):
    return json.loads(json.dumps(report, allow_nan=False))


def _ar_series(n=600):
    rng = np.random.default_rng(431)
    innovations = rng.normal(size=n)
    values = np.zeros(n)
    for i in range(1, n):
        values[i] = 0.9 * values[i - 1] + innovations[i]
    return pd.Series(values + 0.2, index=pd.bdate_range("2024-01-02", periods=n))


def _style_panels():
    dates = pd.bdate_range("2024-01-02", periods=3)
    tickers = [f"S{i:02d}" for i in range(40)]
    size = pd.DataFrame(np.tile(np.arange(1.0, 41.0), (3, 1)), dates, tickers)
    industry = pd.DataFrame(np.tile(["A", "B", "C", "D"] * 10, (3, 1)), dates, tickers)
    effect = industry.replace({"A": "2", "B": "-1", "C": "0.5", "D": "-0.5"}).astype(
        float
    )
    factor = 4.0 + 0.75 * size + effect
    return factor, {"size": size}, industry


def test_forward_returns_hand_calculated_t_plus_one_and_diagnostic():
    dates = pd.date_range("2024-01-01", periods=6)
    returns = pd.DataFrame({"A": [np.nan, 0.1, 0.2, -0.1, 0.3, 0.4]}, index=dates)
    original = returns.copy(deep=True)
    actual = forward_returns(returns, horizon=2)
    expected = pd.DataFrame({"A": [0.08, 0.17, 0.82, np.nan, np.nan, np.nan]}, dates)
    pd.testing.assert_frame_equal(actual, expected)
    diagnostic = forward_returns(returns, horizon=2, execution_lag=0)
    np.testing.assert_allclose(diagnostic.iloc[:4, 0], [0.32, 0.08, 0.17, 0.82])
    assert diagnostic.iloc[-2:].isna().all().all()
    one_day = forward_returns(returns, horizon=1)
    np.testing.assert_allclose(one_day.iloc[:4, 0], returns.iloc[2:, 0])
    pd.testing.assert_frame_equal(returns, original)
    _json_safe(json.loads(actual.to_json()))


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf])
def test_forward_returns_requires_every_contiguous_return(invalid):
    returns = pd.DataFrame({"A": [0.9, 0.1, invalid, 0.2, 0.3, 0.4]})
    result = forward_returns(returns, horizon=2, execution_lag=0)
    assert result.iloc[:2].isna().all().all()
    assert result.iloc[2, 0] == pytest.approx(0.56)
    assert result.iloc[3, 0] == pytest.approx(0.82)
    assert result.iloc[-2:].isna().all().all()


@pytest.mark.parametrize(
    "horizon, lag", [(0, 1), (-1, 0), (1, -1), (1.5, 0), (True, 0)]
)
def test_forward_returns_rejects_invalid_horizon_or_lag(horizon, lag):
    with pytest.raises((TypeError, ValueError)):
        forward_returns(pd.DataFrame({"A": [0.1, 0.2]}), horizon, lag)


@pytest.mark.parametrize("index", [[1, 1], [2, 1]])
def test_forward_returns_requires_strict_time_index(index):
    with pytest.raises(ValueError):
        forward_returns(pd.DataFrame({"A": [0.1, 0.2]}, index=index), 1)


def test_forward_returns_empty_and_unavailable_horizon():
    empty = pd.DataFrame(columns=["A"], dtype=float)
    pd.testing.assert_frame_equal(forward_returns(empty, 2), empty)
    assert forward_returns(pd.DataFrame({"A": [0.1, 0.2]}), 3).isna().all().all()


def test_rank_ic_joint_finite_samples_mask_alignment_and_preserved_dates():
    factor = pd.DataFrame(
        [[1, 2, 3, 4], [4, 3, 2, 1], [1, 3, 2, 4]], columns=list("ABCD")
    )
    labels = pd.DataFrame([[3, 2, 1, np.inf], [1, 2, 3, 4]], columns=list("ABCD"))
    mask = pd.DataFrame([[True, True, True], [False, True, True]], columns=list("CAB"))
    snapshots = [frame.copy(deep=True) for frame in (factor, labels, mask)]
    result = rank_ic(factor, labels, mask, min_stocks=3)
    assert result.iloc[0] == pytest.approx(-1)
    assert result.iloc[1:].isna().all()
    assert result.index.equals(factor.index)
    for actual, original in zip((factor, labels, mask), snapshots):
        pd.testing.assert_frame_equal(actual, original)


@pytest.mark.parametrize("constant_side", ["factor", "labels"])
def test_rank_ic_constant_is_missing_not_zero(constant_side):
    factor = pd.DataFrame([[1, 2, 3], [3, 2, 1]])
    labels = pd.DataFrame([[4, 5, 6], [4, 5, 6]])
    if constant_side == "factor":
        factor.iloc[0] = 7
    else:
        labels.iloc[0] = 7
    result = rank_ic(factor, labels, min_stocks=3)
    assert np.isnan(result.iloc[0])
    assert result.iloc[1] == pytest.approx(-1)


def test_rank_ic_ties_and_default_minimum():
    factor = pd.DataFrame([[1, 1, 3, 4], [1, 2, np.nan, 4]])
    labels = pd.DataFrame([[4, 2, 2, 1], [1, 2, 3, np.inf]])
    result = rank_ic(factor, labels, min_stocks=3)
    assert result.iloc[0] == pytest.approx(
        stats.spearmanr(factor.iloc[0], labels.iloc[0]).statistic
    )
    assert np.isnan(result.iloc[1])
    assert rank_ic(factor, labels).isna().all()
    assert rank_ic(factor.iloc[:0], labels).empty


def test_hac_matches_statsmodels_with_one_sided_null_and_sorted_time():
    series = _ar_series()
    original = series.copy(deep=True)
    result = hac_mean(series.iloc[::-1], max_lags=12, alpha=0.1, null_mean=0.1)
    fit = OLS(series.to_numpy(), np.ones((len(series), 1))).fit(
        cov_type="HAC", cov_kwds={"maxlags": 12, "use_correction": True}
    )
    assert result["status"] == "ok"
    assert result["n_obs"] == len(series)
    assert result["lags"] == 12
    assert result["mean"] == pytest.approx(fit.params[0])
    assert result["se"] == pytest.approx(fit.bse[0])
    np.testing.assert_allclose(
        [result["ci_low"], result["ci_high"]], fit.conf_int(alpha=0.1)[0]
    )
    assert result["p_value"] == pytest.approx(
        stats.norm.sf((fit.params[0] - 0.1) / fit.bse[0])
    )
    assert "finite-sample" in result["note"]
    pd.testing.assert_series_equal(series, original)
    _json_safe(result)


def test_hac_autocorrelation_is_not_iid_standard_error():
    series = _ar_series()
    result = hac_mean(series, max_lags=12)
    iid_se = series.std(ddof=1) / np.sqrt(len(series))
    assert result["se"] > 2 * iid_se
    assert result["p_value"] > stats.norm.sf(result["mean"] / iid_se)


def test_hac_finite_mask_and_gap_note_matches_explicit_compression():
    series = _ar_series(150)
    series.iloc[15:18] = np.nan
    series.iloc[50] = np.inf
    result = hac_mean(series, max_lags=8)
    finite = series[np.isfinite(series)]
    expected = hac_mean(finite, max_lags=8)
    assert result["n_obs"] == 146
    assert result["n_missing"] == 4
    assert result["n_gaps"] == 2
    assert "bridges 2" in result["note"]
    assert result["se"] == expected["se"]
    _json_safe(result)


@pytest.mark.parametrize(
    "values, expected_status, expected_mean",
    [
        ([], "insufficient_data", None),
        ([np.nan, np.inf], "insufficient_data", None),
        ([1.0] * 10, "insufficient_data", 1.0),
        ([0.0] * 80, "degenerate", 0.0),
        ([0.1] * 80, "degenerate", 0.1),
    ],
)
def test_hac_no_evidence_uses_null(values, expected_status, expected_mean):
    result = hac_mean(pd.Series(values, dtype=float), max_lags=5)
    assert result["status"] == expected_status
    if expected_mean is None:
        assert result["mean"] is None
    else:
        assert result["mean"] == pytest.approx(expected_mean)
    for field in ("se", "ci_low", "ci_high", "p_value"):
        assert result[field] is None
    _json_safe(result)


def test_hac_does_not_shorten_unsupported_lags():
    result = hac_mean(_ar_series(60), max_lags=60)
    assert result["status"] == "insufficient_data"
    assert result["lags"] == 60
    assert result["reason"] == "insufficient_lag_support"
    assert result["se"] is None


def test_bootstrap_reproducible_matches_moving_blocks_not_iid():
    series = _ar_series(120)
    original = series.copy(deep=True)
    result = block_mean_interval(series, block_length=8, n_resamples=999, seed=17)
    assert result == block_mean_interval(series, 8, n_resamples=999, seed=17)
    rng = np.random.default_rng(17)
    means = []
    raw = series.to_numpy()
    for _ in range(999):
        starts = rng.choice(np.arange(113), size=15, replace=True)
        sample = np.concatenate([raw[start : start + 8] for start in starts])
        means.append(sample.mean())
    assert result["status"] == "ok"
    np.testing.assert_allclose(
        [result["ci_low"], result["ci_high"]], np.quantile(means, [0.025, 0.975])
    )
    assert result["se"] == pytest.approx(np.std(means, ddof=1))
    assert result["se"] > 1.5 * series.std(ddof=1) / np.sqrt(len(series))
    assert result["p_value"] is None
    assert "Descriptive" in result["note"]
    pd.testing.assert_series_equal(series, original)
    _json_safe(result)


def test_bootstrap_does_not_change_global_rng():
    state = np.random.get_state()
    block_mean_interval(_ar_series(80), 5, n_resamples=20)
    after = np.random.get_state()
    assert state[0] == after[0]
    np.testing.assert_array_equal(state[1], after[1])
    assert state[2:] == after[2:]


def test_bootstrap_does_not_join_missing_gaps_into_blocks():
    series = pd.Series(np.tile([1.0, np.nan, 2.0, np.inf], 40))
    result = block_mean_interval(series, 2)
    assert result["n_obs"] == 80
    assert result["status"] == "insufficient_data"
    assert result["reason"] == "insufficient_contiguous_blocks"
    assert result["ci_low"] is None
    _json_safe(result)


@pytest.mark.parametrize(
    "values, length, status",
    [
        ([], 5, "insufficient_data"),
        ([np.nan, np.inf], 5, "insufficient_data"),
        (list(range(59)), 5, "insufficient_data"),
        (list(range(60)), 31, "insufficient_data"),
        ([0.0] * 80, 5, "degenerate"),
        ([0.1] * 80, 5, "degenerate"),
    ],
)
def test_bootstrap_no_evidence_returns_null(values, length, status):
    result = block_mean_interval(pd.Series(values, dtype=float), length)
    assert result["status"] == status
    assert result["ci_low"] is None
    assert result["ci_high"] is None
    assert result["p_value"] is None
    _json_safe(result)


@pytest.mark.parametrize("invalid", [0, -1, 1, 1.0, True])
def test_bootstrap_requires_actual_time_blocks(invalid):
    with pytest.raises((TypeError, ValueError)):
        block_mean_interval(_ar_series(60), invalid)


@pytest.mark.parametrize(
    "function, argument",
    [(hac_mean, "max_lags"), (block_mean_interval, "block_length")],
)
@pytest.mark.parametrize("alpha", [0, 1, np.nan, np.inf])
def test_intervals_validate_alpha(function, argument, alpha):
    with pytest.raises(ValueError):
        function(_ar_series(60), **{argument: 5}, alpha=alpha)


def test_residualize_pure_style_and_industry_explanation_near_zero():
    factor, styles, industry = _style_panels()
    snapshots = [
        factor.copy(deep=True),
        styles["size"].copy(deep=True),
        industry.copy(deep=True),
    ]
    result, metadata = residualize(factor, styles, industry)
    np.testing.assert_allclose(result.to_numpy(), 0.0, atol=1e-12)
    assert metadata["n_valid"] == factor.size
    assert set(metadata["coverage_by_date"].values()) == {1.0}
    assert metadata["industry"] == "included"
    for actual, original in zip((factor, styles["size"], industry), snapshots):
        pd.testing.assert_frame_equal(actual, original)
    _json_safe(metadata)


@pytest.mark.parametrize("missing", ["size", "industry"])
def test_residualize_missing_reference_date_has_no_fallback(missing):
    factor, styles, industry = _style_panels()
    if missing == "size":
        styles["size"] = styles["size"].iloc[1:]
    else:
        industry = industry.iloc[1:]
    result, metadata = residualize(factor, styles, industry)
    assert result.iloc[0].isna().all()
    assert result.iloc[1:].notna().all().all()
    diagnostic = metadata["diagnostics_by_date"][str(factor.index[0])]
    assert diagnostic["reason"] == "missing_reference_date"
    assert diagnostic["missing_controls"] == [missing]
    assert metadata["coverage_by_date"][str(factor.index[0])] == 0
    _json_safe(metadata)


@pytest.mark.parametrize("missing", ["size", "industry"])
def test_residualize_missing_reference_column_excludes_stock(missing):
    factor, styles, industry = _style_panels()
    if missing == "size":
        styles["size"] = styles["size"].drop(columns="S00")
    else:
        industry = industry.drop(columns="S00")
    result, metadata = residualize(factor, styles, industry)
    assert result["S00"].isna().all()
    np.testing.assert_allclose(result.drop(columns="S00"), 0.0, atol=1e-12)
    assert metadata["n_valid"] == 117


def test_residualize_styles_only_explicitly_omits_industry_and_no_controls_invalid():
    factor, styles, _ = _style_panels()
    result, metadata = residualize(2 + styles["size"] * 3, styles, None)
    np.testing.assert_allclose(result, 0.0, atol=1e-12)
    assert metadata["industry"] == "omitted"
    invalid, metadata = residualize(factor, {}, None)
    assert invalid.isna().all().all()
    assert metadata["n_valid"] == 0
    assert {d["reason"] for d in metadata["diagnostics_by_date"].values()} == {
        "no_controls"
    }
    _json_safe(metadata)


def test_residualize_rank_deficiency_is_declared_not_raw_fallback():
    factor, styles, industry = _style_panels()
    styles["duplicate"] = 7 + 2 * styles["size"]
    result, metadata = residualize(factor, styles, industry)
    assert result.isna().all().all()
    assert metadata["rank_policy"] == "reject_rank_deficient"
    assert {d["reason"] for d in metadata["diagnostics_by_date"].values()} == {
        "rank_deficient"
    }


def test_residualize_requires_positive_residual_degrees_of_freedom():
    factor = pd.DataFrame([[1.0, 2.0, 3.0]])
    industry = pd.DataFrame([["A", "B", "C"]])
    result, metadata = residualize(factor, {}, industry, min_stocks=3)
    assert result.isna().all().all()
    assert metadata["diagnostics_by_date"]["0"]["reason"] == "insufficient_dof"


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf])
def test_residualize_joint_finite_styles_and_factor(invalid):
    factor, styles, industry = _style_panels()
    styles["size"].iloc[:, 0] = invalid
    factor.iloc[:, 1] = invalid
    result, metadata = residualize(factor, styles, industry)
    assert result.iloc[:, :2].isna().all().all()
    np.testing.assert_allclose(result.iloc[:, 2:], 0.0, atol=1e-12)
    assert metadata["n_valid"] == 114


def test_residualize_insufficient_stocks_and_failed_regression(monkeypatch):
    factor, styles, industry = _style_panels()
    result, _ = residualize(factor.iloc[:, :29], styles, industry)
    assert result.isna().all().all()

    def fail(*args, **kwargs):
        raise np.linalg.LinAlgError("test-only failure")

    monkeypatch.setattr(np.linalg, "lstsq", fail)
    result, metadata = residualize(factor, styles, industry)
    assert result.isna().all().all()
    assert {d["reason"] for d in metadata["diagnostics_by_date"].values()} == {
        "regression_failed"
    }
    _json_safe(metadata)


def test_score_to_signal_stable_ticker_ties_masks_and_hold_until_rebalance():
    scores = pd.DataFrame(
        [
            [5, 5, 5, np.inf],
            [0, 20, 0, 0],
            [0, 0, 20, 0],
            [9, 8, -2, -3],
            [0, 20, 0, 0],
            [0, 0, 0, 20],
        ],
        columns=["C", "B", "A", "D"],
    )
    mask = pd.DataFrame(
        [[True, True, True], [False, False, False], [False, False, True]],
        index=[0, 1, 3],
        columns=["C", "B", "A"],
    )
    originals = [scores.copy(deep=True), mask.copy(deep=True)]
    result = score_to_signal(scores, top_n=2, rebalance_days=3, mask=mask)
    expected = pd.DataFrame(
        [[0, 1, 1, 0]] * 3 + [[0, 0, 1, 0]] * 3,
        columns=scores.columns,
        dtype=np.int8,
    )
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(
        score_to_signal(scores[scores.columns[::-1]], 2, 3, mask)[scores.columns],
        result,
    )
    for actual, original in zip((scores, mask), originals):
        pd.testing.assert_frame_equal(actual, original)
    assert set(np.unique(result)) <= {0, 1}
    _json_safe(json.loads(result.to_json()))


def test_score_to_signal_missing_rebalance_mask_clears_targets_and_no_direction_flip():
    scores = pd.DataFrame([[-1, -2], [-100, 100], [-1, -2]], columns=["A", "B"])
    mask = pd.DataFrame([[True, True]], index=[0], columns=scores.columns)
    result = score_to_signal(scores, 1, rebalance_days=2, mask=mask)
    np.testing.assert_array_equal(result, [[1, 0], [1, 0], [0, 0]])
    assert score_to_signal(scores * np.nan, 5).to_numpy().sum() == 0
    assert score_to_signal(scores.iloc[:0], 1).empty


@pytest.mark.parametrize(
    "kwargs", [{"top_n": 0}, {"top_n": -1}, {"top_n": 1, "rebalance_days": 0}]
)
def test_score_to_signal_validates_counts(kwargs):
    with pytest.raises(ValueError):
        score_to_signal(pd.DataFrame([[1, 2]]), **kwargs)


@pytest.mark.parametrize("sign", [1, -1])
def test_decay_relative_half_crossing_is_holding_horizon_not_calendar_lifetime(sign):
    curve = [
        {"horizon": 10, "ic": 0.02 * sign},
        {"horizon": 1, "ic": 0.1 * sign},
        {"horizon": 5, "ic": 0.06 * sign},
    ]
    original = [dict(point) for point in curve]
    result = decay_summary(curve)
    assert result["half_life"] == pytest.approx(6.25)
    assert result["crossing_horizon"] == 10
    assert result["initial_horizon"] == 1
    assert result["half_initial_ic"] == pytest.approx(0.05 * sign)
    assert result["reason"] is None
    assert "Not calendar lifetime" in result["note"]
    assert curve == original
    _json_safe(result)


@pytest.mark.parametrize(
    "ics, reason",
    [
        ([], "insufficient_data"),
        ([0.1], "insufficient_data"),
        ([0.1, 0.09, 0.08], "no_crossing"),
        ([0.1, 0.02, 0.03], "non_monotonic"),
        ([0.0, 0.0], "zero_initial_ic"),
        ([None, 0.01], "missing_ic"),
        ([0.1, None, 0.01], "missing_ic"),
        ([0.1, np.inf], "missing_ic"),
    ],
)
def test_decay_unavailable_is_null_with_reason(ics, reason):
    result = decay_summary([{"horizon": i + 1, "ic": ic} for i, ic in enumerate(ics)])
    assert result["half_life"] is None
    assert result["crossing_horizon"] is None
    assert result["reason"] == reason
    _json_safe(result)


def test_decay_exact_half_plateau_and_duplicate_horizon():
    result = decay_summary(
        [
            {"horizon": 2, "ic": 0.2},
            {"horizon": 4, "ic": 0.1},
            {"horizon": 8, "ic": 0.1},
        ]
    )
    assert result["half_life"] == 4
    with pytest.raises(ValueError):
        decay_summary([{"horizon": 1, "ic": 0.2}, {"horizon": 1, "ic": 0.1}])
