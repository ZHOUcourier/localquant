"""公式方言规范化与可执行性测试（P0-2）

覆盖：
- 方言确定性翻译（三元/单=/&&||/^/MATLAB 点运算/损坏冒号/隐式乘法/括号配平）
- 语义等价（三元→IF 与 np.where 一致；^ 是幂不是异或）
- SEQUENCE 坡道回归已知答案、Alpha191 兼容变量（ret/vol/CAP/CLOSE5/hd/ld/tr/dtm/dbm）
- 真实语料黄金测试：本地库全部预置因子公式规范化后可解析（显式清单除外）
- 静态分类与重算门控的诚实错误
"""

import ast
import asyncio
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend import database
from backend.services.formula_normalizer import normalize_formula
from backend.services.factor_operators import (
    REGBETA,
    SEQUENCE,
    build_operator_namespace,
    eval_factor_formula,
)
from backend.services.factor_research import classify_formula_status

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "localquant.db"

# 源文本损坏、无法确定性修复的因子（显式清单，新增必须说明理由）；
# 原登记的 alpha191_023 已按国泰君安公开定义修复并验证可解析，清单清空。
KNOWN_UNSUPPORTED: set[str] = set()


def _parses(s: str) -> bool:
    try:
        ast.parse(s)
        return True
    except SyntaxError:
        return False


def _toy_ns():
    idx = pd.bdate_range("2024-01-02", periods=10)
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        rng.uniform(90, 110, (10, 3)).cumsum(axis=0) + 100,
        index=idx,
        columns=list("ABC"),
    )
    panels = {
        "close": close,
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "volume": close * 100,
        "amount": close * close * 100,
    }
    return build_operator_namespace(panels), panels


# ── 方言确定性翻译 ─────────────────────────────────────────


def test_ternary_to_if():
    out = normalize_formula("sum((close>delay(close,1)?volume:0),20)")
    assert _parses(out)
    assert "IF(close>delay(close,1),volume,0)" in out


def test_nested_ternary_with_single_eq():
    src = (
        "(close<delay(close,5)?(close-delay(close,5))/delay(close,5):"
        "(close=delay(close,5)?0:(close-delay(close,5))/close))"
    )
    out = normalize_formula(src)
    assert _parses(out)
    assert out.count("IF(") == 2
    assert "?" not in out
    assert "close==delay(close,5)" in out


def test_power_caret():
    out = normalize_formula("(((high * low)^0.5) -vwap)")
    assert _parses(out)
    assert "**" in out and "^" not in out


def test_matlab_dot_ops():
    out = normalize_formula("sum(((close-low)-(high-close))./(high-low).*volume,6)")
    assert _parses(out)
    assert "./" not in out and ".*" not in out


def test_logical_and_parenthesizes_bare_comparisons():
    out = normalize_formula("sum((ld>0 & ld>hd)?ld:0,14)")
    assert _parses(out)
    assert "(ld>0) & (ld>hd)" in out


def test_logical_or_keeps_wrapped_operands():
    out = normalize_formula("((a < 0.05) || (b > 0.05)) ? 1 : 0")
    assert _parses(out)
    collapsed = re.sub(r"\s+", "", out)
    assert "((a<0.05)|(b>0.05))" in collapsed


def test_broken_colon_inside_call():
    assert normalize_formula("std(close:20)") == "std(close,20)"


def test_implicit_multiplication():
    out = normalize_formula("(20-1)*(20-2)(sum(close,5))")
    assert _parses(out)
    assert "(20-2)*(sum(close,5))" in out


def test_unbalanced_extra_close():
    src = (
        "MAX(TS_RANK(DECAY_LINEAR(CORRELATION(RANK(VWAP), RANK(VOLUME), 4), 4), 8), "
        "TS_RANK(DECAY_LINEAR(TS_ARGMAX(CORRELATION(TS_RANK(CLOSE, 7), "
        "TS_RANK(ADV(60), 4), 4), 13), 14), 13)) * -1)"
    )
    assert _parses(normalize_formula(src))


def test_clean_formulas_untouched():
    clean = [
        "RANK(CLOSE / DELAY(CLOSE, 5) - 1)",
        "regbeta(close,sequence,20)",
        "sma(vol*((close-low)-(high-close))/(high-low),11,2)",
        "RANK(ID_SUM(ID_SLICE(m_volume, '14:30', '15:00')) / ID_SUM(m_volume))",
    ]
    for f in clean:
        assert normalize_formula(f) == f, f"合法公式被意外改写: {f}"


def test_normalization_idempotent_on_dialect_corpus():
    corpus = [
        "sum((close>delay(close,1)?volume:0),20)",
        "(ld>0 & ld>hd)?ld:0",
        "((a < 0.05) || (b > 0.05)) ? 1 : 0",
        "(close=delay(close,1)?0:1)",
        "(((high * low)^0.5) -vwap)",
        "sum(((close-low)-(high-close))./(high-low).*volume,6)",
    ]
    for f in corpus:
        once = normalize_formula(f)
        assert normalize_formula(once) == once, f"幂等失败: {f}"


