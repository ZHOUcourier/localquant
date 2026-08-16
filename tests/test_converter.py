"""时间戳标准化测试：QMT epoch 必须按北京时间解析。"""

import pandas as pd

from backend.data.converter import normalize_timestamp


def test_epoch_ms_is_beijing_time():
    # 2024-01-02 09:30:00 Asia/Shanghai = 1704159000000 ms UTC
    idx = normalize_timestamp(pd.Index([1704159000000], dtype="int64"))
    assert idx[0] == pd.Timestamp("2024-01-02 09:30:00")
    assert idx.tz is None


def test_epoch_seconds_is_beijing_time():
    idx = normalize_timestamp(pd.Index([1704159000], dtype="int64"))
    assert idx[0] == pd.Timestamp("2024-01-02 09:30:00")


def test_datetime_keeps_naive():
    idx = pd.DatetimeIndex(["2024-01-02 09:30:00"])
    out = normalize_timestamp(idx)
    assert out.equals(idx)
    assert out.tz is None
