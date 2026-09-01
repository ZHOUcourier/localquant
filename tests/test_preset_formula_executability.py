"""预置因子公式可执行性回归（P0-B）：日频公式库在本地行情上真实求值

历史教训：P0-2 的验收只靠静态分类器（AST 可解析 + 名字存在），整类运行时
失败——别名循环用 RETURNS 函数覆盖 returns 面板、ADV(n) 单参方言、裸 RETURNS
面板变量——被长期虚报为 executable。本测试直接走生产求值链
（normalize_formula → eval_factor_formula），在本地行情面板上真实求值全部
日频预置公式：允许清单之外不得出现任何新失败；允许清单内的坏公式必须稳定失败
（一旦修好须移出清单）；P0-B 修复的代表性公式必须真实求值成功。

面板收缩：全量 125 只 × 940 天求值约 390 秒；收缩为 20 只 × 约 570 天约 40 秒，
失败集合已验证与全量一致。行情缓存不足时跳过（不依赖 QMT 在线）。
"""

import re
import sqlite3

import pandas as pd
import pytest

from backend import database
from backend.services.factor_research import FactorResearchService, extract_formula

# 已知缺陷公式（源公式损坏 / 算子缺参 / 数据快照缺失），如实保留失败状态；
# 每条必须注明原因，修复后必须移出本清单（测试会强制检查）。
ALLOWED_FAILURES = {
    "Alpha101因子_056": "公式无误，但依赖流通市值面板（CAP），本地无 capital 股本快照数据，属数据缺失而非公式缺陷",
}

# P0-B 修复前被虚报 executable 的代表性公式，现在必须真实求值成功：
# 单参 ADV(n) 方言、裸 RETURNS 面板变量。
REPRESENTATIVE_FIXED = ("Alpha101因子_085", "Alpha101因子_014")


def _load_daily_formulas() -> list[tuple[str, str]]:
    """库内全部日频公式因子 [(factor_name, formula)]；跳过无公式与日内公式"""
    db = sqlite3.connect(f"file:{database.DB_PATH}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT factor_name, description FROM preset_factors ORDER BY id"
        ).fetchall()
    finally:
        db.close()
    out = []
    for name, desc in rows:
        formula = extract_formula(desc)
        if not formula or FactorResearchService._is_intraday_formula(formula):
            continue
        out.append((name, formula))
    return out


def _build_namespace() -> dict:
    """收缩面板上的求值命名空间（与 eval_formula_on_local 生产路径同构）"""
    from backend.services import market_data, reference_data
    from backend.services.factor_operators import build_operator_namespace

    codes = sorted(market_data.list_cached_codes("1d", exclude_indices=True))[:20]
    panels = market_data.load_price_panels(codes=codes, start_date="2024-06-01")
    ns = build_operator_namespace(
        panels, industry_map=reference_data.load_industry_map()
    )
    try:
        from backend.services.fundamental import build_fundamental_panels

        fund = build_fundamental_panels(codes, panels["close"].index)
        if fund:
            ns.update({f"fund_{f}": p for f, p in fund.items()})
            ns.update({f"FUND_{f.upper()}": p for f, p in fund.items()})
    except Exception:
        pass
    return ns


@pytest.fixture(scope="class")
def eval_env():
    from backend.services import market_data

    codes = market_data.list_cached_codes("1d", exclude_indices=True)
    if len(codes) < 20:
        pytest.skip(f"本地仅 {len(codes)} 只行情缓存，不足以构建可执行性回归面板")
    formulas = _load_daily_formulas()
    if len(formulas) < 260:
        pytest.fail(f"日频公式库异常缩水：仅 {len(formulas)} 个（预期 ≥260）")
    return _build_namespace(), formulas


class TestPresetFormulaExecutability:
    def test_daily_formulas_no_unexpected_failures(self, eval_env):
        """全库日频公式真实求值：允许清单外零失败，清单内必须稳定失败"""
        from backend.services.factor_operators import eval_factor_formula

        ns, formulas = eval_env
        failures: dict[str, str] = {}
        for name, formula in formulas:
            try:
                eval_factor_formula(formula, ns)
            except Exception as e:  # 任何异常都是不可执行，含非结构化异常
                code = getattr(e, "code", "unexpected")
                failures[name] = f"{code}: {e}"

        unexpected = {k: v for k, v in failures.items() if k not in ALLOWED_FAILURES}
        assert not unexpected, "允许清单之外出现新的公式求值失败:\n" + "\n".join(
            f"  {k} → {v}" for k, v in sorted(unexpected.items())
        )
        gone = set(ALLOWED_FAILURES) - set(failures)
        assert not gone, (
            f"以下允许失败公式现在可求值，请移出 ALLOWED_FAILURES: {sorted(gone)}"
        )

    def test_representative_adv_and_returns_evaluable(self, eval_env):
        """ADV(n) 单参方言与裸 RETURNS：修复前运行时失败，现在必须产出有效面板"""
        from backend.services.factor_operators import eval_factor_formula

        ns, formulas = eval_env
        by_name = dict(formulas)
        for name in REPRESENTATIVE_FIXED:
            assert name in by_name, f"因子库缺少代表性因子 {name}"
            out = eval_factor_formula(by_name[name], ns)
            if isinstance(out, pd.Series):
                out = out.to_frame()
            assert isinstance(out, pd.DataFrame) and not out.empty, (
                f"{name} 求值未产出有效因子面板"
            )

    def test_representative_formulas_contain_target_dialects(self, eval_env):
        """防止库变动导致代表性因子不再覆盖目标方言（测试失去意义）"""
        _, formulas = eval_env
        by_name = dict(formulas)
        assert re.search(r"\bADV\(\s*\d+\s*\)", by_name["Alpha101因子_085"], re.I)
        assert re.search(r"\bRETURNS\b(?!\s*\()", by_name["Alpha101因子_014"], re.I)
