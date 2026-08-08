"""研究正确性修复回归测试

覆盖：
- P0-2/P0-3 回测引擎：复牌跳空收益（ffill 口径）、数据截止强制清算（退市损失入账）、
  死股不再建仓、delisting_events 明细与 assumptions
- P1-4 可交易掩码：次新股过滤改为逐日判定（不再按面板末日一刀切）
- P1-5 ST 状态：按 as-of instrument 快照逐日判定（不把"现在的 ST"倒灌历史截面）；
  涨跌停幅度随 ST 状态逐日切换（5% vs 10%）
- P0-1 退市/历史代码清单：持久化 + 批量下载并入
- P1-5 历史参考快照导入：指数成分/合约名/两融池 as-of 导入 → 逐日掩码可用
- build_return_panel：复牌日跳空收益不再被 fillna(0) 丢弃
"""

import json

import numpy as np
import pandas as pd
import pytest

from backend.services import market_data, reference_data
from backend.services.backtest_analysis import BacktestAnalysisService

svc = BacktestAnalysisService()


def _dates(n: int, start: str = "2024-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


# ── P0-3 复牌跳空收益 ─────────────────────────────────────────


def test_build_return_panel_captures_resume_gap():
    """停牌后复牌日跳空收益必须计入（原始 pct_change+fillna(0) 会整段丢失）"""
    idx = _dates(4)
    close = pd.DataFrame({"A": [100.0, np.nan, 90.0, 90.0]}, index=idx)
    r = market_data.build_return_panel(close)
    # 停牌日收益 0；复牌日 = 90/100-1 = -10%；之后 0
    assert r.iloc[0]["A"] == pytest.approx(0.0)
    assert r.iloc[1]["A"] == pytest.approx(0.0)
    assert r.iloc[2]["A"] == pytest.approx(-0.10)
    assert r.iloc[3]["A"] == pytest.approx(0.0)


def test_backtest_realizes_resume_gap():
    """回测持仓跨越停牌：复牌日跳空损失必须入账（旧行为：损失丢失）"""
    idx = _dates(4)
    prices = pd.DataFrame({"A": [100.0, np.nan, 90.0, 90.0]}, index=idx)
    signals = pd.DataFrame({"A": [1.0, 1.0, 1.0, 1.0]}, index=idx)
    tradable = pd.DataFrame(
        {"A": [True, False, True, True]}, index=idx  # day1 停牌
    )
    result = svc.run_backtest(
        signals, prices, commission_rate=0.0, slippage=0.0,
        stamp_tax=0.0, tradable_mask=tradable,
    )
    r = result["strategy_returns"]
    assert r.iloc[1] == pytest.approx(0.0)      # 停牌日冻结
    assert r.iloc[2] == pytest.approx(-0.10)    # 复牌日跳空损失入账
    assert r.iloc[3] == pytest.approx(0.0)
    assert result["equity_curve"].iloc[-1] == pytest.approx(1_000_000 * 0.9)


# ── P0-2 数据截止强制清算（退市处理）─────────────────────────


def test_backtest_forced_liquidation_at_data_end():
    """数据在面板中途截止：持仓强制清算并按 delisting_loss 计提损失，
    权重释放（旧行为：持仓冻结在末日价，退市损失完全不入账）"""
    idx = _dates(5)
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0, np.nan, np.nan]}, index=idx)
    signals = pd.DataFrame({"A": [1.0] * 5}, index=idx)

    result = svc.run_backtest(
        signals, prices, commission_rate=0.0, slippage=0.0,
        stamp_tax=0.0, delisting_loss=0.3,
    )
    r = result["strategy_returns"]
    pos = result["positions"]
    # day1/day2 正常持有收益 10%
    assert r.iloc[1] == pytest.approx(0.10)
    assert r.iloc[2] == pytest.approx(0.10)
    # day3（截止后首日）：强制清算，损失 0.3 × 权重 1.0
    assert r.iloc[3] == pytest.approx(-0.30)
    assert pos.iloc[3]["A"] == pytest.approx(0.0)
    # day4 死股信号清零，不再持有
    assert pos.iloc[4]["A"] == pytest.approx(0.0)
    assert r.iloc[4] == pytest.approx(0.0)

    # 事件明细与假设
    evts = result["delisting_events"]
    assert len(evts) == 1
    assert evts[0]["code"] == "A"
    assert evts[0]["weight"] == pytest.approx(1.0)
    assert evts[0]["loss_rate"] == pytest.approx(0.3)
    joined = "；".join(result["assumptions"])
    assert "强制清算" in joined
    assert "退市" in joined

    # 累计：1.1 × 1.1 × 0.7 - 1
    assert result["equity_curve"].iloc[-1] == pytest.approx(
        1_000_000 * 1.1 * 1.1 * 0.7
    )


