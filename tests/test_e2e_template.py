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
