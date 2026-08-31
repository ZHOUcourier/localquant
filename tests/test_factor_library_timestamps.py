"""factors 表时间戳回归：全库统一秒级（曾误用毫秒）。"""

import asyncio
import time
from pathlib import Path

from backend.models.factor import FactorCreate
from backend.routes import factor as factor_route


def test_register_factor_stores_seconds_not_ms(tmp_path, monkeypatch):
    from backend import database

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())

    before = int(time.time())
    asyncio.run(
        factor_route.register_factor(
            FactorCreate(name="ts_probe", formula="close / open")
        )
    )
    after = int(time.time())

    rows = asyncio.run(_fetch_rows())
    assert len(rows) == 1
    created_at, updated_at = rows[0]
    assert before <= created_at <= after
    assert before <= updated_at <= after
    # 秒级时间戳远小于 1e11；毫秒级（约 1.8e12）会超过
    assert created_at < 1e11
    assert updated_at < 1e11


async def _fetch_rows():
    from backend.database import get_db

    db = await get_db()
    try:
        cursor = await db.execute("SELECT created_at, updated_at FROM factors")
        return await cursor.fetchall()
    finally:
        await db.close()