def test_backtest_delisting_loss_zero_default():
    """delisting_loss=0：按末日价全额变现（保守上界），权重释放、无损失"""
    idx = _dates(4)
    prices = pd.DataFrame({"A": [100.0, 110.0, np.nan, np.nan]}, index=idx)
    signals = pd.DataFrame({"A": [1.0] * 4}, index=idx)
    result = svc.run_backtest(
        signals, prices, commission_rate=0.0, slippage=0.0, stamp_tax=0.0,
    )
    assert result["positions"].iloc[2]["A"] == pytest.approx(0.0)
    assert result["strategy_returns"].iloc[2] == pytest.approx(0.0)


def test_backtest_forced_liquidation_no_trading_cost():
    """强制清算不产生交易成本（损失由 delisting_pnl 单独入账）"""
    idx = _dates(4)
    prices = pd.DataFrame({"A": [100.0, 110.0, np.nan, np.nan]}, index=idx)
    signals = pd.DataFrame({"A": [1.0] * 4}, index=idx)
    result = svc.run_backtest(
        signals, prices, commission_rate=0.001, slippage=0.001,
        stamp_tax=0.0005, delisting_loss=0.5,
    )
    # 清算日收益 = -0.5 × 权重，不含任何佣金/滑点/印花税
    assert result["strategy_returns"].iloc[2] == pytest.approx(-0.5)
    # 交易明细不记录强制清算（非市场交易）
    assert result["trades"].iloc[2]["A"] == pytest.approx(0.0)


def test_backtest_dead_stock_never_rebought():
    """数据截止后信号仍为正：持仓保持 0（杜绝"死股复活"占权重）"""
    idx = _dates(5)
    prices = pd.DataFrame({"A": [100.0, 100.0, np.nan, np.nan, np.nan]}, index=idx)
    signals = pd.DataFrame({"A": [1.0] * 5}, index=idx)
    result = svc.run_backtest(
        signals, prices, commission_rate=0.0, slippage=0.0, stamp_tax=0.0,
    )
    pos = result["positions"]
    assert pos.iloc[1]["A"] == pytest.approx(1.0)   # 数据截止前正常持仓
    assert pos.iloc[2]["A"] == pytest.approx(0.0)   # 截止后首日清算
    assert (pos.iloc[3:]["A"] == 0.0).all()         # 永不回买
    assert result["delisting_events"][0]["date"] == str(idx[2].date())


def test_backtest_full_panel_no_liquidation():
    """数据覆盖完整区间（末日至面板末日）：不触发强制清算，无 delisting 事件"""
    idx = _dates(4)
    prices = pd.DataFrame({"A": [100.0, 110.0, 121.0, 133.1]}, index=idx)
    signals = pd.DataFrame({"A": [1.0] * 4}, index=idx)
    result = svc.run_backtest(
        signals, prices, commission_rate=0.0, slippage=0.0, stamp_tax=0.0,
    )
    assert result["delisting_events"] == []
    assert not any("强制清算" in a for a in result["assumptions"])


# ── P1-4 次新股逐日过滤 ──────────────────────────────────────


