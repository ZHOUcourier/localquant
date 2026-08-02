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


def _cumprod_ret(a: np.ndarray) -> float:
    """返回一段收益率数组累计收益（-1 保护）"""
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