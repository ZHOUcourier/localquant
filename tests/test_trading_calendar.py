"""P0-7 交易日历持久化与诚实标注测试

验证：
- save/load_trading_calendar 持久化往返
- QMT 未连接时 _trading_calendar 回退到本地持久化日历（离线可用）
- 无日历时 data_freshness 标 calendar_unverified（不再静默工作日近似）
"""

from datetime import date

import pytest

from backend.services import market_data, reference_data


@pytest.fixture
def ref_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(reference_data, "REFERENCE_DIR", tmp_path)
    return tmp_path


def test_trading_calendar_roundtrip(ref_dir):
    dates = [date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4)]
    n = reference_data.save_trading_calendar(dates)
    assert n == 3
    loaded = reference_data.load_trading_calendar()
    assert loaded == sorted(dates)


def test_trading_calendar_load_none_when_absent(ref_dir):
    assert reference_data.load_trading_calendar() is None


def test_trading_calendar_offline_fallback(ref_dir, monkeypatch):
    """QMT 未连接时，_trading_calendar 读本地持久化日历（离线可用）"""
    dates = [date(2023, 1, 2), date(2023, 1, 3)]
    reference_data.save_trading_calendar(dates)
    # 强制 QMT 未连接 + 清空内存缓存
    monkeypatch.setattr(market_data._qmt, "_connected", False)
    market_data._trade_cal.update({"ts": 0.0, "dates": None, "source": None})
    cal = market_data._trading_calendar()
    assert cal == sorted(dates)
    assert market_data.trading_calendar_source() == "persisted"


def test_freshness_calendar_unverified_without_calendar(ref_dir, monkeypatch, tmp_path):
    """无日历时 data_freshness 标 calendar_unverified=True"""
    # 无持久化日历 + QMT 未连接
    monkeypatch.setattr(market_data._qmt, "_connected", False)
    market_data._trade_cal.update({"ts": 0.0, "dates": None, "source": None})
    assert market_data.trading_calendar_source() == "weekday_approx"
    # data_freshness 空缓存也应返回 calendar_unverified=True
    monkeypatch.setattr(market_data.settings, "cache_dir", tmp_path)
    res = market_data.data_freshness("1d")
    assert res["calendar_unverified"] is True
    assert res["calendar"] == "weekday_approx"