# ── 语义等价与已知答案 ─────────────────────────────────────


def test_ternary_semantics_matches_np_where():
    ns, panels = _toy_ns()
    out = eval_factor_formula("(close>delay(close,1)?volume:0)", ns)
    cond = panels["close"] > panels["close"].shift(1)
    expected = panels["volume"].where(cond, 0.0)
    pd.testing.assert_frame_equal(out.fillna(0.0), expected.fillna(0.0))


def test_caret_is_power_not_xor():
    ns, _ = _toy_ns()
    assert float(eval_factor_formula("2^3", ns)) == pytest.approx(8.0)


def test_regbeta_sequence_recovers_slope():
    """a = 2t+1 对时间轴 1..10 滚动回归，斜率应精确恢复 2"""
    idx = pd.bdate_range("2024-01-02", periods=30)
    a = pd.DataFrame({"A": [2.0 * i + 1 for i in range(30)]}, index=idx)
    beta = REGBETA(a, SEQUENCE(10))
    assert float(beta.iloc[-1]["A"]) == pytest.approx(2.0)


def test_regbeta_three_arg_bare_sequence_form():
    """alpha191_116 形态：regbeta(close, sequence, 20)"""
    ns, panels = _toy_ns()
    out = eval_factor_formula("regbeta(close, sequence, 6)", ns)
    assert out.shape == panels["close"].shape
    assert np.isfinite(out.to_numpy()).any()


def test_namespace_aliases_and_alpha191_internals():
    ns, panels = _toy_ns()
    for k in ("ret", "vol", "CAP", "CLOSE5", "OPEN5", "hd", "ld", "tr",
              "dtm", "dbm", "sequence", "SEQUENCE"):
        assert k in ns, f"命名空间缺少 {k}"
    pd.testing.assert_frame_equal(ns["CLOSE5"], panels["close"].shift(5))
    pd.testing.assert_frame_equal(ns["vol"], panels["volume"])


def test_real_dialect_formulas_evaluate():
    """修复前必挂的真实公式（三元/^/sequence/& 逻辑）端到端可求值"""
    ns, panels = _toy_ns()
    formulas = [
        "(((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)",
        "(((high * low)^0.5) -vwap)",
        "regbeta(mean(close,6),sequence(6))",
        "mean(abs(sum((ld>0 & ld>hd)?ld:0,14)*100/sum(tr,14)"
        "-sum((hd>0 &hd>ld)?hd:0,14)*100/sum(tr,14))/(sum(tr,14)),6)",
    ]
    for f in formulas:
        out = eval_factor_formula(f, ns)
        assert isinstance(out, pd.DataFrame)
        assert out.shape == panels["close"].shape


# ── Alpha101 方言：ADV(n) 单参与裸 RETURNS ─────────────────


def test_adv_single_arg_rewritten_to_volume_form():
    assert normalize_formula("ADV(20)") == "ADV(volume,20)"
    out = normalize_formula("rank(-1 * delta(close, 1) / ADV(60))")
    assert "ADV(volume,60)" in out and _parses(out)
    # 大小写不敏感
    assert normalize_formula("adv(5)") == "ADV(volume,5)"


def test_adv_two_arg_and_panel_aliases_untouched():
    assert normalize_formula("ADV(volume, 20)") == "ADV(volume, 20)"
    assert normalize_formula("adv20 / close") == "adv20 / close"
    assert normalize_formula("ADV20 / CLOSE") == "ADV20 / CLOSE"


def test_bare_returns_is_panel_variable():
    assert normalize_formula("RETURNS") == "ret"
    out = normalize_formula("rank(-1 * RETURNS * volume)")
    assert "ret" in out and "RETURNS" not in out and _parses(out)
    assert normalize_formula("std(returns, 20)") == "std(ret, 20)"


def test_returns_call_form_untouched():
    # RETURNS(x, n) 是函数调用，不得被改写成面板变量
    assert normalize_formula("RETURNS(close, 5)") == "RETURNS(close, 5)"
    assert normalize_formula("std(RETURNS(close,1),20)") == "std(RETURNS(close,1),20)"
    # RETURNS_ 面板别名不是裸 RETURNS
    assert normalize_formula("RETURNS_ + 1") == "RETURNS_ + 1"


def test_adv_returns_rewrites_inside_strings_untouched():
    out = normalize_formula("ID_SLICE(m_volume, 'ADV(20)', 'RETURNS')")
    assert "'ADV(20)'" in out and "'RETURNS'" in out


# ── 真实语料黄金测试 ───────────────────────────────────────


