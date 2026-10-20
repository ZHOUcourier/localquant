"""股票池约束内核回归测试

覆盖：
- ST / 退市整理按 instrument 快照逐日 as-of，不倒灌历史
- 次新股按当日距上市日（自然日）逐日排除
- 北交所开关
- 回测 eligibility_mask：不合格标的不建仓、已持有可退出
- 静态股票列表（今天）过滤
"""

import pandas as pd
import pytest

from backend.services import reference_data
from backend.services.backtest_analysis import BacktestAnalysisService
from backend.services.universe_policy import (
    UniversePolicy,
    apply_policy_to_panels,
    build_equity_eligibility,
    filter_codes_today,
)


@pytest.fixture()
def ref_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(reference_data, "REFERENCE_DIR", tmp_path / "reference")
    (tmp_path / "reference").mkdir(parents=True, exist_ok=True)
    return tmp_path / "reference"


def _dates(n: int = 100, start: str = "2024-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _seed_instrument(ref_dir):
    snap1 = pd.DataFrame(
        [
            {"date": "2024-01-02", "code": "600000.SH", "name": "浦发银行",
             "list_date": "2010-01-01"},
            {"date": "2024-01-02", "code": "000001.SZ", "name": "平安银行",
             "list_date": "2010-01-01"},
            {"date": "2024-01-02", "code": "301001.SZ", "name": "次新测试",
             "list_date": "2023-12-01"},
            {"date": "2024-01-02", "code": "830001.BJ", "name": "北交测试",
             "list_date": "2010-01-01"},
            {"date": "2024-01-02", "code": "600002.SH", "name": "候选实业",
             "list_date": "2010-01-01"},
        ]
    )
    snap2 = pd.DataFrame(
        [
            {"date": "2024-03-01", "code": "000001.SZ", "name": "*ST平安",
             "list_date": "2010-01-01"},
            {"date": "2024-03-01", "code": "600002.SH", "name": "退市候选退",
             "list_date": "2010-01-01"},
        ]
    )
    reference_data.import_reference_snapshot("instrument", "2024-01-02", snap1)
    reference_data.import_reference_snapshot("instrument", "2024-03-01", snap2)


def test_st_and_delisting_are_point_in_time(ref_dir):
    _seed_instrument(ref_dir)
    idx = _dates()
    codes = ["600000.SH", "000001.SZ", "600002.SH"]
    result = build_equity_eligibility(idx, codes, UniversePolicy(min_list_days=0))
    # 快照前不误杀；ST 快照日起生效
    assert result.mask.loc["2024-01-05", "000001.SZ"]
    assert not result.mask.loc["2024-03-05", "000001.SZ"]
    # 退市整理仅从名称出现“退”的快照日起生效
    assert result.mask.loc["2024-01-05", "600002.SH"]
    assert not result.mask.loc["2024-03-05", "600002.SH"]
    assert result.stats["excluded_by_reason"]["st"] > 0
    assert result.stats["excluded_by_reason"]["delisting"] > 0


def test_new_stock_filter_uses_calendar_days(ref_dir):
    _seed_instrument(ref_dir)
    idx = _dates()
    codes = ["301001.SZ", "600000.SH"]
    result = build_equity_eligibility(
        idx, codes, UniversePolicy(min_list_days=730)
    )
    # 2023-12-01 上市，2024 年内都未满 730 天
    assert not result.mask["301001.SZ"].any()
    assert result.mask["600000.SH"].all()
    # 关闭后不再按上市日过滤
    off = build_equity_eligibility(
        idx, codes, UniversePolicy(exclude_new=False, min_list_days=730)
    )
    assert off.mask.all().all()


def test_bj_toggle(ref_dir):
    _seed_instrument(ref_dir)
    idx = _dates(20)
    codes = ["830001.BJ", "600000.SH"]
    on = build_equity_eligibility(idx, codes, UniversePolicy(include_bj=True))
    off = build_equity_eligibility(idx, codes, UniversePolicy(include_bj=False))
    assert on.mask["830001.BJ"].all()
    assert not off.mask["830001.BJ"].any()
    assert off.stats["excluded_by_reason"]["bj"] == len(idx)


def test_missing_metadata_warns_but_does_not_crash(ref_dir):
    idx = _dates(10)
    result = build_equity_eligibility(idx, ["600000.SH"], UniversePolicy())
    assert result.mask.all().all()
    assert any("无 instrument" in w for w in result.warnings)


def test_backtest_eligible_mask_blocks_ineligible(ref_dir):
    idx = _dates(5)
    prices = pd.DataFrame(
        {"A": [10.0] * 5, "B": [20.0] * 5}, index=idx
    )
    signals = pd.DataFrame(1.0, index=idx, columns=["A", "B"])
    eligibility = pd.DataFrame(
        {"A": [True] * 5, "B": [False] * 5}, index=idx
    )
    result = BacktestAnalysisService().run_backtest(
        signals,
        prices,
        commission_rate=0,
        slippage=0,
        stamp_tax=0,
        eligible_mask=eligibility,
    )
    assert (result["positions"]["B"].abs() < 1e-12).all()
    assert result["positions"].iloc[1]["A"] == pytest.approx(1.0)


def test_apply_policy_to_panels_filters_signals(ref_dir):
    _seed_instrument(ref_dir)
    idx = _dates(10)
    prices = pd.DataFrame(
        {"600000.SH": 10.0, "301001.SZ": 20.0}, index=idx
    )
    signals = pd.DataFrame(1.0, index=idx, columns=prices.columns)
    filtered, result = apply_policy_to_panels(
        signals, prices, UniversePolicy(min_list_days=730)
    )
    assert (filtered["301001.SZ"] == 0).all()
    assert (filtered["600000.SH"] == 1).all()
    assert result.stats["policy_hash"]


def test_filter_codes_today(ref_dir):
    today = pd.Timestamp.today().normalize()
    snap = pd.DataFrame(
        [
            {"date": str(today.date()), "code": "600000.SH", "name": "老股",
             "list_date": "2010-01-01"},
            {"date": str(today.date()), "code": "301001.SZ", "name": "次新",
             "list_date": str((today - pd.Timedelta(days=30)).date())},
            {"date": str(today.date()), "code": "000001.SZ", "name": "*ST平安",
             "list_date": "2010-01-01"},
        ]
    )
    reference_data.import_reference_snapshot(
        "instrument", str(today.date()), snap
    )
    kept, result = filter_codes_today(
        ["600000.SH", "301001.SZ", "000001.SZ"], UniversePolicy()
    )
    assert kept == ["600000.SH"]
    assert result.stats["excluded_last_date_by_reason"]["st"] == 1
    assert result.stats["excluded_last_date_by_reason"]["new"] == 1
