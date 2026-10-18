"""因果状态分层与冻结 holdout 后的监测；只计算上游提供的真实序列。

不读取行情、联网、持久化或改变 registry 状态。交易日历由输入索引提供，
不能用自然日/工作日日历猜测 QMT 交易日，也不能把量价状态解释为全市场资金拥挤。
"""

from __future__ import annotations

from numbers import Integral

import numpy as np
import pandas as pd

_NOTE = (
    "仅在预设的新增成熟有效观察批次复核；alpha spending 对试验预算及重复复核"
    "使用 union bound，但 HAC 推断仍是有限样本近似，并非精确的序贯保证。"
    "冻结 holdout 与当前窗口及均值差仅作描述，不构成因果或拥挤归因。"
    "不显著不等于失效；本函数不退役、不自动交易，状态迁移仅由人工 registry.review 执行。"
)


def _validate_series(series: pd.Series, name: str) -> None:
    if not isinstance(series, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")
    if series.index.hasnans or not series.index.is_unique:
        raise ValueError(f"{name} index must be nonmissing and unique")
    if not series.index.is_monotonic_increasing:
        raise ValueError(f"{name} index must be ordered chronologically")


def _integer(value: int, name: str, minimum: int = 1) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _finite(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").astype(float)
    return numeric.where(np.isfinite(numeric))


def history_states(close: pd.Series) -> pd.Series:
    """用当日及历史价格生成状态；60 个历史 HV20 才形成滞后一日的波动基线。

    MA20/60、20 日动量和 HV20 沿用 regime 的理念（250 日年化）。
    缺价格、趋势窗口或历史波动基线时返回 None，不补值、不回填未来状态。
    """
    _validate_series(close, "close")
    prices = _finite(close).where(lambda values: values > 0)
    ma20 = prices.rolling(20, min_periods=20).mean()
    ma60 = prices.rolling(60, min_periods=60).mean()
    mom20 = _finite(prices / prices.shift(20) - 1)
    vol20 = np.log(prices).diff().rolling(20, min_periods=20).std() * np.sqrt(250)
    vol_baseline = vol20.expanding(min_periods=60).median().shift(1)
    known = (
        prices.notna() & ma20.notna() & ma60.notna() & mom20.notna()
        & vol20.notna() & vol_baseline.notna()
    )
    trend = pd.Series("range", index=close.index, dtype=object)
    trend.loc[(prices > ma20) & (ma20 > ma60) & (mom20 > 0.02)] = "up"
    trend.loc[(prices < ma20) & (ma20 < ma60) & (mom20 < -0.02)] = "down"
    volatility = pd.Series("normal", index=close.index, dtype=object)
    volatility.loc[vol20 > vol_baseline] = "high"
    result = pd.Series([None] * len(close), index=close.index, dtype=object, name="state")
    result.loc[known] = (trend + "_" + volatility).loc[known]
    return result


def conditional_summary(
    values: pd.Series,
    states: pd.Series,
    min_obs: int = 60,
    prior_strength: int = 60,
) -> list[dict]:
    """按信号日对齐的描述性分层；整体先验包含所有有限值（包括未知状态）。"""
    _validate_series(values, "values")
    _validate_series(states, "states")
    _integer(min_obs, "min_obs")
    _integer(prior_strength, "prior_strength", 0)
    finite = _finite(values)
    aligned_states = states.reindex(values.index)
    global_mean = finite.mean()
    if not np.isfinite(global_mean):
        return []
    frame = pd.DataFrame({"value": finite, "state": aligned_states})
    frame = frame.dropna(subset=["value", "state"])
    rows = []
    for state, group in frame.groupby("state", sort=False):
        n_obs = len(group)
        mean = float(group["value"].mean())
        rows.append({
            "state": state,
            "n_obs": n_obs,
            "mean": mean,
            "shrunk_mean": float(
                (n_obs * mean + prior_strength * global_mean) / (n_obs + prior_strength)
            ),
            "eligible": n_obs >= min_obs,
        })
    return rows


def causal_state_multipliers(
    ic: pd.Series,
    states: pd.Series,
    horizon: int,
    min_obs: int = 60,
    prior_strength: int = 60,
) -> pd.Series:
    """信号日 T 的 IC 在 T+h+1 才成熟；先按完整交易日索引对齐再 shift。

    上游须在 ic 或 states 中保留完整交易日索引（无观测日期保留 NaN）。
    同时滞后 IC 和信号日状态，不把成熟日状态误配给历史信号。
    返回候选因子在基准组合中的分配开关；不得直接缩小权重再归一化。
    未知/不足状态保持 1；这里只因已有足够样本且收缩均值为负才返回 0。
    """
    _validate_series(ic, "ic")
    _validate_series(states, "states")
    _integer(horizon, "horizon", 0)
    _integer(min_obs, "min_obs")
    _integer(prior_strength, "prior_strength", 0)
    dates = ic.index.union(states.index).sort_values()
    signal_states = states.reindex(dates)
    known_ic = _finite(ic.reindex(dates)).shift(horizon + 1)
    known_states = signal_states.shift(horizon + 1)
    result = pd.Series(1.0, index=dates, name="multiplier")
    counts: dict = {}
    sums: dict = {}
    global_count = 0
    global_sum = 0.0
    for position, (value, signal_state, current_state) in enumerate(
        zip(known_ic, known_states, signal_states)
    ):
        if pd.notna(value):
            global_count += 1
            global_sum += value
            if pd.notna(signal_state):
                counts[signal_state] = counts.get(signal_state, 0) + 1
                sums[signal_state] = sums.get(signal_state, 0.0) + value
        if pd.isna(current_state) or counts.get(current_state, 0) < min_obs:
            continue
        n_obs = counts[current_state]
        shrunk = (
            sums[current_state] + prior_strength * global_sum / global_count
        ) / (n_obs + prior_strength)
        if shrunk < 0:
            result.iloc[position] = 0.0
    return result


def _empty_stats(n_obs: int = 0) -> dict:
    return {
        "status": "insufficient_data", "n_obs": n_obs, "mean": None,
        "se": None, "ci_low": None, "ci_high": None, "p_value": None, "lags": None,
    }


def _hac_stats(
    series: pd.Series, *, horizon: int, alpha: float, null_mean: float, min_obs: int,
) -> dict:
    n_obs = int(series.count())
    if not n_obs:
        return _empty_stats()
    # 延迟导入使无数据路径和状态分层不依赖统计模块的加载。
    from backend.services.research_statistics import hac_mean

    # Newey–West 常用带宽下限，且不得低于重叠持有期造成的依赖长度。
    lags = max(horizon, int(np.floor(4 * (n_obs / 100) ** (2 / 9))))
    return hac_mean(
        series, max_lags=lags, alpha=alpha, null_mean=null_mean, min_obs=min_obs,
    )


def monitor_evidence(
    baseline: pd.Series,
    observations: pd.Series,
    *,
    horizon: int,
    window: int,
    review_every: int,
    alpha: float,
    trial_budget: int,
    min_obs: int,
    minimum_effect: float = 0,
) -> dict:
    """冻结 holdout 后新增、已成熟、成本后相对收益的固定网格复核。

    网格按新增有限观察计数：review_every, 2*review_every, ...；首个
    达到 max(window, min_obs) 的网格记为 j=1。NaN/inf 不推进批次；只使用
    最后完成批次截止处的最近 window 个有效观察，忽略尚未完成的尾批。
    上游须传入完整累计新增序列（不是每日片段），并按 review_date 持久化去重。
    baseline 仅作冻结描述，不能与 observations 重叠或被算作新增样本。
    """
    _validate_series(baseline, "baseline")
    _validate_series(observations, "observations")
    _integer(horizon, "horizon", 0)
    for name, value in (
        ("window", window), ("review_every", review_every),
        ("trial_budget", trial_budget), ("min_obs", min_obs),
    ):
        _integer(value, name)
    if not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and between 0 and 1")
    if not np.isfinite(minimum_effect):
        raise ValueError("minimum_effect must be finite")
    if (
        not baseline.empty and not observations.empty
        and observations.index[0] <= baseline.index[-1]
    ):
        raise ValueError("observations must be strictly after the frozen holdout")

    frozen = _finite(baseline)
    aligned_new = _finite(observations)
    new_positions = np.flatnonzero(aligned_new.notna().to_numpy())
    n_new = len(new_positions)
    baseline_stats = _hac_stats(
        frozen, horizon=horizon, alpha=alpha, null_mean=minimum_effect, min_obs=min_obs,
    )
    result = {
        "status": "insufficient_data",
        "recommendation": None,
        "review_number": None,
        "review_date": None,
        "n_new_observations": n_new,
        "n_used": 0,
        "alpha_spent": None,
        "current": _empty_stats(),
        "baseline": baseline_stats,
        "mean_change": None,
        "reason": "新增成熟有效观察不足，保持当前状态。",
        "note": _NOTE,
    }
    required = max(window, min_obs)
    first_batch = (required + review_every - 1) // review_every
    completed_batch = n_new // review_every
    if n_new < required:
        return result
    if completed_batch < first_batch:
        result["reason"] = "样本已达最低要求，但尚未到预设复核网格，保持当前状态。"
        return result

    review_number = completed_batch - first_batch + 1
    cutoff = completed_batch * review_every
    # 保留窗口内部的缺失日期，让 HAC 报告压缩后的滞后含义与数据缺口。
    current_window = aligned_new.iloc[
        new_positions[cutoff - window]:new_positions[cutoff - 1] + 1
    ]
    alpha_spent = alpha / (trial_budget * review_number * (review_number + 1))
    current_stats = _hac_stats(
        current_window, horizon=horizon, alpha=alpha_spent,
        null_mean=minimum_effect, min_obs=min_obs,
    )
    result.update({
        "review_number": review_number,
        "review_date": current_window.index[-1].isoformat()
        if hasattr(current_window.index[-1], "isoformat") else str(current_window.index[-1]),
        "n_used": int(current_window.count()),
        "alpha_spent": alpha_spent,
        "current": current_stats,
    })
    current_mean = current_stats.get("mean")
    baseline_mean = baseline_stats.get("mean")
    if (
        current_mean is not None and baseline_mean is not None
        and np.isfinite(current_mean) and np.isfinite(baseline_mean)
    ):
        result["mean_change"] = float(current_mean - baseline_mean)
    ci_high = current_stats.get("ci_high")
    if ci_high is None or not np.isfinite(ci_high):
        result["reason"] = "当前窗口无法形成有效 HAC 区间，保持当前状态并排查样本或数据缺口。"
    elif ci_high < minimum_effect:
        result.update({
            "status": "review_needed",
            "recommendation": "watch",
            "reason": "当前均值区间上界低于最低效果要求；请人工观察并排查数据、风格和成本，不自动退役。",
        })
    else:
        result.update({
            "status": "monitoring",
            "reason": "当前证据未触发人工观察阈值；继续按预设网格复核，不显著不等于失效。",
        })
    return result
