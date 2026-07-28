from pathlib import Path

import aiosqlite

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
                last_run_id TEXT DEFAULT NULL,
                is_favorite INTEGER DEFAULT 0
            )
        """)

        # 迁移：如果 workflows 表没有 is_favorite 列则添加
        cursor = await db.execute("PRAGMA table_info(workflows)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "is_favorite" not in columns:
            await db.execute(
                "ALTER TABLE workflows ADD COLUMN is_favorite INTEGER DEFAULT 0"
            )

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

        # 预置因子分类表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS preset_factor_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_code TEXT UNIQUE NOT NULL,
                category_name TEXT NOT NULL,
                color_hex TEXT,
                factor_count INTEGER DEFAULT 0
            )
        """)

        # 预置因子表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS preset_factors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_code TEXT UNIQUE NOT NULL,
                factor_name TEXT NOT NULL,
                category_id INTEGER,
                category_code TEXT,
                category_name TEXT,
                category_color_hex TEXT,
                description TEXT,
                ic_mean REAL,
                rank_ic REAL,
                ic_ir REAL,
                ic_std REAL,
                annualized_return REAL,
                maximum_drawdown REAL,
                sharpe_ratio REAL,
                turnover_rate REAL,
                start_date TEXT,
                data_date TEXT,
                stock_pool TEXT,
                is_preset BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 因子池表
        await db.execute("""
            CREATE TABLE IF NOT EXISTS factor_pool (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (factor_id) REFERENCES preset_factors(id)
            )
        """)

        await db.commit()


async def get_db() -> aiosqlite.Connection:
    db = aiosqlite.connect(DB_PATH)
    db = await db
    db.row_factory = aiosqlite.Row
    return db