@pytest.fixture
def ref_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(reference_data, "REFERENCE_DIR", tmp_path)
    return tmp_path


def test_mask_new_stock_filtered_per_date(ref_dir):
    """次新过滤按逐日判定：上市后 20 天内排除，之后恢复可交易；
    旧实现按面板末日一刀切，上市 5 年的新股在早期截面完全未被过滤"""
    idx = _dates(28)  # 2024-01-02 ~ 2024-02-09
    close = pd.DataFrame(
        {
            "NEW.SH": [np.nan] * 10 + [20.0] * 18,  # 2024-01-15 上市
            "OLD.SZ": [50.0] * 28,
        },
        index=idx,
    )
    volume = pd.DataFrame(
        {
            "NEW.SH": [np.nan] * 10 + [1e6] * 18,
            "OLD.SZ": [1e6] * 28,
        },
        index=idx,
    )
    # instrument 快照：NEW.SH 上市日 2024-01-15
    snap = pd.DataFrame(
        [
            {"date": "2024-02-09", "code": "NEW.SH", "name": "新股测试",
             "list_date": "2024-01-15"},
            {"date": "2024-02-09", "code": "OLD.SZ", "name": "老股测试",
             "list_date": "2023-01-01"},
        ]
    )
    reference_data.import_reference_snapshot("instrument", "2024-02-09", snap)

    mask = market_data.build_cross_section_mask(
        {"close": close, "volume": volume}, min_list_days=20
    )
    # 上市后 20 天内（2024-01-15 ~ 2024-02-03）排除
    assert mask.loc["2024-01-16", "NEW.SH"] == False  # noqa: E712
    assert mask.loc["2024-02-02", "NEW.SH"] == False  # noqa: E712
    # 20 天之后恢复可交易
    assert mask.loc["2024-02-05", "NEW.SH"] == True  # noqa: E712
    # 老股全程可交易（无 NaN 污染：无上市日信息/非次新的股票不得被排除）
    assert (mask["OLD.SZ"] == True).all()  # noqa: E712
    assert mask["OLD.SZ"].notna().all()
    assert mask["NEW.SH"].notna().all()


# ── P1-5 ST 状态 as-of ───────────────────────────────────────


def test_st_status_point_in_time(ref_dir):
    """ST 状态从快照日起生效：不把"现在的 ST"倒灌到历史截面"""
    idx = _dates(60, "2024-01-02")
    snap1 = pd.DataFrame(
        [
            {"date": "2024-01-10", "code": "A.SH", "name": "AA科技",
             "list_date": "2020-01-01"},
            {"date": "2024-01-10", "code": "B.SZ", "name": "BB实业",
             "list_date": "2020-01-01"},
        ]
    )
    snap2 = pd.DataFrame(
        [
            {"date": "2024-03-11", "code": "A.SH", "name": "*ST AA",
             "list_date": "2020-01-01"},
            {"date": "2024-03-11", "code": "B.SZ", "name": "BB实业",
             "list_date": "2020-01-01"},
        ]
    )
    reference_data.import_reference_snapshot("instrument", "2024-01-10", snap1)
    reference_data.import_reference_snapshot("instrument", "2024-03-11", snap2)

    status = reference_data.build_st_status(idx, ["A.SH", "B.SZ"])
    assert status is not None
    # 快照日之前 A 不是 ST；快照日起生效
    assert status.loc["2024-03-08", "A.SH"] == False  # noqa: E712
    assert status.loc["2024-03-11", "A.SH"] == True  # noqa: E712
    assert status.loc["2024-03-12", "A.SH"] == True  # noqa: E712
    assert (status["B.SZ"] == False).all()  # noqa: E712


