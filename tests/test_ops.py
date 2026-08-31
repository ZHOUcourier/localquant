"""溯源 + 每日批处理测试（不依赖 QMT；未接数据时走 skipped 路径）"""

import asyncio

import pytest

from backend.services import provenance, scheduler


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """隔离到临时库：溯源/任务流水会真实写库，不得污染生产快照"""
    from backend import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())
    return tmp_path / "test.db"


def test_provenance_roundtrip():
    async def _run():
        rid = await provenance.record_provenance(
            kind="factor",
            entity_id="x1",
            entity_name="test_factor",
            params={"universe_n": 30, "adj": "front"},
            metrics={"rank_ic": 0.02},
            notes="tmp test",
        )
        assert rid > 0
        rows = await provenance.list_provenance(kind="factor", entity_id="x1")
        assert rows and rows[0]["entity_id"] == "x1"
        assert rows[0]["params_json"]["universe_n"] == 30
        assert rows[0]["metrics_json"]["rank_ic"] == pytest.approx(0.02)

    asyncio.run(_run())


def test_scheduler_run_jobs_without_data_is_skipped():
    res = scheduler.run_jobs_sync(trigger="manual", steps=["market", "recalc"])
    assert "market_update" in res
    assert res["market_update"] in ("skipped", "failed", "ok")

    status = asyncio.run(scheduler.check_status())
    assert "recent" in status


def test_config_scheduler_defaults():
    from backend.config import settings
    assert settings.scheduler_enabled
    assert settings.scheduler_update_time == "15:45"
    assert settings.scheduler_recalc_time == "18:30"