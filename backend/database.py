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

        # 策略库表（QUBE 对话产出 / 工作流快照；status: working=工作中, saved=已保存）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'working',
                source TEXT DEFAULT 'chat',
                content TEXT DEFAULT '',
                code TEXT DEFAULT '',
                workflow_id TEXT DEFAULT '',
                session_id TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        # 迁移：早期 strategies 表无 code 列则补齐
        cursor = await db.execute("PRAGMA table_info(strategies)")
        strategy_cols = [row[1] for row in await cursor.fetchall()]
        if "code" not in strategy_cols:
            await db.execute("ALTER TABLE strategies ADD COLUMN code TEXT DEFAULT ''")

        # 策略版本表（保存/AI 优化/回滚都产生一条版本记录）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS strategy_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                code TEXT DEFAULT '',
                content TEXT DEFAULT '',
                note TEXT DEFAULT '',
                backtest_json TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        """)

        # QUBE 会话表（bound_type/bound_id：会话绑定的画板工件 factor/strategy）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS qube_sessions (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '新对话',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                bound_type TEXT DEFAULT '',
                bound_id TEXT DEFAULT ''
            )
        """)

        # 迁移：早期 qube_sessions 无绑定列则补齐
        cursor = await db.execute("PRAGMA table_info(qube_sessions)")
        session_cols = [row[1] for row in await cursor.fetchall()]
        if "pinned" not in session_cols:
            await db.execute(
                "ALTER TABLE qube_sessions ADD COLUMN pinned INTEGER DEFAULT 0"
            )
        if "bound_type" not in session_cols:
            await db.execute(
                "ALTER TABLE qube_sessions ADD COLUMN bound_type TEXT DEFAULT ''"
            )
            await db.execute(
                "ALTER TABLE qube_sessions ADD COLUMN bound_id TEXT DEFAULT ''"
            )
        # 上下文压缩（Claude Code 式 compaction）：context_summary 保存压缩后的
        # 早期会话摘要，compact_upto 为已被压缩进摘要的最末消息 id（其后的消息仍按原文发送）。
        if "context_summary" not in session_cols:
            await db.execute(
                "ALTER TABLE qube_sessions ADD COLUMN context_summary TEXT DEFAULT ''"
            )
            await db.execute(
                "ALTER TABLE qube_sessions ADD COLUMN compact_upto INTEGER DEFAULT 0"
            )
            await db.execute(
                "ALTER TABLE qube_sessions ADD COLUMN compact_at INTEGER DEFAULT 0"
            )

        # QUBE 消息表（tool_calls_json：结构化工具轨迹 {calls, display_timeline, thinking}）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS qube_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                tool_calls_json TEXT DEFAULT '',
                FOREIGN KEY (session_id) REFERENCES qube_sessions(id)
            )
        """)

        # 迁移：早期 qube_messages 无 tool_calls_json 列则补齐
        cursor = await db.execute("PRAGMA table_info(qube_messages)")
        msg_cols = [row[1] for row in await cursor.fetchall()]
        if "tool_calls_json" not in msg_cols:
            await db.execute(
                "ALTER TABLE qube_messages ADD COLUMN tool_calls_json TEXT DEFAULT ''"
            )
        # 迁移：token 用量（usage_json：{prompt_tokens, completion_tokens,
        # reasoning_tokens, total_tokens, estimated}，API 返回或本地估算）
        if "usage_json" not in msg_cols:
            await db.execute(
                "ALTER TABLE qube_messages ADD COLUMN usage_json TEXT DEFAULT ''"
            )

        # QUBE 对话产出的因子（画板工件；与因子库 factors 表独立，存入因子库时落快照）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS qube_factors (
                id TEXT PRIMARY KEY,
                session_id TEXT DEFAULT '',
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                code_type TEXT DEFAULT 'formula',
                code TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)

        # 因子分析记录（9 阶段进度 + 指标/分组/图表结果，画板「历史分析」下拉数据源）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS factor_analyses (
                id TEXT PRIMARY KEY,
                factor_id TEXT NOT NULL,
                session_id TEXT DEFAULT '',
                status TEXT DEFAULT 'running',
                progress_json TEXT DEFAULT '{}',
                params_json TEXT DEFAULT '{}',
                metrics_json TEXT DEFAULT '{}',
                group_return_json TEXT DEFAULT '[]',
                charts_json TEXT DEFAULT '{}',
                error TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                finished_at INTEGER
            )
        """)

        # 策略回测记录（8 阶段进度 + 指标/净值/交易明细/日志，回测中心与画板共用）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id TEXT PRIMARY KEY,
                strategy_id TEXT DEFAULT '',
                strategy_name TEXT DEFAULT '',
                session_id TEXT DEFAULT '',
                status TEXT DEFAULT 'running',
                progress_json TEXT DEFAULT '{}',
                params_json TEXT DEFAULT '{}',
                metrics_json TEXT DEFAULT '{}',
                equity_json TEXT DEFAULT '[]',
                trades_json TEXT DEFAULT '[]',
                log_text TEXT DEFAULT '',
                error TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                finished_at INTEGER
            )
        """)

        # QUBE 技能库（builtin=1 系统内置不可改删；source/url 标注来源）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS qube_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT '',
                category_id TEXT DEFAULT '',
                params_json TEXT DEFAULT '[]',
                prompt TEXT DEFAULT '',
                builtin INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL,
                source TEXT DEFAULT '',
                url TEXT DEFAULT '',
                stars INTEGER DEFAULT 0
            )
        """)

        # 迁移：早期 qube_skills 无来源列则补齐
        cursor = await db.execute("PRAGMA table_info(qube_skills)")
        skill_cols = [row[1] for row in await cursor.fetchall()]
        if "source" not in skill_cols:
            await db.execute(
                "ALTER TABLE qube_skills ADD COLUMN source TEXT DEFAULT ''"
            )
            await db.execute("ALTER TABLE qube_skills ADD COLUMN url TEXT DEFAULT ''")
            await db.execute(
                "ALTER TABLE qube_skills ADD COLUMN stars INTEGER DEFAULT 0"
            )
        if "repo_url" not in skill_cols:
            await db.execute(
                "ALTER TABLE qube_skills ADD COLUMN repo_url TEXT DEFAULT ''"
            )

        # 技能仓库信息缓存（GitHub README/SKILL.md/元数据；按技能名缓存，seed 重建 ID 不变）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS qube_skill_repos (
                skill_name TEXT PRIMARY KEY,
                data_json TEXT DEFAULT '{}',
                fetched_at INTEGER DEFAULT 0
            )
        """)

        # 分析溯源（provenance）：记录每个因子/回测/组合结果的 universe、区间、
        # 复权、基准、参数等，保证任何数字可被复现。kind: factor/backtest/workflow
        await db.execute("""
            CREATE TABLE IF NOT EXISTS provenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                entity_id TEXT DEFAULT '',
                entity_name TEXT DEFAULT '',
                params_json TEXT DEFAULT '{}',
                metrics_json TEXT DEFAULT '{}',
                notes TEXT DEFAULT '',
                source TEXT DEFAULT 'manual',
                created_at INTEGER
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS ix_provenance_kind ON provenance(kind)"
        )

        # 每日批处理日志（调度器触发/手动重跑都写一行，状态可见）
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                status TEXT DEFAULT 'running',   -- running / ok / failed / skipped
                trigger TEXT DEFAULT 'schedule', -- schedule | manual
                detail TEXT DEFAULT '',
                started_at INTEGER,
                finished_at INTEGER
            )
        """)

        await db.commit()

    # 内置技能 seed（幂等，按 name 去重）
    from backend.services.qube_skills import seed_builtin_skills

    await seed_builtin_skills()


async def get_db() -> aiosqlite.Connection:
    db = aiosqlite.connect(DB_PATH)
    db = await db
    db.row_factory = aiosqlite.Row
    return db