def test_mask_excludes_st_only_after_snapshot(ref_dir):
    """可交易掩码：A 在 ST 快照日之后被排除，之前正常参与截面"""
    idx = _dates(60, "2024-01-02")
    close = pd.DataFrame(
        {"A.SH": [100.0] * len(idx), "B.SZ": [100.0] * len(idx)}, index=idx
    )
    volume = pd.DataFrame(
        {"A.SH": [1e6] * len(idx), "B.SZ": [1e6] * len(idx)}, index=idx
    )
    snap = pd.DataFrame(
        [
            {"date": "2024-03-11", "code": "A.SH", "name": "*ST AA",
             "list_date": "2020-01-01"},
            {"date": "2024-03-11", "code": "B.SZ", "name": "BB实业",
             "list_date": "2020-01-01"},
        ]
    )
    reference_data.import_reference_snapshot("instrument", "2024-03-11", snap)

    mask = market_data.build_cross_section_mask({"close": close, "volume": volume})
    assert mask.loc["2024-01-05", "A.SH"] == True  # noqa: E712
    assert mask.loc["2024-03-12", "A.SH"] == False  # noqa: E712
    assert (mask["B.SZ"] == True).all()  # noqa: E712
    assert mask.notna().all().all()  # 无 NaN 污染（NaN 会被下游误判为不可交易）


def test_limit_prices_follow_st_status(ref_dir):
    """涨跌停幅度随 ST 状态逐日切换：快照日前 10%，之后 5%"""
    idx = _dates(20, "2024-03-01")
    close = pd.DataFrame({"A.SH": [10.0] * len(idx)}, index=idx)
    snap = pd.DataFrame(
        [{"date": "2024-03-11", "code": "A.SH", "name": "*ST AA",
          "list_date": "2020-01-01"}]
    )
    reference_data.import_reference_snapshot("instrument", "2024-03-11", snap)

    up, down = reference_data.build_limit_prices(close)
    # 2024-03-08（快照日前）→ 昨收 ×1.10
    assert up.loc["2024-03-08", "A.SH"] == pytest.approx(10.0 * 1.10)
    # 2024-03-11（快照日生效后）→ 昨收 ×1.05
    assert up.loc["2024-03-11", "A.SH"] == pytest.approx(10.0 * 1.05)


# ── P0-1 退市/历史代码清单 ───────────────────────────────────


def test_delisted_codes_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "DELISTED_FILE", tmp_path / "delisted.json")
    assert market_data.load_delisted_codes() == []
    saved = market_data.save_delisted_codes(
        ["600005.SH", " 000013.SZ ", "600005.SH"]
    )
    assert saved == ["000013.SZ", "600005.SH"]  # 去重 + 归一化
    assert market_data.load_delisted_codes() == ["000013.SZ", "600005.SH"]


def test_merge_delisted_codes(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "DELISTED_FILE", tmp_path / "delisted.json")
    market_data.save_delisted_codes(["600005.SH"])
    merged = market_data.merge_delisted_codes(["000001.SZ", "600005.SH"])
    assert merged == ["000001.SZ", "600005.SH"]  # 清单内已有则去重
    merged2 = market_data.merge_delisted_codes(["000001.SZ"])
    assert merged2 == ["000001.SZ", "600005.SH"]  # 自动并入


def test_delisted_list_survives_reload(tmp_path, monkeypatch):
    """持久化到 JSON：重启（重新 import）后清单仍在"""
    monkeypatch.setattr(market_data, "DELISTED_FILE", tmp_path / "delisted.json")
    market_data.save_delisted_codes(["600005.SH", "300372.SZ"])
    data = json.loads((tmp_path / "delisted.json").read_text("utf-8"))
    assert set(data["codes"]) == {"600005.SH", "300372.SZ"}
    assert "updated_at" in data


# ── 历史参考快照导入 → as-of 链路 ────────────────────────────


def test_import_constituents_enables_history(ref_dir):
    """导入 2015 年沪深300 成分快照后，历史区间可按 as-of 重建成分（免幸存者偏差）"""
    df = pd.DataFrame(
        {
            "index_name": ["沪深300"] * 2,
            "code": ["600000.SH", "000001.SZ"],
        }
    )
    rows = reference_data.import_reference_snapshot("constituents", "2015-01-05", df)
    assert rows == 2
    assert "沪深300" in reference_data.list_snapshot_indices()
    members = reference_data.load_index_membership("沪深300")
    assert members is not None
    assert members.loc["2015-01-05", "600000.SH"] == True  # noqa: E712
    assert members.loc["2015-01-05", "000001.SZ"] == True  # noqa: E712


