"""风险与组合层服务 — 风格暴露/归因、组合优化、绩效补充指标、压力测试

口径约定（与 factor_research / backtest_analysis 一致，避免前视）:
- 画像面板 index=日期, columns=股票
- 收益面板 r[T] = T-1 → T 收益
- 权重面板已与基准交易日对齐（回测层负责信号延迟）
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RISKFREE = 0.03  # 年化无风险利率


def _zscore_cross(df: pd.DataFrame) -> pd.DataFrame:
    """按行(截面)做 z-score 标准化"""
    mean = df.mean(axis=1)
    std = df.std(axis=1).replace(0, np.nan)
    return df.sub(mean, axis=0).div(std, axis=0)


def _cumprod_ret(a) -> float:
    """返回一段收益率数组累计收益（-1 保护）"""
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return 0.0
    if (a <= -1.0).any():
        return -1.0
    return float(np.prod(1.0 + a) - 1.0)


# ── 风格暴露构建（Barra 精简）────────────────────────────────────────────


def build_style_exposures(
    close: pd.DataFrame,
    volume: pd.DataFrame | None = None,
    amount: pd.DataFrame | None = None,
    market_cap: pd.DataFrame | None = None,
    fundamental: dict[str, pd.DataFrame] | None = None,
) -> dict[str, pd.DataFrame]:
    """构建截面风格暴露面板 {style: DataFrame(index=date, columns=stock)}

    每个暴露每日在横截面 z-score 标准化。

    风格:
      SIZE        : ln(流通市值)
      MOMENTUM    : 近20交易日累计收益
      LONG_MOM    : 近250交易日累计收益（min_periods=60）
      VOLATILITY  : 近20日日收益 std
      LIQUIDITY   : 近20日平均成交额(亿)；无成交额用成交量
      VALUE       : -ln(PB)，需 fundamental['pb']
      PROFIT_AB   : ROE，需 fundamental['roe']

    Returns:
        仅含可用数据风格。
    """
    styles: dict[str, pd.DataFrame] = {}
    ret = close.pct_change()

    if market_cap is not None and not market_cap.empty:
        styles["SIZE"] = _zscore_cross(np.log(market_cap.replace(0, np.nan)))

    styles["MOMENTUM"] = _zscore_cross(
        ret.rolling(20, min_periods=5).apply(_cumprod_ret, raw=True)
    )
    styles["LONG_MOM"] = _zscore_cross(
        ret.rolling(250, min_periods=60).apply(_cumprod_ret, raw=True)
    )
    styles["VOLATILITY"] = _zscore_cross(ret.rolling(20, min_periods=5).std())

    if amount is not None and not amount.empty:
        styles["LIQUIDITY"] = _zscore_cross(amount.rolling(20).mean() / 1e8)
    elif volume is not None and not volume.empty:
        styles["LIQUIDITY"] = _zscore_cross(volume.rolling(20).mean())

    if fundamental:
        pb = fundamental.get("pb")
        if pb is not None and not pb.empty:
            styles["VALUE"] = _zscore_cross(-np.log(pb.replace(0, np.nan)))
        roe = fundamental.get("roe")
        if roe is not None and not roe.empty:
            styles["PROFIT_AB"] = _zscore_cross(roe)

    return styles


def portfolio_style_exposure(
    weights: pd.DataFrame, styles: dict[str, pd.DataFrame]
) -> dict[str, pd.Series]:
    """组合逐日风格暴露 = Σ(归一化权重 × 风格 zscore)

    Returns:
        {style: Series(index=date, 值=组合对风格暴露)}
    """
    out: dict[str, pd.Series] = {}
    for name, expo in styles.items():
        common = weights.columns.intersection(expo.columns)
        if common.empty:
            continue
        w = weights.reindex(columns=common).fillna(0.0)
        e = expo.reindex(columns=common, index=w.index).fillna(0.0)
        row_sum = w.sum(axis=1).replace(0, np.nan)
        wn = w.div(row_sum, axis=0).fillna(0.0)
        out[name] = (wn * e).sum(axis=1)
    return out


def style_factor_returns(
    returns: pd.DataFrame,
    styles: dict[str, pd.DataFrame],
    min_stocks: int = 10,
) -> dict:
    """风格因子收益归因：每日横截面回归 资产收益 = Σ风格暴露×风格收益 + 残差

    Returns:
        {
          'factor_returns': {style: {date: fac_ret}},
          'summary': [{'style', 'mean', 'std', 't', 'ir', 'cumulative'}],
          'cov': 风格因子日收益协方差(年化) DataFrame 或空,
        }
    """
    style_names = list(styles.keys())
    flows: dict[str, dict] = {s: {} for s in style_names}

    for date, r in returns.iterrows():
        r_valid = r.dropna()
        if len(r_valid) < min_stocks:
            continue
        X_list: list[np.ndarray] = []
        for s in style_names:
            expo = styles[s].reindex(columns=r_valid.index)
            e = (
                expo.loc[date]
                if date in expo.index
                else pd.Series(np.nan, index=r_valid.index)
            )
            e = e.reindex(r_valid.index).fillna(0.0)
            X_list.append(e.to_numpy())
        if not X_list:
            continue
        X = np.column_stack(X_list)
        y = r_valid.to_numpy()
        Xa = np.column_stack([np.ones(len(y)), X])
        if Xa.shape[1] > len(y):
            continue
        try:
            coef, _, _, _ = np.linalg.lstsq(Xa, y, rcond=None)
        except Exception:
            continue
        for j, s in enumerate(style_names):
            flows[s][date] = float(coef[j + 1])

    summary: list[dict] = []
    frame = pd.DataFrame(flows).sort_index()
    for s in style_names:
        ser = (frame[s] if s in frame else pd.Series(dtype=float)).dropna()
        if ser.empty:
            summary.append(
                {
                    "style": s,
                    "mean": 0.0,
                    "std": 0.0,
                    "t": 0.0,
                    "ir": 0.0,
                    "cumulative": 0.0,
                }
            )
            continue
        v = ser.to_numpy(dtype=float)
        m = float(v.mean())
        sd = float(v.std())
        summary.append(
            {
                "style": s,
                "mean": m,
                "std": sd,
                "t": (m / (sd / np.sqrt(len(v)))) if sd > 0 else 0.0,
                "ir": (m / sd * np.sqrt(252)) if sd > 0 else 0.0,
                "cumulative": _cumprod_ret(v),
            }
        )

    cov = pd.DataFrame()
    if len(frame) > 2:
        cov = frame.cov() * 252

    return {
        "factor_returns": {s: flows[s] for s in style_names},
        "summary": summary,
        "cov": cov,
    }


def strategy_attribution(
    strategy_returns: pd.Series,
    portfolio_style_exposures: dict[str, pd.Series],
    style_returns: dict[str, pd.DataFrame],
) -> dict:
    """把策略收益粗略拆成风格贡献总和 + 纯 alpha（残差）

    port_ret_t = Σ_style (组合暴露_style,t × 因子收益_style,t) + alpha_t

    Returns:
        {style_contribution: {style: 累计贡献}, alpha_cum, alpha_series,
          alpha_vol, alpha_ir}
    """
    frame = pd.DataFrame(portfolio_style_exposures).sort_index()
    stylef = pd.DataFrame(style_returns).sort_index()
    common = frame.index.intersection(stylef.index)
    if len(common) == 0:
        base_ret = strategy_returns.dropna()
        return {
            "style_contribution": {},
            "alpha_cum": _cumprod_ret(base_ret.to_numpy()),
            "alpha_series": {str(k.date()): float(v) for k, v in base_ret.items()},
            "alpha_excess": _cumprod_ret(base_ret.to_numpy()) - 1.0,
            "alpha_ir": 0.0,
        }

    alpha = strategy_returns.reindex(common).fillna(0.0).copy()
    contrib: dict[str, float] = {}
    for s in frame.columns:
        if s not in stylef.columns:
            continue
        c = frame[s].reindex(common).fillna(0.0) * stylef[s].reindex(common).fillna(0.0)
        alpha = alpha - c
        contrib[s] = float(c.sum())

    alpha_arr = alpha.to_numpy()
    alpha_cum = _cumprod_ret(alpha_arr)
    sd = float(alpha.std())
    alpha_ir = (alpha.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0

    return {
        "style_contribution": contrib,
        "alpha_cum": alpha_cum,
        "alpha_series": {str(k.date()): float(v) for k, v in alpha.items()},
        "alpha_excess": float(alpha_cum),
        "alpha_ir": alpha_ir,
    }


# ── 行业暴露与行业因子收益（Barra 风格，均值偏离编码）────────────────────────


def build_industry_exposures(
    trade_dates: pd.DatetimeIndex,
    industry_map: dict[str, str] | None,
    top_k: int = 25,
) -> pd.DataFrame:
    """行业暴露面板 {index=date, columns=code}（均值偏离编码，逐股单值）

    每只股票的值为「其所属行业列在均值偏离编码下的取值」= 1 - 行业覆盖率
    （列内去均值：1 - freq_j/N）。截面回归时配合全部行业哑变量使用；
    组合级行业暴露 = Σ 权重 × 该值（近似，不含非本行业列的 -freq_j/N 项，
    报告时明示）。行业数超过 top_k 时小行业归入「其他」。

    Returns:
        DataFrame(index=trade_dates, columns=code)；无行业映射返回空 DataFrame。
    """
    if not industry_map:
        return pd.DataFrame()
    counts = pd.Series(industry_map).value_counts()
    if len(counts) > top_k:
        top = set(counts.head(top_k - 1).index)
        ind_of = {c: (ind if ind in top else "其他") for c, ind in industry_map.items()}
    else:
        ind_of = dict(industry_map)
    codes = sorted(ind_of.keys())
    n = len(codes)
    freq = pd.Series(ind_of).value_counts()
    values = {c: 1.0 - freq[ind_of[c]] / n for c in codes}
    return pd.DataFrame(
        {c: pd.Series(v, index=trade_dates) for c, v in values.items()},
        index=trade_dates,
        columns=codes,
    )


def industry_factor_returns(
    returns: pd.DataFrame,
    industry_map: dict[str, str] | None,
    min_stocks: int = 10,
) -> dict[str, dict]:
    """行业因子收益：每日截面回归 收益 = α + Σ 行业哑变量×行业收益 + 残差

    行业哑变量按行去均值（均值偏离编码）：行业因子收益解释为「该行业相对
    全市场平均的日超额收益」。

    Returns:
        {"factor_returns": {IND_行业: {date: fac_ret}}, "summary": [...]}
    """
    if not industry_map:
        return {"factor_returns": {}, "summary": []}
    inds = sorted({industry_map[c] for c in industry_map})
    flows: dict[str, dict] = {f"IND_{ind}": {} for ind in inds}

    for date, r in returns.iterrows():
        r_valid = r.dropna()
        if len(r_valid) < min_stocks:
            continue
        stocks = [c for c in r_valid.index if industry_map.get(c) in inds]
        if len(stocks) < min_stocks:
            continue
        y = r_valid.reindex(stocks).to_numpy(dtype=float)
        X = np.zeros((len(stocks), len(inds)))
        for j, ind in enumerate(inds):
            X[:, j] = [1.0 if industry_map[c] == ind else 0.0 for c in stocks]
        X = X - X.mean(axis=0)  # 均值偏离编码
        Xa = np.column_stack([np.ones(len(y)), X])
        try:
            coef, _, _, _ = np.linalg.lstsq(Xa, y, rcond=None)
        except Exception:
            continue
        for j, ind in enumerate(inds):
            flows[f"IND_{ind}"][date] = float(coef[j + 1])

    summary = []
    for name, d in flows.items():
        ser = pd.Series(d).dropna()
        if ser.empty:
            summary.append(
                {"style": name, "mean": 0.0, "std": 0.0, "t": 0.0, "ir": 0.0, "cumulative": 0.0}
            )
            continue
        v = ser.to_numpy(dtype=float)
        m = float(v.mean())
        sd = float(v.std())
        summary.append(
            {
                "style": name,
                "mean": m,
                "std": sd,
                "t": (m / (sd / np.sqrt(len(v)))) if sd > 0 else 0.0,
                "ir": (m / sd * np.sqrt(252)) if sd > 0 else 0.0,
                "cumulative": _cumprod_ret(v),
            }
        )
    return {"factor_returns": flows, "summary": summary}


# ── 组合权重优化（带约束）─────────────────────────────────────────────────


def optimize_weights(
    scores: pd.Series,
    covariance: pd.DataFrame | None = None,
    long_only: bool = True,
    max_position: float = 0.20,
    industry_map: dict[str, str] | None = None,
    max_industry_exposure: float = 0.30,
    gross_target: float = 1.0,
    risk_aversion: float = 1.0,
) -> pd.Series:
    """由信号得分构造带约束的截面权重（单期，SLSQP）

    目标: min 0.5*risk_aversion*w'Σw - (得分·w)
    约束: Σw = gross_target；单票 <= max_position；行业暴露 <= 上限

    Args:
        scores: 截面得分 Series（index=股票，越大越好，可含负=看空）
        covariance: 股票收益协方差（无则退化为按得分 + 约束）
        long_only: True 禁止做空
    Returns:
        权重 Series（index=股票，表和≈gross_target）
    """
    from scipy.optimize import minimize

    assets = list(scores.index)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    s = scores.reindex(assets).fillna(0.0).to_numpy(dtype=float)
    s = s - s.mean()

    bounds = [
        (0.0, max_position) if long_only else (-max_position, max_position)
    ] * n
    x0 = np.full(n, 1.0 / n)

    cov = None
    if covariance is not None and n > 1:
        cov = covariance.reindex(index=assets, columns=assets).fillna(0.0).to_numpy()

    cons = [{"type": "eq", "fun": lambda w: w.sum() - gross_target}]

    if industry_map and n > 1:
        inds = sorted({industry_map.get(a, "") for a in assets})
        for ind in inds:
            mask = np.array(
                [industry_map.get(a, "") == ind for a in assets], dtype=float
            )
            if mask.sum() == 0:
                continue
            cons.append(
                {
                    "type": "ineq",
                    "fun": lambda w, m=mask: max_industry_exposure * n
                    - abs(float(m @ w)) * n,
                }
            )

    def obj(w):
        var = 0.0
        if cov is not None:
            var = 0.5 * risk_aversion * float(w @ cov @ w)
        return var - float(s @ w)

    result = minimize(
        obj,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"maxiter": 300, "ftol": 1e-9},
    )
    w = np.clip(result.x, 0.0, gross_target) if long_only else result.x
    if w.sum() <= 1e-12:
        w = np.where(s > 0, 1.0, 0.0)
        w = w / (w.sum() or 1.0)
    return pd.Series(w, index=assets)


# ── 绩效补充指标（相对基准）──────────────────────────────────────────────


def extended_risk_metrics(
    returns: pd.Series,
    benchmark_returns: pd.Series | None = None,
    weights: pd.Series | None = None,
    benchmark_weights: pd.Series | None = None,
) -> dict:
    """补充 quantstats 之外的常用指标:alpha/beta、上行/下行捕获、Active Share"""
    returns = returns.dropna()
    if len(returns) < 2:
        return {"error": "no data"}

    res: dict = {
        "total_return": float((1 + returns).prod() - 1),
        "annual_vol": float(returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0,
    }

    if benchmark_returns is not None:
        bm = benchmark_returns.reindex(returns.index).dropna()
        if len(bm) >= 2:
            covs = np.cov(returns, bm, ddof=1)
            var_b = covs[1, 1]
            beta = float(covs[0, 1] / var_b) if var_b > 0 else 0.0
            rf_daily = (1 + RISKFREE) ** (1 / 252) - 1
            alpha_daily = float((returns - rf_daily).mean()) - beta * float(
                (bm - rf_daily).mean()
            )
            res["beta"] = beta
            res["alpha"] = float((1 + alpha_daily) ** 252 - 1)
            b_pos = bm[bm >= 0]
            b_neg = bm[bm < 0]
            if len(b_pos) > 0:
                up = returns[bm >= 0]
                res["upside_capture"] = float(up.mean() / b_pos.mean()) if b_pos.mean() != 0 else 0.0
            if len(b_neg) > 0:
                down = returns[bm < 0]
                res["downside_capture"] = float(down.mean() / b_neg.mean()) if b_neg.mean() != 0 else 0.0

    if weights is not None and benchmark_weights is not None:
        common = weights.index.intersection(benchmark_weights.index)
        if len(common):
            w = weights.reindex(common).fillna(0.0)
            b = benchmark_weights.reindex(common).fillna(0.0)
            res["active_share"] = float(0.5 * (w - b).abs().sum())

    return res


# ── 压力测试 / 情景分析 ──────────────────────────────────────────────────


def stress_test(
    returns: pd.DataFrame,
    weights: pd.Series,
    scenarios: dict[str, dict[str, float]] | None = None,
) -> dict:
    """针对组合的应力测试（单期收益冲击）

    Args:
        returns: 历史收益 DataFrame(index=date, columns=asset)
        weights: 当前组合权重 Series(index=asset)
        scenarios: {场景名: {asset: 单日冲击%}}，"_default" 表示其余资产的基准冲击。
    Returns:
        {scene: {impact_pct, per_asset_top: [...]}}
    """
    if scenarios is None:
        scenarios = {
            "sharp_crash": {"_default": -0.09},
            "vol_spike": {"_default": -0.04},
            "bull": {"_default": 0.06},
        }
    common = weights.dropna().index
    wsum = float(weights.reindex(common).sum()) or 1.0
    w = weights.reindex(common) / wsum

    out: dict[str, dict] = {}
    for name, shock in scenarios.items():
        default = shock.get("_default", 0.0)
        per_asset = pd.Series(default, index=common)
        for a, v in shock.items():
            if a != "_default":
                per_asset[a] = v
        impact = float((w * per_asset.reindex(common).fillna(default)).sum())
        # 识别冲击最大的几个标的
        top = (w * per_asset.reindex(common).fillna(default)).abs().sort_values(ascending=False).head(5)
        out[name] = {
            "impact_pct": impact,
            "impact_value": impact * wsum,
            "top_risk": [{"asset": k, "w": float(w[k]), "shock": float(per_asset[k])} for k in top.index],
        }
    return out


def covariance_estimator(
    returns: pd.DataFrame, shrinkage: float = 0.20
) -> pd.DataFrame:
    """年化样本协方差 + 向对角目标收缩，对多资产更稳健"""
    returns = returns.dropna(how="all")
    if len(returns) < 2 or returns.shape[1] < 1:
        return pd.DataFrame()
    sigma = returns.cov() * 252
    if shrinkage <= 0:
        return sigma
    diag = np.diag(np.diag(sigma))
    shrink = shrinkage * diag + (1 - shrinkage) * sigma
    return pd.DataFrame(shrink, index=sigma.index, columns=sigma.columns)


# ── 组合事前风险预测（因子协方差法） ────────────────────────────────────────


def risk_forecast(
    weights: pd.Series,
    factor_returns: dict[str, dict],
    portfolio_exposures: dict[str, pd.Series] | None = None,
    factor_cov: pd.DataFrame | None = None,
    returns: pd.DataFrame | None = None,
) -> dict:
    """组合事前风险预测：σ_port² = e' Σ_f e + Σ w_i² σ_resid,i²

    用风格/行业因子日收益协方差（年化）+ 个券残差方差预测组合未来波动，
    并把组合风险分解到每个因子与个券特异项（边际贡献占比）。

    Args:
        weights: 当前组合权重 Series(index=asset)
        factor_returns: {factor: {date: ret}}（来自 style_factor_returns 等）
        portfolio_exposures: {factor: Series(index=date, 组合暴露)}，缺省则
            按 0 处理（调用方应传组合暴露面板）
        factor_cov: 因子年化协方差（有则直接用；无则从 factor_returns 估算）
        returns: 个股收益面板（用于市场模型残差方差估计）

    Returns:
        {forecast_vol_annual, factor_risk_contrib: {factor: pct},
         idiosyncratic_pct, n_factors, n_assets, note}
    """
    if weights is None or weights.dropna().empty:
        return {"forecast_vol_annual": 0.0, "factor_risk_contrib": {}, "idiosyncratic_pct": 0.0, "n_factors": 0, "n_assets": 0, "note": "无权重数据，无法预测"}
    w = weights.dropna()
    assets = list(w.index)
    n_assets = len(assets)

    if factor_cov is None:
        frame = pd.DataFrame(factor_returns or {}).sort_index()
        if frame.shape[0] < 3 or frame.shape[1] < 1:
            return {"forecast_vol_annual": 0.0, "factor_risk_contrib": {}, "idiosyncratic_pct": 0.0, "n_factors": 0, "n_assets": n_assets, "note": "因子收益样本不足，无法估计协方差"}
        frame = frame.dropna(how="all")
        factor_cov = frame.cov() * 252
    if factor_cov.empty:
        return {"forecast_vol_annual": 0.0, "factor_risk_contrib": {}, "idiosyncratic_pct": 0.0, "n_factors": 0, "n_assets": n_assets, "note": "因子协方差为空"}

    factors = list(factor_cov.columns)
    n_factors = len(factors)
    # 组合对各因子的暴露（无面板时按近端暴露近似为 0——调用方应传 portfolio_exposures）
    e = np.zeros(n_factors)
    if portfolio_exposures:
        for j, f in enumerate(factors):
            s = portfolio_exposures.get(f)
            if s is not None and len(s):
                e[j] = float(s.iloc[-1])
    var_f = float(e @ factor_cov.to_numpy() @ e) if n_factors else 0.0

    # 个券特异风险：市场模型残差方差（r_i = α + β·市场 + resid，var(resid) 年化），
    # 权重平方加权（独立残差的组合贡献 Σ w_i² σ_i²）
    resid_var = 0.0
    try:
        ret = returns.reindex(columns=assets).dropna(how="all") if returns is not None else pd.DataFrame()
        if not ret.empty and len(ret) > 20:
            market = ret.mean(axis=1)
            resid_vars: list[float] = []
            for a in assets:
                s = ret[a].dropna()
                if len(s) < 20:
                    continue
                m = market.reindex(s.index).dropna()
                common_idx = s.index.intersection(m.index)
                if len(common_idx) < 20:
                    continue
                x = m.reindex(common_idx).to_numpy()
                y = s.reindex(common_idx).to_numpy()
                beta = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x)) if np.var(x) > 0 else 0.0
                resid = y - (beta * x)
                resid_vars.append(float(np.var(resid, ddof=1) * 252))
            w_arr = w.reindex(assets).fillna(0.0).to_numpy()
            if resid_vars:
                resid_var = float(sum((w_arr[i] ** 2) * resid_vars[i] for i in range(len(resid_vars))))
    except Exception:
        resid_var = 0.0
    total_var = var_f + resid_var
    vol = float(np.sqrt(max(total_var, 0.0)))

    contrib: dict[str, float] = {}
    if var_f > 1e-14 and n_factors:
        marginal = factor_cov.to_numpy() @ e
        for j, f in enumerate(factors):
            contrib[f] = round(float(e[j] * marginal[j] / total_var), 4)
    idio_pct = round(float(resid_var / total_var), 4) if total_var > 0 else 0.0

    return {
        "forecast_vol_annual": round(vol, 4),
        "factor_risk_contrib": contrib,
        "idiosyncratic_pct": idio_pct,
        "n_factors": n_factors,
        "n_assets": n_assets,
        "note": (
            "事前预测口径：σ_port² = 组合暴露'×因子协方差×暴露 + Σ w_i²×市场模型残差方差；"
            "因子边际贡献占比按 e_j×(Σe)_j/总方差"
        ),
    }


# ── 历史情景压力测试（真实行情窗口回放） ────────────────────────────────────


HISTORICAL_SCENARIOS: dict[str, tuple[str, str]] = {
    "2015股灾": ("2015-06-15", "2015-09-15"),
    "2016熔断": ("2016-01-04", "2016-02-29"),
    "2018熊市": ("2018-01-29", "2018-12-28"),
    "2020疫情冲击": ("2020-01-20", "2020-03-31"),
    "2024小微盘流动性危机": ("2024-01-02", "2024-02-08"),
}


def historical_scenario_stress(
    returns: pd.DataFrame,
    weights: pd.Series,
    scenario_windows: dict[str, tuple[str, str]] | None = None,
) -> dict:
    """历史情景回放：把真实危机窗口的逐日收益按当前权重累计到组合

    比正态模拟更有参考价值：直接使用真实市场当时的量价行为（流动性枯竭、
    涨跌停无法卖出等尾部表现已内含在收益序列中）。

    Args:
        returns: 历史收益面板 DataFrame(index=date, columns=asset)
        weights: 当前组合权重 Series(index=asset)

    Returns:
        {scenario: {start, end, n_days, cum_return_pct, max_drawdown_pct, worst_day_pct}}
    """
    if scenario_windows is None:
        scenario_windows = HISTORICAL_SCENARIOS
    common = weights.dropna().index
    w = weights.reindex(common)
    wsum = float(w.sum()) or 1.0
    w = w / wsum

    out: dict[str, dict] = {}
    for name, (start, end) in scenario_windows.items():
        win = returns.loc[returns.index >= pd.Timestamp(start)]
        win = win.loc[win.index <= pd.Timestamp(end)]
        if win.empty:
            out[name] = {"start": start, "end": end, "n_days": 0, "cum_return_pct": None, "max_drawdown_pct": None, "worst_day_pct": None, "note": "区间内无行情缓存"}
            continue
        port = win.reindex(columns=common).fillna(0.0)
        daily = (port.to_numpy() * w.to_numpy()[None, :]).sum(axis=1)
        cum = float(_cumprod_ret(daily) - 1.0)
        eq = np.cumprod(1 + daily)
        dd = float((eq / np.maximum.accumulate(eq) - 1.0).min())
        out[name] = {
            "start": start,
            "end": end,
            "n_days": int(len(win)),
            "cum_return_pct": round(cum * 100, 2),
            "max_drawdown_pct": round(dd * 100, 2),
            "worst_day_pct": round(float(np.min(daily)) * 100, 2),
        }
    return out


# ── 回测策略收益归因（回归法：不需要持仓权重，用风格因子日收益回归）──────────


def strategy_regression_attribution(
    strategy_returns: pd.Series,
    style_returns: dict[str, pd.DataFrame],
    min_obs: int = 30,
) -> dict:
    """收益归因（时序回归法）：组合日收益 ~ Σ β_style × 风格因子日收益 + alpha

    与暴露法（strategy_attribution）互补——不需要逐日持仓权重面板，
    只需要组合日收益 + 各风格因子日收益（来自 style_factor_returns），
    适合对已落库的回测记录（净值曲线）直接做归因。

    Returns:
        {
          ok: bool, message: str,
          beta: {style: β},                每风格回归系数
          contribution: {style: 累计贡献},  β_style × 因子收益逐日累加
          alpha_cum: 残差累计收益,
          alpha_annual: alpha 年化,
          alpha_ir: alpha 信息比率,
          r2: 风格因子解释的组合收益方差比例,
          n_obs: 有效样本数,
        }
    """
    sf = pd.concat(
        [df.rename(columns=lambda c: name) for name, df in style_returns.items()],
        axis=1,
    ).sort_index()
    ret = strategy_returns.dropna().sort_index()
    common = ret.index.intersection(sf.index)
    if len(common) < min_obs:
        return {
            "ok": False,
            "message": f"重叠样本不足 {min_obs} 个交易日（当前 {len(common)}），无法归因",
            "beta": {}, "contribution": {}, "alpha_cum": 0.0,
            "alpha_annual": 0.0, "alpha_ir": 0.0, "r2": 0.0, "n_obs": len(common),
        }
    X = sf.reindex(common)
    y = ret.reindex(common).to_numpy(dtype=float)

    # 多元回归 y = alpha_d + Σ β X（带截距）
    Xa = np.column_stack([np.ones(len(y)), X.to_numpy(dtype=float)])
    try:
        coef, _, _, _ = np.linalg.lstsq(Xa, y, rcond=None)
    except Exception as e:
        return {"ok": False, "message": f"回归失败: {e}", "beta": {},
                "contribution": {}, "alpha_cum": 0.0, "alpha_annual": 0.0,
                "alpha_ir": 0.0, "r2": 0.0, "n_obs": len(common)}

    alpha_daily = coef[0]
    betas = {s: float(coef[i + 1]) for i, s in enumerate(X.columns)}

    # 各风格累计贡献 = Σ β_s × f_s,t（逐日），alpha 序列 = y - Σ β f
    Xv = X.to_numpy(dtype=float)
    alpha_series = y - Xv @ coef[1:]
    contrib: dict[str, float] = {}
    for i, s in enumerate(X.columns):
        contrib[s] = _cumprod_ret((Xv[:, i] * coef[i + 1]).tolist()) if abs(coef[i + 1]) > 1e-12 else 0.0
    alpha_cum = _cumprod_ret(alpha_series.tolist())
    alpha_std = float(alpha_series.std())
    alpha_ir = (alpha_series.mean() / alpha_std * np.sqrt(252)) if alpha_std > 0 else 0.0

    # R² = 1 - SS_res/SS_tot
    ss_res = float(((y - (Xv @ coef[1:] + alpha_daily)) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return {
        "ok": True,
        "message": "",
        "beta": {s: round(v, 4) for s, v in betas.items()},
        "contribution": {s: round(v, 4) for s, v in contrib.items()},
        "alpha_daily": round(float(alpha_daily), 6),
        "alpha_cum": round(alpha_cum, 4),
        "alpha_annual": round(float((1 + alpha_daily) ** 252 - 1), 4),
        "alpha_ir": round(alpha_ir, 4),
        "r2": round(r2, 4),
        "n_obs": int(len(common)),
    }