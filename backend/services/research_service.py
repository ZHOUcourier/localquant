"""冻结协议下的本地 QMT 研究执行与证据归档。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re

import numpy as np
import pandas as pd

from backend.services import research_registry as registry
from backend.services.research_monitor import (
    causal_state_multipliers,
    conditional_summary,
    history_states,
    monitor_evidence,
)
from backend.services.research_statistics import (
    block_mean_interval,
    decay_summary,
    forward_returns,
    hac_mean,
    rank_ic,
    residualize,
    score_to_signal,
)


class ResearchDataUnavailable(ValueError):
    pass


def _series_json(series: pd.Series) -> dict:
    return {
        str(date)[:10]: float(value)
        for date, value in series.items() if pd.notna(value) and np.isfinite(value)
    }


def _fingerprint(frames: dict[str, pd.DataFrame | None], end: str) -> str:
    digest = hashlib.sha256()
    for name, frame in sorted(frames.items()):
        digest.update(name.encode())
        if frame is None:
            digest.update(b"missing")
            continue
        part = frame.loc[frame.index <= pd.Timestamp(end)]
        digest.update(json.dumps(list(part.columns), ensure_ascii=False).encode())
        digest.update(pd.util.hash_pandas_object(part, index=True).values.tobytes())
    return digest.hexdigest()


def _cached_panels(codes: list[str], start: str, end: str) -> tuple[dict, pd.DataFrame]:
    from backend.services import market_data

    frames: dict[str, dict] = {name: {} for name in market_data.PRICE_FIELDS}
    raw_close = {}
    missing = []
    for code in codes:
        cached = market_data._cache.get(code, "1d")
        if cached is None or cached.empty:
            missing.append(code)
            continue
        if "adjust_factor" not in cached.columns:
            raise ResearchDataUnavailable(f"{code} 缓存缺复权因子，无法保证历史价格点位；等待 Windows QMT 完整缓存")
        raw = market_data.normalize_kline_fields(cached).copy()
        raw.index = market_data.normalize_timestamp(raw.index)
        raw = raw.sort_index()
        raw.index = pd.DatetimeIndex(raw.index).tz_localize(None).normalize()
        raw = raw.loc[(raw.index >= pd.Timestamp(start)) & (raw.index <= pd.Timestamp(end))]
        if raw.empty or not raw.index.is_unique:
            raise ResearchDataUnavailable(f"{code} 日期区间为空或存在重复交易日")
        adjusted = market_data._apply_adjust(raw, code, "hfq")
        raw_close[code] = raw["close"]
        for name, values in frames.items():
            if name in adjusted:
                values[code] = adjusted[name].astype(float)
    if missing:
        raise ResearchDataUnavailable("冻结股票池缺少本地 QMT 日线：" + ", ".join(missing[:10]))
    panels = {name: pd.DataFrame(values).sort_index() for name, values in frames.items() if values}
    if "close" not in panels or panels["close"].empty:
        raise ResearchDataUnavailable("本地无 QMT 日线；研究已登记，等待 Windows QMT 数据，不接入替代数据源")
    if "volume" not in panels:
        raise ResearchDataUnavailable("缺少 QMT 成交量，不能验证可交易性")
    return panels, pd.DataFrame(raw_close).reindex(panels["close"].index)


def _load_inputs(study: dict, phase: str) -> dict:
    from backend.services import fundamental, market_data, reference_data

    p = study["protocol"]
    available = market_data.list_cached_codes("1d", exclude_indices=True)
    codes = study.get("universe") or p["codes"] or [
        c for c in available
        if re.fullmatch(r"(?:(?:600|601|603|605|688|689)\d{3}\.SH|(?:000|001|002|003|300|301|302)\d{3}\.SZ|(?:4\d{5}|8\d{5}|92\d{4})\.BJ)", c)
    ]
    codes = sorted(codes)
    if len(codes) < p["min_stocks"]:
        raise ResearchDataUnavailable(f"本地 QMT 股票池不足协议要求的 {p['min_stocks']} 只；当前 {len(codes)} 只")
    end = p["validation_end"] if phase == "validation" else p["end_date"]
    if phase == "monitor":
        end = str(pd.Timestamp.today().date())
    panels, raw_close = _cached_panels(codes, p["start_date"], end)
    close = panels["close"]
    if phase != "monitor" and close.index[-1] < pd.Timestamp(end):
        raise ResearchDataUnavailable("冻结截止日的 QMT 数据尚未齐备；截止日应选择实际交易日，不能缩短留出区间")
    if len(close) < p["min_dates"] + p["horizon"] + 2:
        raise ResearchDataUnavailable("QMT 交易日覆盖不足冻结协议的样本要求")
    unknown_gap = close.isna() & close.ffill().notna() & close.bfill().notna() & ~panels["volume"].reindex_like(close).eq(0)
    if unknown_gap.any().any():
        raise ResearchDataUnavailable("QMT 区间存在不能确认为停牌的缺价记录，不能以零收益替代")
    industry = reference_data.load_industry_panel(close.index, close.columns)
    market_cap = reference_data.build_market_cap_panel(raw_close)
    if market_cap is not None:
        panels["market_cap"] = market_cap
    reference = market_data.load_reference_panels(raw_close, panels.get("volume"))
    reference["tradable_mask"] = reference["tradable_mask"] & close.notna()
    from backend.services.universe_policy import (
        UniversePolicy,
        build_equity_eligibility,
    )

    policy = UniversePolicy(
        exclude_st=bool(p.get("exclude_st", True)),
        exclude_new=bool(p.get("exclude_new", True)),
        min_list_days=int(p.get("min_list_days", 730)),
        include_bj=bool(p.get("include_bj", True)),
        exclude_delisting=bool(p.get("exclude_delisting", True)),
    )
    eligibility = build_equity_eligibility(close.index, close.columns, policy)
    mask = eligibility.mask & close.notna() & (close > 0)
    volume_mask = panels.get("volume")
    if volume_mask is not None:
        mask = mask & (volume_mask.reindex_like(close).fillna(0.0) > 0)
    fund = fundamental.build_fundamental_panels(list(close.columns), close.index) or {}
    states = pd.Series(index=close.index, dtype=object)
    index_frame = market_data._cache.get(p["regime_index"], "1d")
    if index_frame is not None and not index_frame.empty:
        index_frame = index_frame.copy()
        index_frame.index = market_data.normalize_timestamp(index_frame.index)
        index_frame = index_frame.sort_index()
        index_frame.index = pd.DatetimeIndex(index_frame.index).tz_localize(None).normalize()
        index_frame = index_frame.loc[index_frame.index <= pd.Timestamp(end)]
        if "adjust_factor" in index_frame and not index_frame.empty:
            index_frame = market_data._apply_adjust(index_frame, p["regime_index"], "hfq")
            states = history_states(index_frame["close"]).reindex(close.index)
    return {
        "panels": panels, "raw_close": raw_close, "mask": mask,
        "eligibility": eligibility,
        "industry": industry, "fundamental": fund, "reference": reference,
        "states": states, "codes": list(close.columns),
    }


def _causal_factors(formulas: list[str], inputs: dict) -> list[pd.DataFrame]:
    from backend.services.factor_operators import (
        build_operator_namespace,
        eval_factor_formula,
    )

    panels = inputs["panels"]
    close = panels["close"]
    outputs = [pd.DataFrame(np.nan, index=close.index, columns=close.columns) for _ in formulas]
    for date in close.index:
        prefix = {name: frame.loc[:date] for name, frame in panels.items()}
        ind = inputs["industry"]
        mapping = ind.loc[date].dropna().to_dict() if ind is not None and date in ind.index else {}
        fund = {f"fund_{name}": frame.loc[:date] for name, frame in inputs["fundamental"].items()}
        namespace = build_operator_namespace(prefix, industry_map=mapping, fundamental=fund)
        for formula, output in zip(formulas, outputs):
            values = eval_factor_formula(formula, namespace)
            if not isinstance(values, pd.DataFrame) or date not in values.index:
                raise ValueError("研究公式必须输出 date × stock 面板")
            row = values.loc[date].reindex(close.columns).astype(float)
            output.loc[date] = row.where(np.isfinite(row))
    return outputs


def _weights(signal: pd.DataFrame) -> pd.DataFrame:
    return signal.div(signal.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def _run_portfolio(signal: pd.DataFrame, inputs: dict, p: dict, *, stress: bool = False) -> dict:
    from backend.services.backtest_analysis import BacktestAnalysisService

    panels, refs = inputs["panels"], inputs["reference"]
    # 价格收益用后复权；涨跌停比较必须与 high/low 使用同一价格尺度。
    scale = panels["close"].div(inputs["raw_close"].replace(0, np.nan))
    up = refs.get("up_limit")
    down = refs.get("down_limit")
    eligibility = inputs.get("eligibility")
    return BacktestAnalysisService().run_backtest(
        signals=signal, prices=panels["close"], initial_capital=p["initial_capital"],
        commission_rate=p["commission_rate"] * (2 if stress else 1),
        slippage=p["slippage"] * (2 if stress else 1), stamp_tax=p["stamp_tax"],
        normalize="long_only", execute_at="next_close", max_gross_exposure=1.0,
        tradable_mask=refs["tradable_mask"],
        eligible_mask=eligibility.mask if eligibility is not None else None,
        up_limit=up * scale if up is not None else None,
        down_limit=down * scale if down is not None else None,
        high=panels.get("high"), low=panels.get("low"),
    )


def compute_evidence(study: dict, trial: dict, phase: str, inputs: dict) -> dict:
    from backend.services import risk

    p = study["protocol"]
    panels, mask = inputs["panels"], inputs["mask"]
    close = panels["close"]
    start = p["train_end"] if phase == "validation" else p["validation_end"]
    end = p["validation_end"] if phase == "validation" else p["end_date"]
    if phase == "monitor":
        end = str(close.index[-1].date())
    phase_dates = close.index[(close.index > pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))]
    if len(phase_dates) < p["min_dates"]:
        raise ResearchDataUnavailable("该阶段尚无足够 QMT 交易日，不能计算置信区间")
    frames = _causal_factors([trial["formula"], *p["baseline_formulas"]], inputs)
    factor = frames[0] * trial["direction"]
    returns = close.ffill().pct_change(fill_method=None)
    # 只有缓存明确记录了停牌的缺价日才能沿用零收益；未知缺口不拼成完整标签。
    observed = close.notna() | panels["volume"].reindex_like(close).eq(0)
    returns = returns.where(observed)
    labels = forward_returns(returns, p["horizon"], execution_lag=1)
    diagnostic = forward_returns(returns, p["horizon"], execution_lag=0)
    raw_ic = rank_ic(factor, labels, mask=mask, min_stocks=p["min_stocks"])
    styles = risk.build_style_exposures(
        close, volume=panels.get("volume"), amount=panels.get("amount"),
        market_cap=panels.get("market_cap"), fundamental=inputs["fundamental"],
    )
    neutral, neutral_meta = residualize(factor, styles, inputs["industry"], min_stocks=p["min_stocks"])
    if frames[1:]:
        baseline_scores = sum(frame.rank(axis=1, pct=True) for frame in frames[1:]) / len(frames[1:])
        baseline = score_to_signal(baseline_scores, p["top_n"], p["rebalance_days"], mask=mask)
    else:
        baseline = score_to_signal(close.notna().astype(float), len(close.columns), p["rebalance_days"], mask=mask)
    candidate = score_to_signal(factor, p["top_n"], p["rebalance_days"], mask=mask)
    base_w, candidate_w = _weights(baseline), _weights(candidate)
    blend = (1 - p["candidate_weight"]) * base_w + p["candidate_weight"] * candidate_w
    signals = {"baseline": baseline, "raw": candidate, "incremental": blend}
    neutral_available = bool(neutral.loc[phase_dates].notna().sum(axis=1).ge(p["min_stocks"]).any())
    if neutral_available:
        signals["neutralized"] = score_to_signal(neutral, p["top_n"], p["rebalance_days"], mask=mask)
        signals["matched_raw"] = score_to_signal(factor.where(neutral.notna()), p["top_n"], p["rebalance_days"], mask=mask)
    if inputs["states"].notna().any():
        multiplier = causal_state_multipliers(
            raw_ic, inputs["states"], p["horizon"], p["min_dates"], p["regime_shrinkage"]
        )
        allocation = multiplier * p["candidate_weight"]
        signals["regime"] = base_w.mul(1 - allocation, axis=0) + candidate_w.mul(allocation, axis=0)
    for signal in signals.values():
        signal.loc[signal.index <= pd.Timestamp(start)] = 0.0
    portfolios = {name: _run_portfolio(signal, inputs, p) for name, signal in signals.items()}
    base_returns = portfolios["baseline"]["strategy_returns"].reindex(phase_dates)
    alpha = p["alpha"] / p["trial_budget"]
    tracks = {}
    for name in ("raw", "neutralized", "incremental"):
        if name not in portfolios:
            tracks[name] = {"status": "unavailable", "reason": "参考暴露或有效样本不足；未回退原因子", "coverage": neutral_meta}
            continue
        daily = portfolios[name]["strategy_returns"].reindex(phase_dates)
        active = daily - base_returns
        ic = raw_ic if name != "neutralized" else rank_ic(neutral, labels, mask=mask, min_stocks=p["min_stocks"])
        tracks[name] = {
            "status": "ok", "ic": hac_mean(ic.reindex(phase_dates), p["horizon"], min_obs=p["min_dates"]),
            "net": hac_mean(active, p["horizon"], min_obs=p["min_dates"]),
            "returns": _series_json(daily), "active_returns": _series_json(active),
            "daily_ic": _series_json(ic.reindex(phase_dates)),
            "cost_summary": portfolios[name]["cost_summary"],
        }
        if name == "neutralized":
            tracks[name]["coverage"] = neutral_meta
            paired_ic = rank_ic(factor.where(neutral.notna()), labels, mask=mask, min_stocks=p["min_stocks"])
            paired_delta = daily - portfolios["matched_raw"]["strategy_returns"].reindex(phase_dates)
            tracks[name]["matched_raw_ic"] = hac_mean(paired_ic.reindex(phase_dates), p["horizon"], min_obs=p["min_dates"])
            tracks[name]["paired_net_delta"] = hac_mean(paired_delta, p["horizon"], min_obs=p["min_dates"])
    primary_series = pd.Series(tracks["incremental"]["active_returns"], dtype=float)
    primary_series.index = pd.to_datetime(primary_series.index)
    primary = hac_mean(primary_series, p["horizon"], alpha=alpha, null_mean=p["minimum_effect"], min_obs=p["min_dates"])
    bootstrap = block_mean_interval(primary_series, max(p["horizon"] + 1, p["rebalance_days"]), min_obs=p["min_dates"])
    stress_base = _run_portfolio(signals["baseline"], inputs, p, stress=True)
    stress_blend = _run_portfolio(signals["incremental"], inputs, p, stress=True)
    stress_active = (stress_blend["strategy_returns"] - stress_base["strategy_returns"]).reindex(phase_dates)
    decision = "inconclusive"
    if primary["status"] != "ok" or raw_ic.reindex(phase_dates).notna().sum() < p["min_dates"]:
        decision = "insufficient_data"
    elif primary["ci_low"] > p["minimum_effect"] and float(stress_active.mean()) > p["minimum_effect"]:
        decision = "supported"
    curve = []
    for horizon in sorted({1, p["horizon"], 5, 10, 20}):
        labels_h = forward_returns(returns, horizon, execution_lag=1)
        values = rank_ic(factor, labels_h, mask=mask, min_stocks=p["min_stocks"]).reindex(phase_dates).dropna()
        curve.append({"horizon": horizon, "ic": float(values.mean()) if len(values) else None})
    comparison = None
    if "regime" in portfolios:
        delta = (portfolios["regime"]["strategy_returns"] - portfolios["incremental"]["strategy_returns"]).reindex(phase_dates)
        comparison = hac_mean(delta, p["horizon"], min_obs=p["min_dates"])
    manifest_frames = {**panels, "industry": inputs["industry"], **{f"fund_{k}": v for k, v in inputs["fundamental"].items()}}
    manifest = {
        "protocol_hash": study["protocol_hash"], "trial_id": trial["id"], "phase": phase,
        "codes": inputs["codes"], "n_stocks": len(close.columns), "n_dates": len(phase_dates),
        "data_start": str(close.index[0].date()), "data_end": str(close.index[-1].date()),
        "evaluation_start": str(phase_dates[0].date()), "evaluation_end": str(phase_dates[-1].date()),
        "data_hash": _fingerprint(manifest_frames, end),
        "validation_data_hash": _fingerprint(manifest_frames, p["validation_end"]),
        "price_adjustment": "hfq", "signal_evaluation": "causal_prefix",
        "execution": "signal_T_close_fill_T_plus_1_close", "label_end_offset": p["horizon"] + 1,
        "primary": "incremental_cost_net_return_vs_frozen_baseline", "family_alpha": p["alpha"],
        "trial_budget": p["trial_budget"], "test_alpha": alpha,
        "universe": (
            inputs["eligibility"].manifest() if inputs.get("eligibility") else {}
        ),
    }
    limitations = [
        "只读取本地 QMT 缓存；不下载或接入替代金融数据。",
        "HAC 与时间块区间为有限样本近似；样本门槛不是统计功效保证。",
        "原始/残差 IC、状态矩阵和衰减均为次要诊断；主检验是固定组合增量的成本后相对收益。",
        "Bonferroni 按预注册试验预算控制本研究族；不能纠正平台外尝试或事后挑选的股票池。",
        "不同日期的快照不等于独立样本；持有时距衰减不等于因子的日历寿命。",
        "无真实成交/盘口深度/其他参与者持仓，容量及全市场拥挤程度未验证。",
        "当前股票池的历史完整性与退市覆盖需 QMT 数据审查；成本后正收益不保证未来盈利。",
        "最终留出仅在本研究内封存；不能证明研究员此前未查看同一历史区间。",
    ]
    limitations.extend(inputs["reference"].get("assumptions", []))
    if inputs.get("eligibility") is not None:
        limitations.extend(inputs["eligibility"].warnings)
    for portfolio in portfolios.values():
        limitations.extend(portfolio.get("assumptions", []))
    result = {
        "status": "completed", "decision": decision, "source": "local_qmt_cache",
        "summary": {"decision": decision, "n_dates": len(phase_dates), "primary_mean": primary["mean"], "primary_p": primary["p_value"]},
        "primary": primary, "bootstrap": bootstrap, "tracks": tracks,
        "cost_stress": {"commission_slippage_multiplier": 2, "mean_incremental_return": float(stress_active.mean())},
        "diagnostic_ic": hac_mean(rank_ic(factor, diagnostic, mask=mask, min_stocks=p["min_stocks"]).reindex(phase_dates), p["horizon"], min_obs=p["min_dates"]),
        "decay": {"curve": curve, **decay_summary(curve)},
        "regime": {
            "status": "ok" if inputs["states"].notna().any() else "unavailable",
            "conditional": conditional_summary(raw_ic.reindex(phase_dates), inputs["states"], p["min_dates"], p["regime_shrinkage"]),
            "comparison": comparison,
            "note": "状态权重只用已成熟标签；未达状态样本门槛不启用降权，比较仅为诊断。",
        },
        "manifest": manifest, "limitations": list(dict.fromkeys(limitations)),
    }
    if phase == "monitor":
        held = next(r for r in study["runs"] if r["trial_id"] == trial["id"] and r["phase"] == "holdout" and r["status"] == "completed")
        baseline_values = pd.Series(held["result"]["tracks"]["incremental"]["active_returns"], dtype=float)
        baseline_values.index = pd.to_datetime(baseline_values.index)
        observations = primary_series.loc[primary_series.index > pd.Timestamp(p["end_date"])]
        monitor = monitor_evidence(
            baseline_values, observations, horizon=p["horizon"], window=p["monitor_window"],
            review_every=p["review_every"], alpha=p["alpha"], trial_budget=p["trial_budget"],
            min_obs=p["min_dates"], minimum_effect=p["minimum_effect"],
        )
        result["monitor"] = monitor
        result["decision"] = "review_needed" if monitor["status"] == "review_needed" else "inconclusive"
        result["summary"]["decision"] = result["decision"]
    return result


async def run_trial(trial_id: str, phase: str = "validation") -> dict:
    study, trial, run = await registry.begin_run(trial_id, phase)
    try:
        study = await registry.get_study(study["id"])
        inputs = await asyncio.to_thread(_load_inputs, study, phase)
        await registry.freeze_universe(study["id"], inputs["codes"])
        result = await asyncio.to_thread(compute_evidence, study, trial, phase, inputs)
        earlier = [r for r in study.get("runs", []) if r["phase"] == "validation" and r["status"] == "completed"]
        if earlier and any(r["result"].get("manifest", {}).get("validation_data_hash") != result["manifest"]["validation_data_hash"] for r in earlier):
            raise ValueError("QMT 验证区间或参考数据已变化，不能与旧试验拼接；请保留旧证据并重新登记研究")
        if phase == "monitor" and "monitor" in result:
            review = result["monitor"]
            duplicate = next((r for r in study["runs"] if r["phase"] == "monitor" and r["status"] == "completed" and r["result"].get("monitor", {}).get("review_date") == review.get("review_date")), None)
            if review["status"] == "insufficient_data" or duplicate:
                reason = "尚未到新的复核网格，重复计算不增加有效观察" if duplicate else review["reason"]
                result["status"] = "awaiting_data"
                result["decision"] = "insufficient_data"
                result["summary"]["decision"] = "insufficient_data"
                result["limitations"].append(reason)
                if duplicate:
                    review["duplicate_of"] = duplicate["id"]
                return await registry.finish_run(run["id"], "awaiting_data", result, reason)
        return await registry.finish_run(run["id"], "completed", result)
    except asyncio.CancelledError:
        await asyncio.shield(registry.finish_run(run["id"], "failed", {"summary": {}, "status": "failed"}, "研究执行已取消，未写入完成证据"))
        raise
    except ResearchDataUnavailable as exc:
        return await registry.finish_run(run["id"], "awaiting_data", {
            "status": "awaiting_data", "decision": "insufficient_data", "source": "local_qmt_cache",
            "summary": {}, "limitations": [str(exc)],
        }, str(exc))
    except Exception as exc:
        return await registry.finish_run(run["id"], "failed", {
            "status": "failed", "decision": "inconclusive", "summary": {}, "limitations": [str(exc)],
        }, str(exc))