def test_import_instrument_st_history(ref_dir):
    """导入历史名称快照（曾 ST）：逐日 ST 状态可回溯"""
    df = pd.DataFrame(
        [{"code": "C.SZ", "name": "ST 昌九", "list_date": "2010-01-01"}]
    )
    reference_data.import_reference_snapshot("instrument", "2015-06-01", df)
    status = reference_data.build_st_status(
        pd.bdate_range("2015-06-01", periods=5), ["C.SZ"]
    )
    assert status.loc["2015-06-01", "C.SZ"] == True  # noqa: E712


def test_import_margin_pool_as_of(ref_dir):
    """导入历史两融池快照 → 逐日可融券掩码（as-of，早于快照为 NaN）"""
    df = pd.DataFrame({"code": ["600000.SH", "000001.SZ"]})
    reference_data.import_reference_snapshot("margin", "2024-01-10", df)
    idx = pd.bdate_range("2024-01-01", periods=20)
    mask = reference_data.load_universe_pool_mask("margin", idx)
    assert mask is not None
    assert pd.isna(mask.loc["2024-01-02", "600000.SH"])  # 早于首次快照 → NaN
    assert mask.loc["2024-01-10", "600000.SH"] == True  # noqa: E712
    assert mask.loc["2024-01-10", "000001.SZ"] == True  # noqa: E712
    # 池外代码：reindex 后为 NaN，调用方按需 fillna(False)（见 portfolio_backtest）
    outer = mask.reindex(columns=["999999.SH"])
    assert pd.isna(outer.loc["2024-01-10", "999999.SH"])


def test_import_reference_rejects_unknown_kind(ref_dir):
    with pytest.raises(ValueError, match="未知快照类型"):
        reference_data.import_reference_snapshot(
            "nonsense", "2024-01-01", pd.DataFrame({"code": ["A"]})
        )


# ── Bug A: _rolling_ic_weights 前视（IC[T] 需要 T+1 收益）────────────────


def test_rolling_ic_weights_no_lookahead():
    """T 日权重不得使用 IC[T]（其依赖 T+1 收益）：
    改动末日收益，任何日期的权重都必须不变"""
    from backend.services.factor_research import factor_research

    rng = np.random.default_rng(42)
    idx = _dates(60)
    n = 15
    ret = pd.DataFrame(
        rng.normal(0.001, 0.02, size=(60, n)), index=idx,
        columns=[f"S{i}" for i in range(n)],
    )
    fac = pd.DataFrame(
        rng.normal(0, 1, size=(60, n)), index=idx, columns=ret.columns
    )
    factors = {"A": fac, "B": -fac}
    w1, _ = factor_research._rolling_ic_weights(
        factors, ret, ic_window=10, min_window=3
    )
    ret2 = ret.copy()
    ret2.iloc[-1] = ret2.iloc[-1] * -10  # 末日收益剧烈变化
    w2, _ = factor_research._rolling_ic_weights(
        factors, ret2, ic_window=10, min_window=3
    )
    for name in w1:
        joined = w1[name].reindex(w2[name].index)
        assert (joined == w2[name]).all(), (
            f"因子 {name} 的权重依赖了末日收益 — 存在 1 日前视"
        )
    # 权重仍为 |滚动IC| 归一 + 符号对齐
    assert (w1["A"] != 0).any() or (w1["B"] != 0).any()


