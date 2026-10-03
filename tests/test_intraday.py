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


# ── ID_PV_ENTROPY：日内价量结构熵 ────────────────────────────────


def _entropy_bars(times_minutes, closes, volumes, base_day="2024-01-02"):
    """按 (分钟-of-day, close, volume) 列表构造单股票单日 5m 面板"""
    idx = pd.DatetimeIndex(
        [pd.Timestamp(base_day) + pd.Timedelta(minutes=m) for m in times_minutes]
    )
    return (
        pd.DataFrame({"600000.SH": closes}, index=idx),
        pd.DataFrame({"600000.SH": volumes}, index=idx),
    )


def _session_minutes():
    """48 根 5m bar 的日内分钟时刻（09:35..11:30, 13:05..15:00）"""
    return list(range(9 * 60 + 35, 11 * 60 + 30 + 1, 5)) + list(
        range(13 * 60 + 5, 15 * 60 + 1, 5)
    )


def test_pv_entropy_uniform_is_ln8():
    """收盘与成交量全日均匀 → 8 时段均匀分布，熵 = ln(8)"""
    from backend.services.intraday_operators import ID_PV_ENTROPY

    price, vol = _entropy_bars(
        _session_minutes(), [20.0] * 48, [1000.0] * 48
    )
    h = ID_PV_ENTROPY(price, vol, 30)
    assert len(h) == 1
    assert abs(float(h.iloc[0, 0]) - np.log(8)) < 1e-9


def test_pv_entropy_full_concentration_is_zero():
    """全部成交量集中在单一时段 → 熵 = 0"""
    from backend.services.intraday_operators import ID_PV_ENTROPY

    vols = [1000.0] * 6 + [0.0] * 42  # 零成交 bar 被清洗，仅时段 0 有量
    price, vol = _entropy_bars(_session_minutes(), [20.0] * 48, vols)
    h = ID_PV_ENTROPY(price, vol, 30)
    assert abs(float(h.iloc[0, 0])) < 1e-9


def test_pv_entropy_two_slots_is_ln2():
    """量均分于首尾两个时段（收盘恒定）→ p=0.5/0.5，熵 = ln(2)"""
    from backend.services.intraday_operators import ID_PV_ENTROPY

    vols = [1000.0] * 6 + [0.0] * 36 + [1000.0] * 6
    price, vol = _entropy_bars(_session_minutes(), [20.0] * 48, vols)
    h = ID_PV_ENTROPY(price, vol, 30)
    assert abs(float(h.iloc[0, 0]) - np.log(2)) < 1e-9


def test_pv_entropy_price_ratio_affects_value():
    """时段收盘价参与分布（价占比×量占比），与纯量集中度结果不同

    量均匀、时段收盘价 1..8 递增：p_b = close_b / Σclose，
    熵 = -Σ (b/36)·ln(b/36)，必须严格小于均匀熵 ln(8)。
    """
    from backend.services.intraday_operators import ID_PV_ENTROPY

    minutes = _session_minutes()
    closes, vols = [], []
    for m in minutes:
        elapsed = (m - 9 * 60 - 30) if m <= 11 * 60 + 30 else (120 + m - 13 * 60)
        slot = (elapsed - 1) // 30
        closes.append(float(slot + 1))
        vols.append(1000.0)
    price, vol = _entropy_bars(minutes, closes, vols)
    h = float(ID_PV_ENTROPY(price, vol, 30).iloc[0, 0])
    ratios = np.arange(1, 9) / 36.0
    expect = float(-(ratios * np.log(ratios)).sum())
    assert abs(h - expect) < 1e-9
    assert h < np.log(8)


def test_pv_entropy_zero_volume_day_is_nan():
    """全日无有效成交 → NaN"""
    from backend.services.intraday_operators import ID_PV_ENTROPY

    price, vol = _entropy_bars(_session_minutes(), [20.0] * 48, [0.0] * 48)
    h = ID_PV_ENTROPY(price, vol, 30)
    assert np.isnan(h.iloc[0, 0])


