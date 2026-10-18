"""Pure, aligned research statistics; no data access, execution or direction selection.

Scalar reports contain JSON-native values (unavailable evidence is None). Panels
retain the required NaN sentinel; use pandas.to_json to serialize panels as null.
"""

from __future__ import annotations

from itertools import pairwise
from numbers import Integral, Real

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.regression.linear_model import OLS

__all__ = [
    "block_mean_interval",
    "decay_summary",
    "forward_returns",
    "hac_mean",
    "rank_ic",
    "residualize",
    "score_to_signal",
]


def _integer(value: int, name: str, minimum: int = 1) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer >= {minimum}")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return int(value)


def _alpha(value: float) -> float:
    if not np.isfinite(value) or not 0 < value < 1:
        raise ValueError("alpha must be finite and between 0 and 1")
    return float(value)


def _panel(frame: pd.DataFrame, name: str, ordered: bool = False) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a DataFrame")
    if not frame.index.is_unique or not frame.columns.is_unique:
        raise ValueError(f"{name} must have unique dates and tickers")
    if ordered and not frame.index.is_monotonic_increasing:
        raise ValueError(f"{name} index must be strictly increasing")


def _numbers(frame: pd.DataFrame | pd.Series) -> np.ndarray:
    return frame.to_numpy(dtype=float, na_value=np.nan, copy=True)


def _allowed(mask: pd.DataFrame | None, frame: pd.DataFrame) -> np.ndarray:
    if mask is None:
        return np.ones(frame.shape, dtype=bool)
    _panel(mask, "mask")
    # Only explicit True/1 permits selection; missing labels never grant access.
    return (
        mask.reindex(index=frame.index, columns=frame.columns)
        .eq(True)
        .fillna(False)
        .to_numpy(dtype=bool)
    )