def test_rolling_ic_weights_excludes_same_day_ic():
    """权重 = IC 序列 shift(1) 后的滚动均值（T 日权重只用 ≤ T-1 的 IC）"""
    from backend.services.factor_research import factor_research

    idx = _dates(30)
    n = 6
    rng = np.random.default_rng(7)
    ret = pd.DataFrame(
        rng.normal(0.001, 0.02, size=(30, n)), index=idx,
        columns=[f"S{i}" for i in range(n)],
    )
    fac = pd.DataFrame(
        rng.normal(0, 1, size=(30, n)), index=idx, columns=ret.columns
    )
    # 手工复算：T 日 IC = corr(rank(fac[T]), rank(ret[T+1]))
    def _ic_at(t):
        f = fac.iloc[t].dropna()
        r = ret.iloc[t + 1].dropna()
        common = f.index.intersection(r.index)
        return f[common].rank().corr(r[common].rank())

    ics = pd.Series(
        {idx[t]: _ic_at(t) for t in range(29)}, name="ic"
    ).sort_index()
    expected = ics.shift(1).rolling(10, min_periods=3).mean()

    w, ic = factor_research._rolling_ic_weights(
        {"F": fac}, ret, ic_window=10, min_window=3
    )
    got = w["F"].abs()  # 单因子：权重 = |IC|/|IC| × sign
    joined = got.reindex(expected.index).dropna()
    assert (joined.abs() == expected.reindex(joined.index).abs()).all()
    # 首窗（shift 后不足 min_window）为 NaN，不建仓
    assert got.iloc[:3].isna().all()

# ── Bug B: 事件研究窗口截断 ─────────────────────────────────


def test_event_study_truncated_window_no_error():
    """事件位于面板边界（窗口被截断）时不再 IndexError，CAR 按实际窗口对齐"""
    from backend.services import event_study as es

    idx = _dates(20)
    n = 6
    ret = pd.DataFrame(
        np.zeros((20, n)), index=idx, columns=[f"S{i}" for i in range(n)]
    )
    # 事件在面板第一天：window_before 全部缺失（旧实现会越界）
    ev = pd.DataFrame(
        {"date": [idx[0]] * n, "code": [f"S{i}" for i in range(n)]}
    )
    res = es.event_study_analysis(ret, ev, window_before=5, window_after=5)
    assert res["ok"] is True
    assert "0" in res["car"]  # 事件日 CAR 存在
    assert res["car"]["5"]["mean"] == pytest.approx(0.0)  # 全零收益 → CAR=0

    # 事件在面板最后一天：window_after 全部缺失
    ev2 = pd.DataFrame(
        {"date": [idx[-1]] * n, "code": [f"S{i}" for i in range(n)]}
    )
    res2 = es.event_study_analysis(ret, ev2, window_before=5, window_after=5)
    assert res2["ok"] is True
    assert res2["car"]["0"]["mean"] == pytest.approx(0.0)


def test_event_study_car_alignment():
    """截断窗口下 CAR 逐日累计仍按相对日正确对齐（非错位拼接）"""
    from backend.services import event_study as es

    idx = _dates(20)
    n = 6
    ret = pd.DataFrame(
        np.zeros((20, n)), index=idx, columns=[f"S{i}" for i in range(n)]
    )
    ret["S0"] = 0.01  # S0 每天 +1%
    ev = pd.DataFrame(
        {"date": [idx[1]] * n, "code": [f"S{i}" for i in range(n)]}
    )  # 事件在第二天，前后窗口都部分存在
    # 用外部基准（全 0）避免「市场均值含事件股自身」的抵消效应
    market = pd.Series(0.0, index=idx)
    res = es.event_study_analysis(
        ret, ev, window_before=3, window_after=5, market_returns=market
    )
    assert res["ok"] is True
    # 事件在 idx[1]（i0=1）：相对日 -3/-2 越界，-1 起可用（共 7 天）
    assert "-1" in res["car"] and "-2" not in res["car"]
    # S0 全程 +1%/日 → car[d] = (d+2)×(1%/6)（d=-1..5，逐日严格对齐）
    assert res["car"]["-1"]["mean"] == pytest.approx(1 * 0.01 / n, abs=1e-6)
    assert res["car"]["0"]["mean"] == pytest.approx(2 * 0.01 / n, abs=1e-6)
    assert res["car"]["5"]["mean"] == pytest.approx(7 * 0.01 / n, abs=1e-6)


