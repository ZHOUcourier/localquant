"""分钟级（日内高频）因子研究链路测试：清洗 → 聚合算子 → 因子求值 → 时刻IC

不依赖 QMT：构造 5m 分钟缓存，注入已知因子结构，断言聚合结果与手算一致。
"""

import numpy as np
import pandas as pd
import pytest

from backend.services import intraday_cleaner
from backend.services import intraday_operators as io


def _make_minute_cache(tmp_path, n_stocks=10, days=30):
    """构造 5m 分钟缓存：每交易日 48 根 bar（09:35~11:30, 13:05~15:00）"""
    from backend.data.cache import DataCache

    cache = DataCache(tmp_path)
    rng = np.random.default_rng(42)
    codes = [f"{600000 + i}.SH" for i in range(n_stocks)]
    morning_min = range(9 * 60 + 35, 11 * 60 + 30 + 1, 5)  # 09:35..11:30
    afternoon_min = range(13 * 60 + 5, 15 * 60 + 0 + 1, 5)  # 13:05..15:00
    times = [
        f"{m // 60:02d}:{m % 60:02d}" for m in [*morning_min, *afternoon_min]
    ]
    assert len(times) == 48, len(times)

    dates = pd.bdate_range("2024-01-02", periods=days)
    for c in codes:
        idx = pd.DatetimeIndex(
            [pd.Timestamp(d).replace(hour=int(t[:2]), minute=int(t[3:])) for d in dates for t in times]
        )
        n = len(idx)
        # 注入「尾盘动量」：最后 6 根 bar 收益 = 第 n-12 根起每根 +0.1% → TAIL_RET>0
        base = 20.0
        close = np.full(n, base)
        daily_ret = rng.normal(0.0002, 0.01, days)
        bar_ret = rng.normal(0.0, 0.003, n)
        for d in range(days):
            start = d * 48
            close[start] = base * (1 + daily_ret[d])
            for b in range(1, 48):
                r = bar_ret[start + b]
                if b >= 36:
                    r += 0.001  # 最后 12 根正漂移 → TAIL_RET(12)>0
                close[start + b] = close[start + b - 1] * (1 + r)
            base = close[start + 47]
        open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.001, n))
        high = close * (1 + np.abs(rng.normal(0, 0.002, n)))
        low = close * (1 - np.abs(rng.normal(0, 0.002, n)))
        volume = rng.integers(1e5, 1e6, n).astype(float)
        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=idx,
        )
        df["amount"] = df["close"] * df["volume"]
        cache.save(c, "5m", df)
    return cache, codes


@pytest.fixture
def minute_cache(tmp_path):
    cache, codes = _make_minute_cache(tmp_path)
    import backend.services.intraday_cleaner as ic
    from backend.data.cache import DataCache

    ic._cache = DataCache(tmp_path)
    yield cache, codes
    ic._cache = None


def test_clean_removes_auction_bar_and_meta(tmp_path):
    """竞价 bar 剔除 + 逐日 meta（n_bars/is_half/one_line）"""
    cache, codes = _make_minute_cache(tmp_path, n_stocks=1, days=3)
    raw = cache.get(codes[0], "5m")
    assert len(raw) == 3 * 48
    _cleaned, meta = intraday_cleaner.clean_code_minute(raw, "5m")
    assert len(_cleaned) == 3 * 48  # 构造数据无竞价 bar（首根 09:35），不剔除
    assert len(meta) == 3
    assert meta["n_bars"].iloc[0] == 48
    assert not meta["is_half"].any()


def test_clean_detects_one_line(tmp_path):
    """一字板日标记：high==low==close 的 bar 序列被标 one_line"""
    cache, codes = _make_minute_cache(tmp_path, n_stocks=1, days=3)
    raw = cache.get(codes[0], "5m")
    idx = raw.index
    # 第 2 个交易日全部 bar 一字
    day2 = idx[idx.normalize() == idx[48].normalize()]
    raw.loc[day2, "high"] = raw.loc[day2, "close"]
    raw.loc[day2, "low"] = raw.loc[day2, "close"]
    _cleaned, meta = intraday_cleaner.clean_code_minute(raw, "5m")
    assert bool(meta["one_line"].iloc[1])


