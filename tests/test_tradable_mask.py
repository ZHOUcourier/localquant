"""P0-6 可交易掩码一致性与探索去指数测试

验证：
- compute 生成的 artifact 含 tradable_mask，分析端点可按 token 解析（_resolve_tradable_mask）
- factor_decay 接受 mask 参数
- 探索 _cache_files(exclude_indices=True) 剔除指数
"""

import numpy as np
import pandas as pd

from backend.services import market_data
from backend.services.factor_research import factor_research


def test_factor_decay_accepts_mask():
    """factor_decay 支持 mask：剔除不可交易标的后 IC 仍可计算"""
    dates = pd.bdate_range("2023-01-02", periods=60)
    codes = [f"{600000 + i}.SH" for i in range(20)]
    rng = np.random.default_rng(1)
    factor = pd.DataFrame(rng.normal(0, 1, (60, 20)), index=dates, columns=codes)
    rets = rng.normal(0.0005, 0.02, (60, 20))
    returns = pd.DataFrame(rets, index=dates, columns=codes)
    # 掩码：全部可交易
    mask = pd.DataFrame(True, index=dates, columns=codes)
    out = factor_research.factor_decay(factor, returns, max_period=5, mask=mask)
    assert "decay_series" in out
    assert len(out["decay_series"]) == 5


def test_cache_files_exclude_indices(tmp_path, monkeypatch):
    """_cache_files(exclude_indices=True) 剔除宽基指数缓存文件"""
    from backend.data.cache import DataCache
    from backend.routes import explorer as explorer_route

    cache = DataCache(tmp_path)
    dates = pd.bdate_range("2023-01-02", periods=10)
    df = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1e6, "amount": 1e6},
        index=dates,
    )
    # 两只股票 + 一个宽基指数
    for c in ["600000.SH", "000001.SZ", "000300.SH"]:
        cache.save(c, "1d", df)
    monkeypatch.setattr(market_data, "_cache", cache)
    monkeypatch.setattr(explorer_route.settings, "cache_dir", tmp_path)

    all_files = explorer_route._cache_files("1d", exclude_indices=False)
    stock_files = explorer_route._cache_files("1d", exclude_indices=True)
    all_codes = {explorer_route._file_code(f) for f in all_files}
    stock_codes = {explorer_route._file_code(f) for f in stock_files}
    assert "000300.SH" in all_codes
    assert "000300.SH" not in stock_codes
    assert "600000.SH" in stock_codes


def test_compute_stores_tradable_mask_and_resolve(tmp_path, monkeypatch):
    """compute 落 artifact 含 tradable_mask，_resolve_tradable_mask 可按 token 解析"""
    from backend.routes.factor import _resolve_tradable_mask
    from backend.services.panel_artifact import store_panels

    dates = pd.bdate_range("2023-01-02", periods=30)
    codes = [f"{600000 + i}.SH" for i in range(15)]
    mask = pd.DataFrame(True, index=dates, columns=codes)
    mask.iloc[5, 3] = False  # 某日某股不可交易
    factor = pd.DataFrame(np.ones((30, 15)), index=dates, columns=codes)

    token = store_panels({"factor_data": factor, "tradable_mask": mask})
    resolved = _resolve_tradable_mask(token, factor)
    assert resolved is not None
    assert resolved.loc[dates[5], codes[3]] == False
    # 无 token 返回 None
    assert _resolve_tradable_mask("", factor) is None
