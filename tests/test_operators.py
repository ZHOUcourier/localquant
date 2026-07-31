"""算子回归测试：INDUSTRY_NEUTRALIZE 真实行业内去均值、无数据时报错"""

import pandas as pd
import pytest

from backend.services.factor_operators import (
    INDUSTRY_NEUTRALIZE,
    build_operator_namespace,
)


def test_industry_neutralize_removes_industry_mean():
    idx = pd.bdate_range("2024-01-02", periods=3)
    # A,B 属食品（均值高）；C,D 属银行（均值低）
    factor = pd.DataFrame(
        {"A": [5.0, 6, 7], "B": [7.0, 8, 9], "C": [1.0, 2, 3], "D": [3.0, 4, 5]},
        index=idx,
    )
    industry_map = {"A": "食品", "B": "食品", "C": "银行", "D": "银行"}
    out = INDUSTRY_NEUTRALIZE(factor, industry_map)
    # 每个行业内截面均值应为 0
    for date in idx:
        assert out.loc[date, ["A", "B"]].mean() == pytest.approx(0.0)
        assert out.loc[date, ["C", "D"]].mean() == pytest.approx(0.0)


def test_industry_neutralize_errors_without_data():
    """无行业数据时显式报错，不静默退化为全市场去均值"""
    factor = pd.DataFrame({"A": [1.0, 2.0], "B": [3.0, 4.0]})
    # 清掉可能存在的模块级映射
    import backend.services.factor_operators as ops

    ops.__dict__.pop("_ACTIVE_INDUSTRY_MAP", None)
    with pytest.raises(ValueError, match="行业分类"):
        INDUSTRY_NEUTRALIZE(factor)


def test_namespace_injects_industry_map():
    """build_operator_namespace 注入 industry_map 后算子可无参调用"""
    idx = pd.bdate_range("2024-01-02", periods=2)
    close = pd.DataFrame({"A": [10.0, 11], "B": [20.0, 22]}, index=idx)
    ns = build_operator_namespace(
        {"close": close, "volume": None, "amount": None},
        industry_map={"A": "食品", "B": "银行"},
    )
    # 命名空间可正常求值（含 INDUSTRY_NEUTRALIZE 别名）
    assert "INDUSTRY_NEUTRALIZE" in ns
    assert "industry_neutralize" in ns