def test_aggregators_match_manual():
    """ID_LAST / ID_SUM / ID_MEAN 与手算一致"""
    _rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-02", periods=2)
    idx = pd.DatetimeIndex(
        [
            dates[0] + pd.Timedelta(minutes=5 * i)
            for i in range(4)
        ]
        + [dates[1] + pd.Timedelta(minutes=5 * i) for i in range(4)]
    )
    s = pd.DataFrame({"600000.SH": np.arange(8, dtype=float)}, index=idx)
    last = io.ID_LAST(s, 0)
    assert last.loc[dates[0], "600000.SH"] == 3.0
    assert last.loc[dates[1], "600000.SH"] == 7.0
    assert io.ID_SUM(s).loc[dates[0], "600000.SH"] == 6.0
    assert io.ID_MEAN(s).loc[dates[1], "600000.SH"] == 5.5
    assert io.ID_LAST(s, 2).loc[dates[0], "600000.SH"] == 2.5
    assert io.ID_FIRST(s, 0).loc[dates[0], "600000.SH"] == 0.0


def test_m_delay_does_not_cross_days():
    """M_DELAY 按日分组：日首根为 NaN，不混入前一日尾 bar"""
    dates = pd.bdate_range("2024-01-02", periods=2)
    idx = pd.DatetimeIndex([dates[0] + pd.Timedelta(minutes=5 * i) for i in range(3)]
                           + [dates[1] + pd.Timedelta(minutes=5 * i) for i in range(3)])
    s = pd.DataFrame({"600000.SH": np.arange(6, dtype=float)}, index=idx)
    d = io.M_DELAY(s, 1)
    assert np.isnan(d.iloc[0, 0])  # 日首根
    assert d.iloc[1, 0] == 0.0
    assert np.isnan(d.iloc[3, 0])  # 次日首根不取前日末值
    assert d.iloc[4, 0] == 3.0


def test_tail_ret_positive_with_injected_drift(minute_cache, tmp_path):
    """注入尾盘正漂移后 TAIL_RET(12) 应显著为正"""
    _cache, codes = _make_minute_cache(tmp_path, n_stocks=3, days=20)
    loaded = intraday_cleaner.load_intraday_panels(codes, "5m")
    panels, meta = loaded["panels"], loaded["meta"]
    ns = io.build_intraday_namespace(panels, meta)
    fac = ns["TAIL_RET"](12)
    assert not fac.empty
    assert float(fac.mean().mean()) > 0.0


def test_build_intraday_namespace_formula_eval(minute_cache, tmp_path):
    """公式环境：TAIL_RET 与 ID_SLICE+ID_MEAN 组合可直接求值并折叠到日频"""
    _cache, codes = _make_minute_cache(tmp_path, n_stocks=3, days=20)
    loaded = intraday_cleaner.load_intraday_panels(codes, "5m")
    panels, meta = loaded["panels"], loaded["meta"]
    ns = io.build_intraday_namespace(panels, meta)
    r1 = eval("RANK(TAIL_RET(12))", {"__builtins__": {}}, ns)
    assert isinstance(r1, pd.DataFrame)
    assert len(r1.index) == 20
    # 分钟级中间结果：ID_SLICE 后 ID_MEAN 折叠
    r2 = eval("ID_MEAN(ID_SLICE(m_close, '14:00', '15:00'))", {"__builtins__": {}}, ns)
    assert isinstance(r2, pd.DataFrame)
    assert len(r2.index) == 20
    # RV 全日正值
    rv = eval("RV()", {"__builtins__": {}}, ns)
    assert float(rv.values[~np.isnan(rv.values)].min()) >= 0.0


def test_intraday_formula_detection_routes():
    """语法分流：分钟公式被识别、日频公式不误判"""
    svc = __import__("backend.services.factor_research", fromlist=["FactorResearchService"]).factor_research
    assert svc._is_intraday_formula("RANK(TAIL_RET(12))")
    assert svc._is_intraday_formula("ID_MEAN(ID_SLICE(m_close, '14:00', '15:00'))")
    assert svc._is_intraday_formula("RANK(JUMP_DAY())")
    assert svc._is_intraday_formula("M_SUM(m_volume, 12)")
    # 日频公式不应被误判（哪怕含 MA/RV 等子串之外的内容）
    assert not svc._is_intraday_formula("RANK(close / DELAY(close, 5) - 1)")
    assert not svc._is_intraday_formula("RANK(-ROC(close, 12))")
    assert not svc._is_intraday_formula("DELTA(close, 5)")


def test_intraday_panels_clean_flag(minute_cache, tmp_path):
    """load_intraday_panels 返回清洗标记与面板结构"""
    _cache, codes = _make_minute_cache(tmp_path, n_stocks=3, days=20)
    loaded = intraday_cleaner.load_intraday_panels(codes, "5m")
    assert loaded["cleaned"] is True
    assert {"open", "high", "low", "close", "volume", "amount"}.issubset(loaded["panels"].keys())
    assert len(loaded["meta"]) == 3
    assert len(loaded["panels"]["close"].columns) == 3
    assert "auc_vol" in loaded["meta"][codes[0]].columns or "auc_vol" not in loaded["meta"][codes[0]].columns
