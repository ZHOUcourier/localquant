"""QUBE 投研编排与技能库单测

覆盖：内置技能 seed（30 个）、技能 CRUD 权限、因子分析 9 阶段编排、
回测 8 阶段编排与落库（净值/交易明细/日志/进度）。
行情与沙箱用合成数据 monkeypatch，不依赖本地 QMT 缓存。
"""

import asyncio
import json
import time
import uuid

import numpy as np
import pandas as pd
import pytest

import backend.database as database


@pytest.fixture()
def qube_db(tmp_path, monkeypatch):
    """独立临时数据库（不污染 data/localquant.db）"""
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())
    return tmp_path / "test.db"


def _synth_panels(n_days=80, n_stocks=12, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    cols = [f"{600000 + i}.SH" for i in range(n_stocks)]
    close = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0, 0.02, (n_days, n_stocks)), axis=0),
        index=dates,
        columns=cols,
    )
    volume = pd.DataFrame(
        rng.integers(1_000_000, 5_000_000, (n_days, n_stocks)),
        index=dates,
        columns=cols,
    ).astype(float)
    return {
        "open": close * 0.99,
        "high": close * 1.02,
        "low": close * 0.98,
        "close": close,
        "volume": volume,
        "amount": close * volume,
    }


# ── 技能库 ─────────────────────────────────────────────────


def test_builtin_skills_seeded(qube_db):
    """init_db 后内置技能 = QuantSkills 6 个 + LLMQuant 18 个，均带来源标注"""

    async def _check():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT source, COUNT(*) AS n FROM qube_skills "
                "WHERE builtin = 1 GROUP BY source"
            )
            counts = {r["source"]: r["n"] for r in await cur.fetchall()}
            cur = await db.execute(
                "SELECT COUNT(*) AS n FROM qube_skills WHERE builtin = 1 "
                "AND (url = '' OR source = '')"
            )
            missing_meta = (await cur.fetchone())["n"]
        finally:
            await db.close()
        return counts, missing_meta

    counts, missing_meta = asyncio.run(_check())
    assert counts == {"QuantSkills": 6, "LLMQuant": 18}
    assert missing_meta == 0, "每个内置技能都必须标注来源与链接"


def test_builtin_skills_have_detailed_prompt(qube_db):
    """内置技能正文（prompt）内容详实非空"""

    async def _check():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT name, LENGTH(prompt) AS n FROM qube_skills WHERE builtin = 1"
            )
            return {r["name"]: r["n"] for r in await cur.fetchall()}
        finally:
            await db.close()

    lengths = asyncio.run(_check())
    assert len(lengths) == 24
    assert all(n > 200 for n in lengths.values()), "每个内置技能正文应详实（>200 字符）"


# ── 因子分析编排（9 阶段）─────────────────────────────────


def test_factor_analysis_pipeline(qube_db, monkeypatch):
    from backend.services import market_data, qube_research

    monkeypatch.setattr(
        market_data,
        "load_price_panels",
        lambda codes, start_date, end_date: _synth_panels(),
    )

    async def _run():
        now = int(time.time())
        fid = str(uuid.uuid4())
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO qube_factors (id, session_id, name, code_type, code, "
                "created_at, updated_at) VALUES (?, 's1', '5日动量', 'formula', "
                "'close / DELAY(close, 5) - 1', ?, ?)",
                (fid, now, now),
            )
            await db.commit()
        finally:
            await db.close()
        aid = await qube_research.create_factor_analysis(
            fid, "s1", {"adjustment_cycle": 5, "group_number": 5}
        )
        result = await qube_research.execute_factor_analysis(aid)
        db = await database.get_db()
        try:
            cur = await db.execute("SELECT * FROM factor_analyses WHERE id = ?", (aid,))
            row = await cur.fetchone()
        finally:
            await db.close()
        return result, row

    result, row = asyncio.run(_run())
    assert row["status"] == "done"
    progress = json.loads(row["progress_json"])
    assert progress["percent"] == 100
    assert len(progress["stages"]) == 9
    assert all(s["status"] == "done" for s in progress["stages"])
    metrics = json.loads(row["metrics_json"])
    assert "ic_mean" in metrics["summary"]
    charts = json.loads(row["charts_json"])
    assert charts["ic"]["series"], "IC 序列不应为空"
    assert charts["group_cumulative"], "分组累计收益不应为空"
    assert result["summary"]["ic_mean"] == metrics["summary"]["ic_mean"]


