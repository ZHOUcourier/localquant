"""pytest 会话级初始化：幂等地确保新表(provenance/daily_jobs)存在，避免测试只连不建表。"""

import asyncio

import pytest

from backend import database


@pytest.fixture(scope="session", autouse=True)
def _init_db_session():
    asyncio.run(database.init_db())
    yield