@pytest.mark.skipif(not DB_PATH.exists(), reason="本地数据库不存在")
def test_golden_corpus_all_preset_formulas():
    """本地库全部预置因子公式：规范化后可解析（显式清单除外），合法公式零改写"""
    markers = ["公式是：", "计算公式：", "公式：", "公式为："]

    def extract(desc):
        for m in markers:
            if desc and m in desc:
                return desc.split(m, 1)[1].strip()
        return ""

    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT factor_code, description FROM preset_factors"
        ).fetchall()
    finally:
        db.close()

    still_broken, rewritten_valid = [], []
    n_formulas = 0
    for code, desc in rows:
        f = extract(desc)
        if not f:
            continue
        n_formulas += 1
        if _parses(f):
            if normalize_formula(f) != f:
                # 合法公式只允许 ^→** 这类语义修正，必须仍可解析
                assert _parses(normalize_formula(f)), f"合法公式被破坏: {code}"
                rewritten_valid.append(code)
            continue
        if not _parses(normalize_formula(f)):
            still_broken.append(code)

    assert n_formulas >= 270, f"语料异常：仅 {n_formulas} 个带公式因子"
    assert set(still_broken) == KNOWN_UNSUPPORTED, (
        f"规范化后仍不可解析的因子超出已知清单: {still_broken}"
    )
    # 方言修正应真实发生（33 个语法错误 + 9 个 ^ 异或）
    assert len(rewritten_valid) >= 10


# ── 静态分类与诚实错误 ─────────────────────────────────────


def test_classify_status_categories():
    assert classify_formula_status("没有公式标记的描述")[0] == "missing_formula"
    assert classify_formula_status("公式是：RANK(CLOSE / DELAY(CLOSE, 5) - 1)")[0] == "executable"
    assert classify_formula_status("公式是：rank(close,,)")[0] == "syntax_error"
    status, detail = classify_formula_status("公式是：RANK(TOTALLY_UNKNOWN_NAME(close))")
    assert status == "unsupported"
    assert "TOTALLY_UNKNOWN_NAME" in detail
    assert classify_formula_status("公式是：RANK(fund_pe)")[0] == "needs_fundamental"


def test_classify_dialect_formula_is_executable():
    """修复前被判'语法错误'的方言公式，规范化后应分类为可执行"""
    assert classify_formula_status(
        "公式是：(((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)"
    )[0] == "executable"
    assert classify_formula_status(
        "公式是：regbeta(mean(close,6),sequence(6))"
    )[0] == "executable"


def test_eval_empty_formula_reports_missing_code():
    from backend.services.factor_research import factor_research

    res = factor_research.eval_formula_on_local("")
    assert res["ok"] is False
    assert res["code"] == "missing_formula"


# ── 重算门控（临时数据库）──────────────────────────────────


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())
    return tmp_path / "test.db"


def test_recalc_gate_honest_for_unexecutable(tmp_db):
    """不可执行因子的重算：如实返回分类原因，不落历史快照、不谎报数据不足"""
    from backend.services.factor_research import factor_research

    async def _run():
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO preset_factors (factor_code, factor_name, description) "
                "VALUES (?, ?, ?)",
                ("broken_x", "损坏因子", "公式是：rank(close,,)"),
            )
            await db.commit()
            cur = await db.execute(
                "SELECT id FROM preset_factors WHERE factor_code = 'broken_x'"
            )
            fid = (await cur.fetchone())["id"]
        finally:
            await db.close()

        result = await factor_research.recalculate_preset_factor(fid)

        db = await database.get_db()
        try:
            # 门控提前返回时不建历史表；表不存在本身即说明未落快照
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='preset_factor_ic_history'"
            )
            if await cur.fetchone():
                cur = await db.execute(
                    "SELECT COUNT(*) c FROM preset_factor_ic_history WHERE factor_id = ?",
                    (fid,),
                )
                history_rows = (await cur.fetchone())["c"]
            else:
                history_rows = 0
            cur = await db.execute(
                "SELECT formula_status FROM preset_factors WHERE id = ?", (fid,)
            )
            status = (await cur.fetchone())["formula_status"]
        finally:
            await db.close()
        return result, history_rows, status

    result, history_rows, status = asyncio.run(_run())
    assert result["recalc_mode"] == "syntax_error"
    assert "数据不足" not in result["recalc_message"]
    assert history_rows == 0  # 未落历史快照
    assert status == "syntax_error"


def test_recalc_gate_missing_formula(tmp_db):
    """无公式因子：如实返回 missing_formula，而不是'数据不足'"""
    from backend.services.factor_research import factor_research

    async def _run():
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO preset_factors (factor_code, factor_name, description) "
                "VALUES (?, ?, ?)",
                ("nof_x", "无公式因子", "参数化指标，无公式"),
            )
            await db.commit()
            cur = await db.execute(
                "SELECT id FROM preset_factors WHERE factor_code = 'nof_x'"
            )
            fid = (await cur.fetchone())["id"]
        finally:
            await db.close()
        return await factor_research.recalculate_preset_factor(fid)

    result = asyncio.run(_run())
    assert result["recalc_mode"] == "missing_formula"
    assert "数据不足" not in result["recalc_message"]