# ── Bug C: 工作流节点缓存随数据失效 ──────────────────────────


def test_node_cache_key_tracks_data_version(tmp_path, monkeypatch):
    """重新下载/更新数据后，节点缓存键必须变化（避免旧数据结果被当作新结果）"""
    from backend.config import settings
    from backend.engine import runner

    monkeypatch.setattr(settings, "cache_dir", tmp_path)
    # 重置版本缓存，绕过 TTL
    runner._data_version_cache = {"ts": 0.0, "version": ""}
    k1 = runner._compute_cache_key("因子构建", {"formula": "MA(close,5)"})

    (tmp_path / "1d").mkdir()
    (tmp_path / "1d" / "000001_SZ.parquet").write_bytes(b"x")
    runner._data_version_cache = {"ts": 0.0, "version": ""}
    k2 = runner._compute_cache_key("因子构建", {"formula": "MA(close,5)"})

    assert k1 != k2  # 数据出现 → 缓存键变化

    runner._data_version_cache = {"ts": 0.0, "version": ""}
    k3 = runner._compute_cache_key("因子构建", {"formula": "MA(close,5)"})
    assert k2 == k3  # 数据未变 → 缓存键稳定（可命中）

    # 修改数据文件（mtime 变化）→ 缓存键再变
    import os
    import time as _time

    (tmp_path / "1d" / "000001_SZ.parquet").write_bytes(b"y")
    os.utime(tmp_path / "1d" / "000001_SZ.parquet", (1, 1))
    runner._data_version_cache = {"ts": 0.0, "version": ""}
    k4 = runner._compute_cache_key("因子构建", {"formula": "MA(close,5)"})
    assert k4 != k3


# ── INDUSTRY_NEUTRALIZE 命名空间隔离（并发扫描/工作流不互相污染）──────────


def test_industry_neutralize_namespace_isolation():
    """两个命名空间用不同行业映射时互不污染（模块级全局竞争回归测试）"""
    import pandas as pd

    from backend.services.factor_operators import build_operator_namespace

    idx = pd.bdate_range("2024-01-02", periods=5)
    close = pd.DataFrame(
        {"A.SH": [10.0] * 5, "B.SH": [20.0] * 5, "C.SZ": [30.0] * 5}, index=idx
    )
    panels = {"close": close, "volume": None, "amount": None}
    f = pd.DataFrame(
        {"A.SH": [1.0, 2.0, 3.0, 4.0, 5.0],
         "B.SH": [10.0, 11.0, 12.0, 13.0, 14.0],
         "C.SZ": [100.0, 101.0, 102.0, 103.0, 104.0]},
        index=idx,
    )
    ns1 = build_operator_namespace(panels, industry_map={"A.SH": "X", "B.SH": "X", "C.SZ": "Y"})
    ns2 = build_operator_namespace(panels, industry_map={"A.SH": "P", "B.SH": "Q", "C.SZ": "R"})
    r1 = ns1["INDUSTRY_NEUTRALIZE"](f)
    r2 = ns2["INDUSTRY_NEUTRALIZE"](f)
    # 分组不同 → 中性化结果必须不同（若共享模块全局，两者会相同或互相污染）
    assert not r1.equals(r2)
    # 行业组内去均值：A、B 同组 → 组内去均值后 A = -(B - mean)
    mean_ab = f[["A.SH", "B.SH"]].mean(axis=1)
    assert r1["A.SH"].equals(f["A.SH"] - mean_ab)
    # 无行业数据时显式报错（不回退到共享全局）
    ns3 = build_operator_namespace(panels, industry_map=None)
    import pytest as _p

    with _p.raises(ValueError, match="行业分类"):
        ns3["INDUSTRY_NEUTRALIZE"](f)
