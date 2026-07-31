"""IC / 分层分析对齐回归测试

锁住对齐约定：
- IC：T 日因子 vs T→T+p 前向累计收益（p=1 即次日收益）
- 分层：T 日因子分组 → T+1 日收益计入该组（无前视）
用构造的已知答案面板验证：完美预测因子 IC=1、随机因子 IC≈0、
故意前视的因子（用当日已实现收益）不会得到虚高 IC。
"""

import numpy as np
import pandas as pd

from backend.services.factor_research import FactorResearchService

svc = FactorResearchService()

N_STOCKS = 20
N_DAYS = 60


def _panel(seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """构造 (returns, close) 面板：r[T] 为 T-1→T 日收益"""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=N_DAYS)
    cols = [f"S{i:02d}" for i in range(N_STOCKS)]
    rets = pd.DataFrame(
        rng.normal(0.0, 0.02, size=(N_DAYS, N_STOCKS)), index=idx, columns=cols
    )
    rets.iloc[0] = 0.0
    close = (1 + rets).cumprod() * 100
    return rets, close


def test_perfect_factor_rank_ic_is_one():
    """T 日因子 = T+1 日收益 → period=1 RankIC 应为 1"""
    rets, _ = _panel()
    factor = rets.shift(-1)  # 完美预知次日收益
    result = svc.ic_analysis(factor.dropna(how="all"), rets, periods=[1])
    assert result["period_1"]["rank_ic_mean"] > 0.999
    assert result["period_1"]["ic_mean"] > 0.999


def test_perfect_factor_period5_cumulative():
    """T 日因子 = T→T+5 前向累计收益 → period=5 RankIC 应为 1"""
    rets, _ = _panel()
    fwd5 = ((1 + rets).shift(-1).rolling(5).apply(np.prod, raw=True)).shift(-4) - 1
    factor = fwd5.dropna(how="all")
    result = svc.ic_analysis(factor, rets, periods=[5])
    assert result["period_5"]["rank_ic_mean"] > 0.999


def test_lookahead_factor_not_rewarded():
    """前视陷阱：T 日因子 = T 日当日已实现收益，随机行情下 IC 应接近 0 而非 1"""
    rets, _ = _panel()
    factor = rets.copy()  # 用已实现收益冒充预测
    result = svc.ic_analysis(factor, rets, periods=[1])
    assert abs(result["period_1"]["ic_mean"]) < 0.3
    assert abs(result["period_1"]["rank_ic_mean"]) < 0.3


def test_random_factor_ic_near_zero():
    """随机因子 IC ≈ 0"""
    rets, _ = _panel()
    rng = np.random.default_rng(42)
    factor = pd.DataFrame(
        rng.normal(size=rets.shape), index=rets.index, columns=rets.columns
    )
    result = svc.ic_analysis(factor, rets, periods=[1])
    assert abs(result["period_1"]["ic_mean"]) < 0.15


def test_quantile_analysis_no_lookahead_and_monotonic():
    """分层：完美因子最高组累计收益应大于最低组；前视因子不应完美分层"""
    rets, _ = _panel()
    perfect = rets.shift(-1).dropna(how="all")
    q = svc.quantile_analysis(perfect, rets, n_groups=5)
    assert q["cumulative_returns"]["group_5"] > q["cumulative_returns"]["group_1"]
    # 平均单期收益严格递增（完美因子）
    means = [q["mean_return_by_group"][str(i)] for i in range(1, 6)]
    assert all(means[i] < means[i + 1] for i in range(4))

    # 前视因子（当日收益）分层收益不应呈现完美单调价差
    lookahead = svc.quantile_analysis(rets, rets, n_groups=5)
    la_means = [lookahead["mean_return_by_group"][str(i)] for i in range(1, 6)]
    spread_la = la_means[-1] - la_means[0]
    spread_ok = means[-1] - means[0]
    assert spread_la < spread_ok * 0.5  # 前视被消除后价差应显著小于真实预测


def test_full_factor_analysis_smoke():
    """完整报告在修正对齐后可正常产出核心区块"""
    rets, _ = _panel()
    perfect = rets.shift(-1).dropna(how="all")
    report = svc.full_factor_analysis(perfect, rets, periods=[1, 5], n_groups=5)
    assert report["summary"]["rank_ic"] > 0.9
    assert len(report["group_perf"]) >= 5
    assert report["summary"]["monotonicity"] >= 0.75
