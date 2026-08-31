"""P2-H 回归：数据时效检查区分「数据滞后」与「单股断档（疑似停牌/退市）」。

单股久缺数（如退市股末日停在数月前）不得与正常滞后股混报，
更不得把整体时效 status 拉成 stale。
"""

import datetime as dt

import pandas as pd
import pytest

from backend.services import market_data


class _FakeCache:
    def __init__(self, latest: dict[str, str]):
        self._latest = latest

    def get_latest_timestamp(self, code: str, period: str):
        v = self._latest.get(code)
        return pd.Timestamp(v) if v else None


@pytest.fixture()
def freshness_env(monkeypatch):
    """固定交易日历（近 60 个工作日，末日为今天）与三只标的"""
    today = dt.datetime.now().astimezone().date()
    calendar = [d.date() for d in pd.bdate_range(end=today, periods=60)]

    def install(latest: dict[str, str], use_calendar: bool = True):
        monkeypatch.setattr(
            market_data, "list_cached_codes", lambda period="1d": list(latest)
        )
        monkeypatch.setattr(market_data, "_cache", _FakeCache(latest))
        monkeypatch.setattr(
            market_data, "_trading_calendar", lambda: calendar if use_calendar else None
        )
        monkeypatch.setattr(
            market_data, "trading_calendar_source", lambda: "test"
        )

    return install, calendar


def test_single_stock_gap_not_mixed_with_stale(freshness_env):
    install, calendar = freshness_env
    install(
        {
            "FRESH.SH": str(calendar[-1]),  # 滞后 0
            "LAG.SH": str(calendar[-8]),  # 滞后 7：数据滞后
            "DELIST.SZ": str(calendar[-31]),  # 滞后 30：单股断档
        }
    )
    result = market_data.data_freshness()

    assert result["stale_count"] == 1
    assert result["stale"][0]["code"] == "LAG.SH"
    assert result["stale"][0]["stale_trade_days"] == 7

    assert result["gap_count"] == 1
    assert result["gapped"][0]["code"] == "DELIST.SZ"
    assert result["gapped"][0]["stale_trade_days"] == 30
    assert "单股断档" in result["gapped"][0]["reason"]
    assert result["gap_threshold_trade_days"] == 20


def test_gap_only_does_not_poison_status(freshness_env):
    """只有单股断档、无数据滞后时，整体时效仍应为 ok（Dashboard stale_count 不受污染）"""
    install, calendar = freshness_env
    install(
        {
            "FRESH.SH": str(calendar[-1]),
            "DELIST.SZ": str(calendar[-31]),
        }
    )
    result = market_data.data_freshness()

    assert result["stale_count"] == 0
    assert result["status"] == "ok"
    assert result["gap_count"] == 1


def test_gap_classification_weekday_fallback(freshness_env):
    """无交易日历的工作日近似下同样区分断档"""
    install, _ = freshness_env
    today = dt.datetime.now().astimezone().date()
    long_ago = today - dt.timedelta(days=60)  # 约 42 个工作日
    install({"DELIST.SZ": str(long_ago)}, use_calendar=False)
    result = market_data.data_freshness()

    assert result["stale_count"] == 0
    assert result["gap_count"] == 1
    assert result["status"] == "ok"
