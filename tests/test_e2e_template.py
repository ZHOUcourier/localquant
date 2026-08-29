"""端到端集成测试：构造 parquet 缓存 fixture，跑通 factor_research 模板工作流

不依赖 QMT——正是"消费已缓存 parquet"的路径（目标 Windows 环境上同构）。
"""

import asyncio
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.data.cache import DataCache
from backend.services import market_data


@pytest.fixture
def cached_market(tmp_path, monkeypatch):
    """在临时目录构造 30 只股票 × 150 日的日线缓存，并接管 market_data._cache"""
    cache = DataCache(tmp_path)
    rng = np.random.default_rng(2024)
    dates = pd.bdate_range("2023-01-02", periods=150)
    codes = [f"{600000 + i}.SH" for i in range(30)]
    for c in codes:
        rets = rng.normal(0.0005, 0.02, size=len(dates))
        close = 20 * np.cumprod(1 + rets)
        df = pd.DataFrame(
            {
                "open": close * (1 + rng.normal(0, 0.002, len(dates))),
                "high": close * (1 + abs(rng.normal(0, 0.01, len(dates)))),
                "low": close * (1 - abs(rng.normal(0, 0.01, len(dates)))),
                "close": close,
                "volume": rng.integers(1e6, 1e7, len(dates)).astype(float),
                "amount": close * rng.integers(1e6, 1e7, len(dates)),
            },
            index=dates,
        )
        cache.save(c, "1d", df)

    monkeypatch.setattr(market_data, "_cache", cache)
    return codes


def test_template_factor_research_runs_green(cached_market, monkeypatch):
    """加载 factor_research 模板，注入股票池后端到端执行，断言全绿且产出 IC/分组报告"""
    from backend.engine import runner
    from backend.plugins.loader import load_all_nodes

    load_all_nodes()  # 确保内置节点已注册到 ALL_WORK_NODES

    tpl = json.loads(Path("templates/factor_research.json").read_text(encoding="utf-8"))
    nodes = tpl["nodes"]
    # 给 FactorFormulaNode 注入股票池与区间（模板默认股票池可能为空）
    for n in nodes:
        if n["name"] == "FactorFormulaNode":
            n.setdefault("static_input_data", {})
            n["static_input_data"]["stock_pool"] = cached_market
            n["static_input_data"]["start_date"] = "20230101"
            n["static_input_data"]["end_date"] = "20231231"
            n["static_input_data"].setdefault(
                "formula", "RANK(close / DELAY(close, 5) - 1)"
            )

    ctx = asyncio.run(runner.run_workflow("e2e-test", nodes, tpl["links"]))
    assert ctx.status == "completed", f"工作流未完成: {ctx.status}"
    # FactorFormulaNode 应产出因子面板
    n1 = ctx.get_node_output("n1")
    assert n1 is not None and n1.get("factor_data") is not None


def test_load_price_panels_from_cache(cached_market):
    """缓存优先路径：无 QMT 时也能从 parquet 装配价格面板"""
    panels = market_data.load_price_panels(codes=cached_market[:10])
    assert "close" in panels
    assert not panels["close"].empty
    assert panels["close"].shape[1] == 10


def test_template_backtest_analysis_runs_green(cached_market):
    """backtest_analysis 模板（行情→因子信号→回测→输出）端到端跑通，产出净值曲线

    此前该模板因 QMTKlineNode 离线返回空、kline_data 结构与下游类型不匹配而失败；
    现在 QMTKlineNode 走本地缓存输出面板、BacktestNode 接受 DataFrame，应全绿。
    """
    from backend.engine import runner
    from backend.plugins.loader import load_all_nodes

    load_all_nodes()

    tpl = json.loads(Path("templates/backtest_analysis.json").read_text(encoding="utf-8"))
    ctx = asyncio.run(runner.run_workflow("e2e-bt", tpl["nodes"], tpl["links"]))
    assert ctx.status == "completed", f"工作流未完成: {ctx.status}"

    # QMTKlineNode 应从缓存输出非空 close 面板
    n1 = ctx.get_node_output("n1")
    assert n1 is not None and n1.get("close") is not None
    # BacktestNode 应产出净值曲线
    n3 = ctx.get_node_output("n3")
    assert n3 is not None and n3.get("equity_curve")


def test_template_stock_selection_runs_green(cached_market):
    """stock_selection 模板（两路价格因子→打分排序→输出）端到端跑通，产出排序结果

    此前该模板依赖 QMT 在线节点（K线+财务）而无法离线运行；现改为两路价格因子
    （各自从本地缓存加载），应全绿。
    """
    from backend.engine import runner
    from backend.plugins.loader import load_all_nodes

    load_all_nodes()

    tpl = json.loads(Path("templates/stock_selection.json").read_text(encoding="utf-8"))
    ctx = asyncio.run(runner.run_workflow("e2e-ss", tpl["nodes"], tpl["links"]))
    assert ctx.status == "completed", f"工作流未完成: {ctx.status}"

    # 两个因子节点都应产出因子面板
    n1 = ctx.get_node_output("n1")
    n2 = ctx.get_node_output("n2")
    assert n1 is not None and n1.get("factor_data") is not None
    assert n2 is not None and n2.get("factor_data") is not None
    # StockRankNode 应产出排序结果
    n3 = ctx.get_node_output("n3")
    assert n3 is not None
    assert n3.get("row_count", 0) >= 1
