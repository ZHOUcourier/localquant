"""实验记录时间戳单位回归（P1-C）

历史 bug：experiments.created_at 曾以毫秒落库，而其余各表与前端渲染
（new Date(ts * 1000)）一律按秒，导致实验时间显示为公元 5 万年。
本测试钉死写入侧单位：新实验时间戳必须是秒。
"""

import asyncio
import sqlite3
import time

import pytest

from backend import database
from backend.models.experiment import ExperimentCreate
from backend.services.experiment_service import experiment_service


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())
    return tmp_path / "test.db"


def test_create_stores_seconds_not_ms(tmp_db):
    req = ExperimentCreate(source="backtest", source_id="run-x", name="单位测试")
    before = int(time.time())
    asyncio.run(experiment_service.create(req))
    after = int(time.time())

    conn = sqlite3.connect(tmp_db)
    try:
        (ts,) = conn.execute("SELECT created_at FROM experiments").fetchone()
    finally:
        conn.close()

    assert before <= ts <= after, "created_at 不在当前墙钟秒区间内"
    assert ts < 10**11, "created_at 数量级异常（毫秒值 ≥1e12，秒值 ~1.7e9）"


def test_seconds_rows_sort_consistently_with_migrated_legacy(tmp_db):
    """迁移后的历史行（秒）与新写入行同单位，按时间排序不乱"""
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "INSERT INTO experiments (id, source, name, tags, params_json, "
            "metrics_json, status, created_at) VALUES "
            "('legacy', 'backtest', '历史行', '[]', '{}', '{}', 'completed', ?)",
            (int(time.time()) - 3600,),
        )
        conn.commit()
    finally:
        conn.close()

    asyncio.run(
        experiment_service.create(
            ExperimentCreate(source="backtest", name="新行")
        )
    )
    results = asyncio.run(experiment_service.list_experiments())
    names = [r["name"] for r in results]
    assert names == ["新行", "历史行"], "秒级时间戳排序应使新行在前"
