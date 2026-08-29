"""P0-5 参考数据 point-in-time 测试

验证：
- load_industry_panel 逐日 as-of（多快照时逐日取不晚于当日的分类；早于首快照为 NaN）
- load_industry_map(as_of) as-of 语义（早于所有快照返回空，不回退未来）
- load_membership_mask 逐日 as-of 成分掩码
- INDUSTRY_NEUTRALIZE 优先用逐日面板做 PIT 中性化
"""

import pandas as pd
import pytest

from backend.services import reference_data
from backend.services.factor_operators import INDUSTRY_NEUTRALIZE


@pytest.fixture
def ref_dir(tmp_path, monkeypatch):
    """把 REFERENCE_DIR 指到临时目录，构造两期行业快照与一期指数成分快照"""
    monkeypatch.setattr(reference_data, "REFERENCE_DIR", tmp_path)

    # 行业快照：code A 在 2023-01-02 属"银行"，2023-06-01 改为"科技"；B 一直"银行"
    industry = pd.DataFrame(
        [
            {"date": "2023-01-02", "code": "A", "industry": "银行"},
            {"date": "2023-01-02", "code": "B", "industry": "银行"},
            {"date": "2023-06-01", "code": "A", "industry": "科技"},
        ]
    )
    industry.to_parquet(tmp_path / "industry.parquet", index=False)

    # 指数成分快照：2023-01-02 含 A；2023-06-01 加入 B
    cons = pd.DataFrame(
        [
            {"date": "2023-01-02", "index_name": "000300.SH", "code": "A"},
            {"date": "2023-06-01", "index_name": "000300.SH", "code": "A"},
            {"date": "2023-06-01", "index_name": "000300.SH", "code": "B"},
        ]
    )
    cons.to_parquet(tmp_path / "index_constituents.parquet", index=False)
    return tmp_path


def test_industry_panel_as_of(ref_dir):
    dates = ["2023-02-01", "2023-07-01"]
    panel = reference_data.load_industry_panel(dates, codes=["A", "B"])
    assert panel is not None
    # 2023-02：A 尚未改行业 → 银行；2023-07：A 已改为科技
    assert panel.loc["2023-02-01", "A"] == "银行"
    assert panel.loc["2023-07-01", "A"] == "科技"
    assert panel.loc["2023-02-01", "B"] == "银行"


def test_industry_panel_before_first_snapshot_is_nan(ref_dir):
    panel = reference_data.load_industry_panel(["2022-01-01"], codes=["A"])
    assert panel is not None
    assert pd.isna(panel.loc["2022-01-01", "A"])


def test_industry_map_as_of_no_future(ref_dir):
    # as_of 早于所有快照 → 空（不回退未来）
    assert reference_data.load_industry_map(as_of="2022-01-01") == {}
    # as_of 在首期与二期之间 → 只有首期分类
    m = reference_data.load_industry_map(as_of="2023-03-01")
    assert m.get("A") == "银行"
    # as_of 在二期之后 → A 改为科技
    m2 = reference_data.load_industry_map(as_of="2023-07-01")
    assert m2.get("A") == "科技"


def test_membership_mask_as_of(ref_dir):
    mask = reference_data.load_membership_mask("000300.SH", ["2023-02-01", "2023-07-01"])
    assert mask is not None
    # A 两期都在；B 仅 2023-06 后在
    assert bool(mask.loc["2023-02-01", "A"]) is True
    assert bool(mask.loc["2023-02-01", "B"]) is False
    assert bool(mask.loc["2023-07-01", "B"]) is True


def test_industry_neutralize_uses_pit_panel(ref_dir):
    """两日因子，A 行业在 2023-06 变更 → 逐日中性化应按当日行业去均值"""
    dates = pd.DatetimeIndex(["2023-02-01", "2023-07-01"])
    # A、B 因子值：两日相同，若同行业则去均值后互为相反数
    factor = pd.DataFrame({"A": [1.0, 1.0], "B": [3.0, 3.0]}, index=dates)
    panel = reference_data.load_industry_panel(dates, codes=["A", "B"])

    import backend.services.factor_operators as ops

    ops.__dict__.pop("_ACTIVE_INDUSTRY_MAP", None)
    ops.__dict__.pop("_ACTIVE_INDUSTRY_PANEL", None)
    out = INDUSTRY_NEUTRALIZE(factor, industry_panel=panel)

    # 2023-02：A、B 同属银行 → 去均值后 A=-1, B=+1
    assert out.loc["2023-02-01", "A"] == pytest.approx(-1.0)
    assert out.loc["2023-02-01", "B"] == pytest.approx(1.0)
    # 2023-07：A 属科技、B 属银行 → 各自单票行业内去均值 → 均为 0
    assert out.loc["2023-07-01", "A"] == pytest.approx(0.0)
    assert out.loc["2023-07-01", "B"] == pytest.approx(0.0)
