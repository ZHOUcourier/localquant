"""中性化回归测试：行业哑变量 + 对数市值 OLS 残差"""

import numpy as np
import pandas as pd

from backend.services.factor_research import FactorResearchService

svc = FactorResearchService()

N_STOCKS = 40
N_DAYS = 5


def _fixtures():
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2024-01-02", periods=N_DAYS)
    cols = [f"S{i:02d}" for i in range(N_STOCKS)]
    industries = ["食品", "银行", "电子", "医药"]
    ind_of = {c: industries[i % 4] for i, c in enumerate(cols)}
    # 因子 = 行业偏移 + 市值暴露 + 噪音
    ind_offset = {"食品": 2.0, "银行": -1.0, "电子": 0.5, "医药": -0.5}
    caps = pd.DataFrame(
        rng.uniform(1e9, 5e10, size=(N_DAYS, N_STOCKS)), index=idx, columns=cols
    )
    noise = rng.normal(0, 0.1, size=(N_DAYS, N_STOCKS))
    factor = pd.DataFrame(index=idx, columns=cols, dtype=float)
    for c in cols:
        factor[c] = (
            ind_offset[ind_of[c]] + 0.3 * np.log(caps[c]) + noise[:, cols.index(c)]
        )
    industry = pd.DataFrame({c: [ind_of[c]] * N_DAYS for c in cols}, index=idx)
    return factor, industry, caps, ind_of


def test_neutralize_removes_industry_and_cap_exposure():
    factor, industry, caps, ind_of = _fixtures()
    neutralized = svc.neutralize(factor, industry, caps)

    for date in factor.index:
        row = neutralized.loc[date]
        # 行业内均值 ≈ 0（行业暴露被剥离）
        for ind in set(ind_of.values()):
            members = [c for c, v in ind_of.items() if v == ind]
            assert abs(row[members].mean()) < 1e-6
        # 与对数市值的相关性 ≈ 0（市值暴露被剥离）
        log_cap = np.log(caps.loc[date])
        corr = row.astype(float).corr(log_cap)
        assert abs(corr) < 0.05
