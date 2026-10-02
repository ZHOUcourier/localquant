"""回测成交明细落库回归测试（P0-A）

覆盖 2026-08-30 审查发现的三个同源问题：
1. 成交明细按位置索引从未对齐的原始价格面板取价 → 价格错位；
2. `price <= 0` 守卫挡不住 NaN → NaN 价成交落库；
3. 含 NaN 的历史记录读出后严格 JSON 序列化失败 → 详情接口 500。
"""

import json

import numpy as np
import pandas as pd

from backend.services.backtest_records import _trade_tail
from backend.services.qube_research import run_row_to_dict

DATES = pd.to_datetime(
    ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]
)


def _raw_prices():
    # 原始面板：5 行（比对齐后的持仓多 2 行），且列顺序与持仓相反——
    # 位置索引取价必然错位，标签对齐取价才正确。
    return pd.DataFrame(
        {
            "B": [200.0, 201.0, 202.0, 203.0, 204.0],
            "A": [100.0, 101.0, 102.0, 103.0, 104.0],
        },
        index=DATES,
    )


def test_trade_tail_aligns_misaligned_price_panel():
    # 引擎对齐后的持仓只含中间 3 天
    positions = pd.DataFrame(
        {
            "A": [0.5, 0.5, 0.0],
            "B": [0.0, 0.3, 0.3],
        },
        index=DATES[1:4],
    )
    trades = _trade_tail(positions, _raw_prices(), initial_capital=1_000_000)

    by_key = {(t["ts"], t["symbol"]): t for t in trades}
    assert ("2026-07-28", "A") in by_key  # 首日建仓
    assert ("2026-07-29", "B") in by_key
    assert ("2026-07-30", "A") in by_key  # 清仓

    # 价格必须等于「成交当日」的标签价，而不是错位后的值
    assert by_key[("2026-07-28", "A")]["price"] == 101.0
    assert by_key[("2026-07-29", "B")]["price"] == 202.0
    assert by_key[("2026-07-30", "A")]["price"] == 103.0
    assert all(np.isfinite(t["price"]) for t in trades)


def test_trade_tail_skips_nan_and_nonpositive_prices():
    positions = pd.DataFrame(
        {"A": [0.5, 0.5], "B": [0.4, 0.4]}, index=DATES[:2]
    )
    prices = pd.DataFrame(
        {"A": [float("nan"), 101.0], "B": [0.0, 201.0]},
        index=DATES[:2],
    )
    trades = _trade_tail(positions, prices, initial_capital=1_000_000)

    # 首日建仓两笔：一笔 NaN 价、一笔 0 价，都必须被丢弃而不是落库
    assert trades == []


def test_run_row_to_dict_sanitizes_legacy_nan():
    # 模拟历史污染记录：trades/equity/metrics 内含 NaN 字面量
    row = {
        "id": "r1",
        "strategy_id": "",
        "strategy_name": "run-api",
        "session_id": "",
        "status": "done",
        "progress_json": "{}",
        "params_json": "{}",
        "metrics_json": '{"total_return": 0.14, "sharpe_ratio": NaN}',
        "equity_json": '[{"ts": "2026-08-06", "equity": 1000.0}, '
        '{"ts": "2026-08-07", "equity": NaN}]',
        "trades_json": '[{"ts": "2026-08-07", "symbol": "000037.SZ", '
        '"side": "买入", "weight": 0.001, "price": NaN}]',
        "error": "",
        "created_at": 1788103014,
        "finished_at": 1788103014,
        "log_text": "",
    }
    d = run_row_to_dict(row, with_detail=True)

    assert d["metrics"]["sharpe_ratio"] is None
    assert d["metrics"]["total_return"] == 0.14
    assert d["equity"][1]["equity"] is None
    assert d["trades"][0]["price"] is None

    # Starlette 使用 allow_nan=False；净化后必须可严格序列化（否则详情接口 500）
    json.dumps(d, allow_nan=False, ensure_ascii=False)


def test_persist_backtest_run_records_sandboxed(tmp_path, monkeypatch):
    """run-strategy 直跑链路：执行环境（sandboxed）随记录落库 metrics 与日志"""
    import asyncio

    from backend import database
    from backend.services.backtest_records import persist_backtest_run

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())

    idx = pd.DatetimeIndex(["2026-07-01", "2026-07-02"])
    result = {
        "equity_curve": pd.Series([1_000_000.0, 1_010_000.0], index=idx),
        "positions": pd.DataFrame({"A": [0.5, 0.5]}, index=idx),
        "prices": pd.DataFrame({"A": [10.0, 10.1]}, index=idx),
        "cost_summary": {},
        "assumptions": [],
    }
    run_id = asyncio.run(
        persist_backtest_run(
            params={"signal_code": "def generate_signals(prices, **kw): ..."},
            result=result,
            metrics={"total_return": 0.01},
            strategy_name="沙箱标注测试",
            source="run_strategy",
            sandboxed=False,
        )
    )

    async def _q():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT metrics_json, log_text FROM backtest_runs WHERE id = ?",
                (run_id,),
            )
            return await cur.fetchone()
        finally:
            await db.close()

    row = asyncio.run(_q())
    metrics = json.loads(row["metrics_json"])
    assert metrics["sandboxed"] is False
    assert "进程内执行（无容器隔离）" in row["log_text"]
    # 实验自动创建只收数值指标，sandboxed 布尔值不会进实验指标卡
