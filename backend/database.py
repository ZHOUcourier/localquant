import aiosqlite
from pathlib import Path

DB_PATH = Path("./data/localquant.db")


async def init_db():
    """初始化数据库表"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 工作流表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                nodes_json TEXT DEFAULT '[]',
                links_json TEXT DEFAULT '[]',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                last_run_id TEXT DEFAULT NULL
            )
        """)

        # 工作流运行记录表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                started_at INTEGER,
                finished_at INTEGER,
                node_outputs_json TEXT DEFAULT '{}',
                logs_json TEXT DEFAULT '[]',
                FOREIGN KEY (workflow_id) REFERENCES workflows(id)
            )
        """)

        # 实验记录表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT DEFAULT '',
                name TEXT DEFAULT '',
                note TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                params_json TEXT DEFAULT '{}',
                metrics_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'completed',
                created_at INTEGER NOT NULL
            )
        """)

        # 因子库表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS factors (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                formula TEXT DEFAULT '',
                code TEXT DEFAULT '',
                version INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        await db.commit()


async def get_db() -> aiosqlite.Connection:
    db = aiosqlite.connect(DB_PATH)
    db = await db
    db.row_factory = aiosqlite.Row
    return db