def _finite_number(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def _series_values(series: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    if not isinstance(series, pd.Series):
        raise TypeError("series must be a Series")
    if not series.index.is_unique:
        raise ValueError("series must have unique time labels")
    values = _numbers(series.sort_index())
    return values, np.isfinite(values)


def _mean_report(values: np.ndarray) -> dict:
    with np.errstate(over="ignore", invalid="ignore"):
        mean = _finite_number(np.mean(values)) if len(values) else None
    return {
        "status": "insufficient_data",
        "n_obs": len(values),
        "mean": mean,
        "se": None,
        "ci_low": None,
        "ci_high": None,
        "p_value": None,
        "reason": None,
    }


def forward_returns(
    returns: pd.DataFrame, horizon: int, execution_lag: int = 1
) -> pd.DataFrame:
    """Label T with product(1 + r[T+lag+1:T+lag+h+1]) - 1.

    lag=0 is close T to close T+h (diagnostic); lag=1 enters after close
    T+1. Horizons count supplied rows, not calendar days. Every return in the
    window must be finite; neither missing rows nor incomplete tails are filled.
    """
    horizon = _integer(horizon, "horizon")
    execution_lag = _integer(execution_lag, "execution_lag", 0)
    _panel(returns, "returns", ordered=True)
    values = _numbers(returns)
    output = np.full(values.shape, np.nan)
    count = len(values) - horizon - execution_lag
    if count > 0:
        valid = np.ones((count, values.shape[1]), dtype=bool)
        gross = np.ones_like(valid, dtype=float)
        with np.errstate(over="ignore", invalid="ignore"):
            for offset in range(execution_lag + 1, execution_lag + horizon + 1):
                window = values[offset : offset + count]
                valid &= np.isfinite(window)
                gross *= 1.0 + window
            net = gross - 1.0
        output[:count] = np.where(valid & np.isfinite(net), net, np.nan)
    return pd.DataFrame(output, index=returns.index, columns=returns.columns)


def rank_ic(
    factor: pd.DataFrame,
    labels: pd.DataFrame,
    mask: pd.DataFrame | None = None,
    min_stocks: int = 30,
) -> pd.Series:
    """Daily cross-sectional Spearman IC on jointly finite, permitted stocks."""
    min_stocks = _integer(min_stocks, "min_stocks")
    _panel(factor, "factor")
    _panel(labels, "labels")
    x = _numbers(factor)
    y = _numbers(labels.reindex(index=factor.index, columns=factor.columns))
    valid = np.isfinite(x) & np.isfinite(y) & _allowed(mask, factor)
    output = np.full(len(factor), np.nan)
    for i in range(len(factor)):
        if int(valid[i].sum()) < max(2, min_stocks):
            continue
        a, b = x[i, valid[i]], y[i, valid[i]]
        if np.all(a == a[0]) or np.all(b == b[0]):
            continue
        output[i] = stats.spearmanr(a, b).statistic
    return pd.Series(output, index=factor.index, name="rank_ic")


def hac_mean(
    series: pd.Series,
    max_lags: int,
    alpha: float = 0.05,
    null_mean: float = 0,
    min_obs: int = 60,
) -> dict:
    """Intercept-only OLS with corrected Bartlett HAC and normal-approximation CI.

    max_lags is used exactly, never silently shortened. The caller must choose
    at least the label holding horizon; n <= max_lags cannot support inference.
    """
    lags = _integer(max_lags, "max_lags", 0)
    min_obs = _integer(min_obs, "min_obs")
    alpha = _alpha(alpha)
    if not np.isfinite(null_mean):
        raise ValueError("null_mean must be finite")
    raw, finite = _series_values(series)
    values = raw[finite]
    result = _mean_report(values)
    n = len(values)
    positions = np.flatnonzero(finite)
    n_gaps = int(np.sum(np.diff(positions) > 1))
    result.update(
        lags=lags,
        n_missing=int((~finite).sum()),
        n_gaps=n_gaps,
        null_mean=float(null_mean),
        note=(
            "HAC finite-sample normal approximation with Bartlett weights and "
            "use_correction=True; not iid. max_lags is used as supplied and must "
            "be at least the holding horizon; dependence beyond max_lags is not "
            "covered. n_obs <= max_lags returns insufficient_data, not shorter "
            "lags. Time labels are sorted; nonfinite observations are removed. "
            f"Compression bridges {n_gaps} missing-observation gap(s); lags then "
            "measure retained observations, not elapsed calendar time. Absent "
            "time labels cannot be inferred without a supplied trading calendar."
        ),
    )
    if n < min_obs or n <= lags:
        result["reason"] = "min_obs" if n < min_obs else "insufficient_lag_support"
        return result
    if n < 2 or result["mean"] is None or np.all(values == values[0]):
        result.update(status="degenerate", reason="constant_or_nonfinite_mean")
        return result
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        fit = OLS(values, np.ones((n, 1))).fit(
            cov_type="HAC", cov_kwds={"maxlags": lags, "use_correction": True}
        )
        mean, se = float(fit.params[0]), float(fit.bse[0])
        critical = stats.norm.ppf(1 - alpha / 2)
        low, high = mean - critical * se, mean + critical * se
        p_value = stats.norm.sf((mean - null_mean) / se) if se > 0 else np.nan
    if se <= 0 or not np.isfinite([mean, se, low, high, p_value]).all():
        result.update(status="degenerate", reason="invalid_hac_variance")
        return result
    result.update(
        status="ok",
        mean=mean,
        se=se,
        ci_low=float(low),
        ci_high=float(high),
        p_value=float(p_value),
    )
    return result


def block_mean_interval(
    series: pd.Series,
    block_length: int,
    alpha: float = 0.05,
    n_resamples: int = 999,
    seed: int = 0,
    min_obs: int = 60,
) -> dict:
    """Percentile moving-block bootstrap CI, never a pointwise iid bootstrap.

    Resample overlapping complete finite blocks, concatenate and truncate to
    n_obs. Blocks do not bridge explicit missing observations. This is a
    descriptive CI only, not another direction/parameter-selection test.
    """
    block_length = _integer(block_length, "block_length", 2)
    n_resamples = _integer(n_resamples, "n_resamples", 2)
    seed = _integer(seed, "seed", 0)
    min_obs = _integer(min_obs, "min_obs")
    alpha = _alpha(alpha)
    raw, finite = _series_values(series)
    values = raw[finite]
    result = _mean_report(values)
    n = len(values)
    result.update(
        block_length=block_length,
        n_resamples=n_resamples,
        seed=seed,
        method="moving_block_percentile",
        n_missing=int((~finite).sum()),
        note=(
            "Descriptive percentile moving-block bootstrap CI only; no extra "
            "selection test or p-value. Blocks preserve supplied sorted row "
            "order and never cross explicit nonfinite gaps. Finite runs shorter "
            "than block_length are excluded from resampling (the reported mean "
            "still uses all finite observations). Absent calendar labels are "
            "not inferred; interval validity depends on suitable block length "
            "and temporal stationarity."
        ),
    )
    if n < min_obs or n < block_length * 2:
        result["reason"] = "min_obs" if n < min_obs else "insufficient_blocks"
        return result
    # Use counts rather than compressing the series across missing time points.
    counts = np.concatenate(([0], np.cumsum(finite, dtype=np.int64)))
    starts = np.flatnonzero(
        counts[block_length:] - counts[:-block_length] == block_length
    )
    result["n_available_blocks"] = len(starts)
    if len(starts) < 2:
        result["reason"] = "insufficient_contiguous_blocks"
        return result
    if result["mean"] is None or np.all(values == values[0]):
        result.update(status="degenerate", reason="constant_or_nonfinite_mean")
        return result
    rng = np.random.default_rng(seed)
    n_blocks = (n + block_length - 1) // block_length
    offsets = np.arange(block_length)
    means = np.empty(n_resamples)
    with np.errstate(over="ignore", invalid="ignore"):
        for i in range(n_resamples):
            sampled = rng.choice(starts, size=n_blocks, replace=True)
            sample = raw[(sampled[:, None] + offsets).ravel()[:n]]
            means[i] = np.mean(sample)
        low, high = np.quantile(means, [alpha / 2, 1 - alpha / 2])
        se = np.std(means, ddof=1)
    if not np.isfinite([low, high, se]).all() or se <= 0:
        result.update(status="degenerate", reason="invalid_bootstrap_variance")
        return result
    result.update(status="ok", se=float(se), ci_low=float(low), ci_high=float(high))
    return result


def residualize(
    factor: pd.DataFrame,
    styles: dict[str, pd.DataFrame],
    industry: pd.DataFrame | None,
    min_stocks: int = 30,
) -> tuple[pd.DataFrame, dict]:
    """Cross-sectional OLS residuals, never raw-factor fallback.

    Numeric styles are centered/scaled on each common finite cross-section.
    Policy: reject a rank-deficient design (including collinear styles) rather
    than silently omitting a requested control. Require positive residual dof.
    """
    min_stocks = _integer(min_stocks, "min_stocks")
    _panel(factor, "factor")
    aligned = {}
    for name, frame in styles.items():
        _panel(frame, f"style {name}")
        aligned[name] = _numbers(
            frame.reindex(index=factor.index, columns=factor.columns)
        )
    categories = None
    if industry is not None:
        _panel(industry, "industry")
        categories = industry.reindex(index=factor.index, columns=factor.columns)
    values = _numbers(factor)
    output = np.full(values.shape, np.nan)
    metadata = {
        "styles": [str(name) for name in styles],
        "industry": "omitted" if industry is None else "included",
        "rank_policy": "reject_rank_deficient",
        "style_scaling": "cross_sectional_center_and_scale",
        "n_valid": 0,
        "coverage_by_date": {},
        "diagnostics_by_date": {},
    }
    for i, date in enumerate(factor.index):
        diagnostic = {"n_valid": 0, "n_residuals": 0, "reason": None}
        key = str(date)
        metadata["diagnostics_by_date"][key] = diagnostic
        metadata["coverage_by_date"][key] = 0.0
        if not styles and industry is None:
            diagnostic["reason"] = "no_controls"
            continue
        missing = [
            str(name) for name, frame in styles.items() if date not in frame.index
        ]
        if industry is not None and date not in industry.index:
            missing.append("industry")
        if missing:
            diagnostic.update(reason="missing_reference_date", missing_controls=missing)
            continue
        valid = np.isfinite(values[i])
        for data in aligned.values():
            valid &= np.isfinite(data[i])
        if categories is not None:
            row = categories.iloc[i]
            present = row.map(
                lambda v: (
                    bool(pd.notna(v))
                    and (
                        bool(np.isfinite(v))
                        if isinstance(v, Real)
                        else bool(str(v).strip())
                    )
                )
            ).to_numpy(dtype=bool)
            valid &= present
        n = int(valid.sum())
        diagnostic["n_valid"] = n
        if n < min_stocks:
            diagnostic["reason"] = "insufficient_stocks"
            continue
        columns = [np.ones((n, 1))]
        for data in aligned.values():
            x = data[i, valid]
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                centered = x - np.mean(x)
                scale = np.std(centered)
                columns.append((centered / scale if scale > 0 else centered)[:, None])
        if categories is not None:
            dummies = pd.get_dummies(
                categories.iloc[i, valid], drop_first=True, dtype=float
            )
            columns.append(dummies.to_numpy())
        design = np.column_stack(columns)
        diagnostic["n_params"] = int(design.shape[1])
        if n <= design.shape[1]:
            diagnostic["reason"] = "insufficient_dof"
            continue
        if not np.isfinite(design).all():
            diagnostic["reason"] = "nonfinite_design"
            continue
        try:
            rank = int(np.linalg.matrix_rank(design))
            diagnostic["rank"] = rank
            if rank != design.shape[1]:
                diagnostic["reason"] = "rank_deficient"
                continue
            coefficients, _, _, _ = np.linalg.lstsq(
                design, values[i, valid], rcond=None
            )
            with np.errstate(over="ignore", invalid="ignore"):
                residuals = values[i, valid] - design @ coefficients
        except np.linalg.LinAlgError:
            diagnostic["reason"] = "regression_failed"
            continue
        if not np.isfinite(residuals).all():
            diagnostic["reason"] = "nonfinite_residuals"
            continue
        output[i, valid] = residuals
        diagnostic["n_residuals"] = n
        metadata["n_valid"] += n
        metadata["coverage_by_date"][key] = float(n / len(factor.columns))
    return pd.DataFrame(output, index=factor.index, columns=factor.columns), metadata


def score_to_signal(
    scores: pd.DataFrame,
    top_n: int,
    rebalance_days: int = 5,
    mask: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Long-only 0/1 targets, rebalance from row zero; engine handles T+1.

    Scores are already direction-adjusted by the caller. Ties use ascending
    ticker strings. Masks affect selection dates only, not held targets.
    """
    top_n = _integer(top_n, "top_n")
    rebalance_days = _integer(rebalance_days, "rebalance_days")
    _panel(scores, "scores", ordered=True)
    values = _numbers(scores)
    allowed = _allowed(mask, scores) & np.isfinite(values)
    output = np.zeros(scores.shape, dtype=np.int8)
    tickers = [str(ticker) for ticker in scores.columns]
    for i in range(0, len(scores), rebalance_days):
        candidates = np.flatnonzero(allowed[i])
        selected = sorted(candidates, key=lambda j: (-values[i, j], tickers[j]))[:top_n]
        output[i : min(i + rebalance_days, len(scores)), selected] = 1
    return pd.DataFrame(output, index=scores.index, columns=scores.columns)


def decay_summary(curve: list[dict]) -> dict:
    """Describe a monotone half-initial-IC crossing along holding horizons.

    half_life is the linearly interpolated holding horizon (not the difference
    from initial_horizon). Negative initial IC is compared in its initial sign;
    this does not select or change the strategy's direction. Never extrapolate.
    """
    points = []
    for point in curve:
        horizon = _integer(point["horizon"], "horizon")
        ic = point["ic"]
        points.append((horizon, None if ic is None else _finite_number(ic)))
    points.sort(key=lambda point: point[0])
    if len({horizon for horizon, _ in points}) != len(points):
        raise ValueError("horizons must be unique")
    result = {
        "half_life": None,
        "crossing_horizon": None,
        "initial_horizon": points[0][0] if points else None,
        "initial_ic": points[0][1] if points else None,
        "half_initial_ic": None,
        "reason": None,
        "note": (
            "Descriptive holding-horizon half-decay relative to the initial IC, "
            "with linear interpolation only. Not calendar lifetime, a fitted "
            "exponential half-life, or a strategy/parameter-selection test."
        ),
    }
    if len(points) < 2:
        result["reason"] = "insufficient_data"
        return result
    if any(ic is None for _, ic in points):
        result["reason"] = "missing_ic"
        return result
    initial = points[0][1]
    if initial == 0:
        result["reason"] = "zero_initial_ic"
        return result
    result["half_initial_ic"] = initial / 2
    sign = 1 if initial > 0 else -1
    oriented = [ic * sign for _, ic in points]
    if any(b > a for a, b in pairwise(oriented)):
        result["reason"] = "non_monotonic"
        return result
    level = abs(initial) / 2
    for i in range(1, len(points)):
        if oriented[i] <= level:
            fraction = (oriented[i - 1] - level) / (oriented[i - 1] - oriented[i])
            left, right = points[i - 1][0], points[i][0]
            result["half_life"] = float(left + fraction * (right - left))
            result["crossing_horizon"] = right
            return result
    result["reason"] = "no_crossing"
    return result
