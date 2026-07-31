"""P1-A 空壳修复回归测试：ic_weighted 加权、PCA 降维"""

import numpy as np
import pandas as pd
import pytest

from backend.services.factor_research import FactorResearchService

svc = FactorResearchService()


def _panel(seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-02", periods=60)
    cols = [f"S{i:02d}" for i in range(20)]
    rets = pd.DataFrame(rng.normal(0, 0.02, size=(60, 20)), index=idx, columns=cols)
    rets.iloc[0] = 0.0
    return rets


def test_ic_weighted_favors_predictive_factor():
    """ic_weighted：高 IC 因子权重应显著大于噪音因子"""
    rets = _panel()
    good = rets.shift(-1).dropna(how="all")  # 完美预测因子
    rng = np.random.default_rng(99)
    noise = pd.DataFrame(
        rng.normal(size=good.shape), index=good.index, columns=good.columns
    )
    weights = svc._ic_weights({"good": good, "noise": noise}, rets, ic_window=120)
    assert abs(weights["good"]) > abs(weights["noise"])
    # |权重| 归一（和为 1）
    assert abs(weights["good"]) + abs(weights["noise"]) == pytest.approx(1.0, abs=1e-6)


def test_ic_weighted_requires_return_data():
    """无 return_data 时报错，而非静默退化等权"""
    rets = _panel()
    good = rets.shift(-1).dropna(how="all")
    with pytest.raises(ValueError, match="return_data"):
        svc.multi_factor_combine({"a": good, "b": good}, method="ic_weighted")


def test_pca_reduces_dimensions():
    """特征工程 PCA 分支：输出主成分列 PC1.."""
    from backend.plugins.builtin.feature_engineering import (
        FeatureEngineeringInput,
        FeatureEngineeringNode,
    )

    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2024-01-02", periods=50)
    df = pd.DataFrame(
        {
            "f1": rng.normal(size=50),
            "f2": rng.normal(size=50),
            "f3": rng.normal(size=50),
        },
        index=idx,
    )
    node = FeatureEngineeringNode()
    out = node.run(FeatureEngineeringInput(data=df, method="pca", pca_variance=0.95))
    assert out.data is not None
    assert any(c.startswith("PC") for c in out.data.columns)
    assert all(name.startswith("PC") for name in out.feature_names)