def test_factor_analysis_error_marks_stage(qube_db, monkeypatch):
    """公式非法时 status=error 且进行中阶段标记 error"""
    from backend.services import market_data, qube_research

    monkeypatch.setattr(
        market_data,
        "load_price_panels",
        lambda codes, start_date, end_date: _synth_panels(),
    )

    async def _run():
        now = int(time.time())
        fid = str(uuid.uuid4())
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO qube_factors (id, session_id, name, code_type, code, "
                "created_at, updated_at) VALUES (?, 's1', '坏因子', 'formula', "
                "'NOT_AN_OPERATOR(close)', ?, ?)",
                (fid, now, now),
            )
            await db.commit()
        finally:
            await db.close()
        aid = await qube_research.create_factor_analysis(fid, "s1", {})
        with pytest.raises(Exception):
            await qube_research.execute_factor_analysis(aid)
        db = await database.get_db()
        try:
            cur = await db.execute("SELECT * FROM factor_analyses WHERE id = ?", (aid,))
            return await cur.fetchone()
        finally:
            await db.close()

    row = asyncio.run(_run())
    assert row["status"] == "error"
    assert row["error"]
    progress = json.loads(row["progress_json"])
    assert any(s["status"] == "error" for s in progress["stages"])


# ── 回测编排（8 阶段）────────────────────────────────────


def test_backtest_run_pipeline(qube_db, monkeypatch):
    from backend.services import market_data, qube_research, sandbox

    panels = _synth_panels()
    monkeypatch.setattr(
        market_data, "load_price_panels", lambda codes, start_date, end_date: panels
    )
    monkeypatch.setattr(
        market_data,
        "load_reference_panels",
        lambda close, volume=None: {
            "tradable_mask": None,
            "up_limit": None,
            "down_limit": None,
        },
    )

    async def fake_run_signals(code, prices):
        # 5 日动量做多前 3 名（等权）
        mom = prices.pct_change(5)
        rank = mom.rank(axis=1, ascending=False)
        signals = (rank <= 3).astype(float) / 3.0
        return signals, False

    monkeypatch.setattr(sandbox, "run_signals", fake_run_signals)

    async def _run():
        rid = await qube_research.create_backtest_run(
            "strat-1", "动量策略", "s1", "def generate_signals(prices, **kw): ...", {}
        )
        result = await qube_research.execute_backtest_run(rid)
        db = await database.get_db()
        try:
            cur = await db.execute("SELECT * FROM backtest_runs WHERE id = ?", (rid,))
            return result, await cur.fetchone()
        finally:
            await db.close()

    result, row = asyncio.run(_run())
    assert row["status"] == "done"
    progress = json.loads(row["progress_json"])
    assert progress["percent"] == 100
    assert len(progress["stages"]) == 8
    metrics = json.loads(row["metrics_json"])
    assert "total_return" in metrics
    assert "max_drawdown" in metrics
    equity = json.loads(row["equity_json"])
    assert len(equity) > 0 and {"ts", "equity"} <= set(equity[0])
    trades = json.loads(row["trades_json"])
    assert len(trades) > 0 and {"ts", "symbol", "side", "price", "qty", "fee"} <= set(
        trades[0]
    )
    assert "回测完成" in row["log_text"]
    assert result["metrics"]["trade_count"] == metrics["trade_count"]