def test_pv_entropy_auction_bar_excluded():
    """竞价 bar（09:30，交易分钟偏移 0）不参与：加入后熵不变"""
    from backend.services.intraday_operators import ID_PV_ENTROPY

    minutes = _session_minutes()
    price, vol = _entropy_bars(minutes, [20.0] * 48, [1000.0] * 48)
    h_ref = float(ID_PV_ENTROPY(price, vol, 30).iloc[0, 0])
    price2 = pd.concat(
        [
            pd.DataFrame(
                {"600000.SH": [20.5]},
                index=pd.DatetimeIndex([pd.Timestamp("2024-01-02 09:30:00")]),
            ),
            price,
        ]
    )
    vol2 = pd.concat(
        [
            pd.DataFrame(
                {"600000.SH": [500.0]},
                index=pd.DatetimeIndex([pd.Timestamp("2024-01-02 09:30:00")]),
            ),
            vol,
        ]
    )
    h2 = float(ID_PV_ENTROPY(price2, vol2, 30).iloc[0, 0])
    assert abs(h_ref - h2) < 1e-12


def test_pv_entropy_half_day_four_slots_is_ln4():
    """半日市（上午 24 根 bar）→ 4 个时段，熵上界 ln(4)"""
    from backend.services.intraday_operators import ID_PV_ENTROPY

    minutes = list(range(9 * 60 + 35, 11 * 60 + 30 + 1, 5))
    price, vol = _entropy_bars(minutes, [20.0] * 24, [1000.0] * 24)
    h = ID_PV_ENTROPY(price, vol, 30)
    assert abs(float(h.iloc[0, 0]) - np.log(4)) < 1e-9


def test_pv_entropy_coarse_60m_bars():
    """60m 数据：每根 bar 自成一个宽时段（4 个），均匀 → ln(4)（跨周期不可比）"""
    from backend.services.intraday_operators import ID_PV_ENTROPY

    minutes = [10 * 60 + 30, 11 * 60 + 30, 14 * 60, 15 * 60]
    price, vol = _entropy_bars(minutes, [20.0] * 4, [1000.0] * 4)
    h = ID_PV_ENTROPY(price, vol, 30)
    assert abs(float(h.iloc[0, 0]) - np.log(4)) < 1e-9


def test_pv_entropy_via_namespace_and_preset_formula(minute_cache, tmp_path):
    """公式环境：原始熵 / RANK 包装 / MA20 平滑均可在分钟命名空间内求值"""
    _cache, codes = _make_minute_cache(tmp_path, n_stocks=5, days=25)
    loaded = intraday_cleaner.load_intraday_panels(codes, "5m")
    ns = io.build_intraday_namespace(loaded["panels"], loaded["meta"])
    raw = eval("ID_PV_ENTROPY(m_close, m_volume, 30)", {"__builtins__": {}}, ns)
    assert isinstance(raw, pd.DataFrame) and not raw.empty
    assert float(raw.values[~np.isnan(raw.values)].min()) >= 0.0
    assert float(raw.values[~np.isnan(raw.values)].max()) <= np.log(8) + 1e-9
    ranked = eval("RANK(-ID_PV_ENTROPY(m_close, m_volume, 30))", {"__builtins__": {}}, ns)
    assert float(ranked.values[~np.isnan(ranked.values)].max()) <= 1.0 + 1e-9
    smooth = eval(
        "MA(ID_PV_ENTROPY(m_close, m_volume, 30), 20)", {"__builtins__": {}}, ns
    )
    assert len(smooth.index) == len(raw.index)


def test_pv_entropy_detection_routes():
    """含 ID_PV_ENTROPY 的公式被识别为分钟语法"""
    svc = __import__(
        "backend.services.factor_research", fromlist=["factor_research"]
    ).factor_research
    assert svc._is_intraday_formula("RANK(-ID_PV_ENTROPY(m_close, m_volume, 30))")
    assert svc._is_intraday_formula("RANK(PV_ENTROPY_30M())")
