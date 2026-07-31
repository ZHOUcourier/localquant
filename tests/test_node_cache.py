"""节点级缓存回归测试：缓存命中/失效、参数变化与代码变化触发失效"""

import pandas as pd

from backend.engine import runner


def _clear():
    runner.clear_node_cache()


def test_cache_key_stable_for_same_input():
    """相同节点+相同输入 → 相同 cache_key"""
    merged = {"code_list": "000001.SZ", "period": "1d"}
    k1 = runner._compute_cache_key("QMTKlineNode", merged)
    k2 = runner._compute_cache_key("QMTKlineNode", dict(merged))
    assert k1 == k2


def test_cache_key_changes_with_param():
    """参数变化 → cache_key 变化（下游改参数即失效）"""
    k1 = runner._compute_cache_key("N", {"p": 1})
    k2 = runner._compute_cache_key("N", {"p": 2})
    assert k1 != k2


def test_cache_key_changes_with_code_text():
    """代码文本变化 → cache_key 变化（代码类节点改代码即失效）"""
    k1 = runner._compute_cache_key("CodeNode", {"code": "factor_data = close"})
    k2 = runner._compute_cache_key("CodeNode", {"code": "factor_data = -close"})
    assert k1 != k2


def test_cache_key_changes_with_upstream_dataframe():
    """上游 DataFrame 内容变化 → cache_key 变化"""
    df1 = pd.DataFrame({"A": [1.0, 2.0]})
    df2 = pd.DataFrame({"A": [1.0, 3.0]})
    k1 = runner._compute_cache_key("N", {"data": df1})
    k2 = runner._compute_cache_key("N", {"data": df2})
    assert k1 != k2


def test_cache_store_and_load_roundtrip():
    """存储后可命中加载；清空后失效"""
    _clear()
    key = runner._compute_cache_key("N", {"p": 42})
    assert runner._cache_load(key) is None
    runner._cache_store(key, {"result": 123})
    loaded = runner._cache_load(key)
    assert loaded == {"result": 123}
    runner.clear_node_cache()
    assert runner._cache_load(key) is None
