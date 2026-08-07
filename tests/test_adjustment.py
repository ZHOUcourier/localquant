"""复权因子存储测试：raw + adjust_factor 增量一致性 / 旧缓存兼容 / 读取口径"""

import pandas as pd
import pytest

from backend.services import market_data


def _synthetic_split_frame(days: list, factor_before: float = 1.0, factor_after: float = 2.0):
    """构造含一次 2:1 除权事件的缓存帧（不复权价 + adjust_factor）

    除权日 split_day：raw 价格减半；factor 从 factor_before 跳到 factor_after
    （后复权锚定上市日：事件之后 ×factor，历史不变）。
    """
    n = len(days)
    split_at = n // 2
    # 除权前：10 + i*0.5；除权日（2:1 拆股）：价格精确减半后继续
    pre_close = 10 + (split_at - 1) * 0.5
    raw = pd.Series(
        [10 + i * 0.5 if i < split_at else pre_close / 2 + (i - split_at) * 0.5
         for i in range(n)],
        index=days, dtype=float,
    )
    factor = pd.Series([factor_before] * split_at + [factor_after] * (n - split_at), index=days)
    df = pd.DataFrame({"open": raw, "high": raw * 1.01, "low": raw * 0.99,
                       "close": raw, "volume": 1e6, "amount": 1e7,
                       "adjust_factor": factor})
    return df


class TestAdjustFactor:
    def test_qfq_continuous_across_split(self):
        days = pd.bdate_range("2024-01-01", periods=100)
        df = _synthetic_split_frame(days)
        out = market_data._apply_adjust(df, "000001.SZ", "qfq")
        # 前复权后除权日前后应连续（无跳变）
        split = days[50]
        assert abs(out["close"].loc[split] - out["close"].loc[days[49]]) < 1e-6
        # 除权后价格=raw（factor=latest）
        assert out["close"].iloc[-1] == df["close"].iloc[-1]

    def test_hfq_unchanged_history_after_new_event(self):
        """增量自洽核心：新增除权事件后，历史 hfq 价不变（无需重写历史缓存）"""
        days1 = pd.bdate_range("2024-01-01", periods=100)
        df1 = _synthetic_split_frame(days1, factor_before=1.0, factor_after=2.0)
        hfq_before = market_data._apply_adjust(df1, "000001.SZ", "hfq")["close"].iloc[50]

        # 第二次除权（factor 2→3）增量追加：新行 factor=3，历史行保持 factor=2
        days2 = pd.bdate_range(days1[-1] + pd.Timedelta(days=1), periods=20)
        n2 = len(days2)
        raw2 = pd.Series([15 + i * 0.3 for i in range(n2)], index=days2)
        df2 = pd.DataFrame({"open": raw2, "high": raw2 * 1.01, "low": raw2 * 0.99,
                            "close": raw2, "volume": 1e6, "amount": 1e7,
                            "adjust_factor": 3.0})
        combined = pd.concat([df1, df2])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()

        hfq_after = market_data._apply_adjust(combined, "000001.SZ", "hfq")["close"].loc[days1[50]]
        assert abs(hfq_after - hfq_before) < 1e-9

        # qfq 新锚点（最新 factor=3）：历史价格整体按 2/3 缩放（前复权语义）
        qfq = market_data._apply_adjust(combined, "000001.SZ", "qfq")
        assert abs(qfq["close"].loc[days1[50]] - df1["close"].iloc[50] * 2.0 / 3.0) < 1e-9

    def test_legacy_cache_qfq_compat_and_hfq_error(self):
        """旧版前复权缓存（无 adjust_factor 列）：qfq 透明兼容，hfq 明确报错"""
        days = pd.bdate_range("2024-01-01", periods=60)
        legacy = pd.DataFrame({"open": 10.0, "close": 10.5, "volume": 1e6},
                              index=days)
        legacy.index.name = "time"
        out = market_data._apply_adjust(legacy, "000001.SZ", "qfq")
        assert out["close"].iloc[-1] == 10.5
        with pytest.raises(ValueError, match="旧版前复权缓存"):
            market_data._apply_adjust(legacy, "000001.SZ", "hfq")

    def test_merge_with_factor(self):
        raw = pd.DataFrame({"close": [10.0, 10.5, 5.25, 5.5]},
                           index=pd.bdate_range("2024-01-01", periods=4))
        back = pd.DataFrame({"close": [10.0, 10.5, 10.5, 11.0]},
                            index=raw.index)
        merged = market_data._merge_with_factor(raw, back)
        assert list(merged["adjust_factor"]) == pytest.approx([1.0, 1.0, 2.0, 2.0])
        assert list(merged.columns) == ["close", "adjust_factor"]

    def test_unknown_adjust_raises(self):
        days = pd.bdate_range("2024-01-01", periods=10)
        df = _synthetic_split_frame(days)
        with pytest.raises(ValueError, match="未知复权口径"):
            market_data._apply_adjust(df, "x", "front")
