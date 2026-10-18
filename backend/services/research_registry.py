"""本地研究登记与证据审计。仅管理记录，不访问行情、LLM 或交易接口。"""

import hashlib
import json
import time
import uuid
from contextlib import asynccontextmanager

from backend.database import get_db
from backend.models.research import (
    ReviewRequest,
    StudyCreate,
    TrialCreate,
    normalize_codes,
)


async def ensure_tables(db) -> None:
    """在调用方事务内建表，不自行提交，也不依赖全库 init_db。"""
    statements = (
        """CREATE TABLE IF NOT EXISTS research_studies (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            hypothesis TEXT NOT NULL,
            sources_json TEXT NOT NULL,
            protocol_json TEXT NOT NULL,
            protocol_hash TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'research'
                CHECK (state IN ('research', 'active', 'watch', 'dormant', 'retired')),
            selected_trial_id TEXT,
            universe_json TEXT,
            created_at INTEGER NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS research_trials (
            id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL REFERENCES research_studies(id),
            formula TEXT NOT NULL,
            direction INTEGER NOT NULL CHECK (direction IN (-1, 1)),
            rationale TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            UNIQUE (study_id, formula, direction)
        )""",
        """CREATE TABLE IF NOT EXISTS research_runs (
            id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL REFERENCES research_studies(id),
            trial_id TEXT NOT NULL REFERENCES research_trials(id),
            phase TEXT NOT NULL CHECK (phase IN ('validation', 'holdout', 'monitor')),
            status TEXT NOT NULL CHECK (
                status IN ('running', 'completed', 'awaiting_data', 'failed')),
            result_json TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS research_reviews (
            id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL REFERENCES research_studies(id),
            from_state TEXT NOT NULL,
            target_state TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )""",
        """CREATE UNIQUE INDEX IF NOT EXISTS ix_research_one_running
            ON research_runs(study_id) WHERE status = 'running'""",
        """CREATE INDEX IF NOT EXISTS ix_research_runs_trial_phase
            ON research_runs(trial_id, phase, status)""",
        """CREATE INDEX IF NOT EXISTS ix_research_reviews_study
            ON research_reviews(study_id)""",
        # 与 database.init_db 的已有表兼容；独立临时数据库也能原子落审计记录。
        """CREATE TABLE IF NOT EXISTS experiments (
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
        )""",
    )
    for statement in statements:
        await db.execute(statement)


@asynccontextmanager
async def _transaction():
    db = await get_db()
    try:
        # 检查条件、选择锁定、写入记录不可被另一个连接插入；读取也获得一致快照。
        await db.execute("BEGIN IMMEDIATE")
        await ensure_tables(db)
        yield db
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    finally:
        await db.close()


def _json(value) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Research evidence must be finite, JSON-serializable data"
        ) from exc


def _decode(row) -> dict:
    value = dict(row)
    for key in ("sources", "protocol", "universe", "result"):
        stored_key = f"{key}_json"
        if stored_key in value:
            stored = value.pop(stored_key)
            # SQL NULL 表示尚未冻结，JSON [] 表示已经冻结为空；对外都返回列表。
            value[key] = json.loads(stored) if stored is not None else []
    return value


async def _one(db, sql: str, params: tuple = ()):
    async with db.execute(sql, params) as cursor:
        return await cursor.fetchone()


async def _many(db, sql: str, params: tuple = ()) -> list[dict]:
    async with db.execute(sql, params) as cursor:
        return [_decode(row) for row in await cursor.fetchall()]


async def _study(db, study_id: str) -> dict:
    row = await _one(db, "SELECT * FROM research_studies WHERE id = ?", (study_id,))
    if row is None:
        raise KeyError(f"Study not found: {study_id}")
    return _decode(row)


async def _trial(db, trial_id: str) -> dict:
    row = await _one(db, "SELECT * FROM research_trials WHERE id = ?", (trial_id,))
    if row is None:
        raise KeyError(f"Trial not found: {trial_id}")
    return _decode(row)


async def _completed(db, trial_id: str, phase: str):
    return await _one(
        db,
        """SELECT * FROM research_runs
            WHERE trial_id = ? AND phase = ? AND status = 'completed' LIMIT 1""",
        (trial_id, phase),
    )


async def create_study(req: StudyCreate) -> dict:
    # 对列表等可变嵌套对象重新校验、序列化为独立快照；此后没有协议更新接口。
    req = StudyCreate.model_validate(req.model_dump())
    protocol_json = _json(req.protocol.model_dump())
    study_id = str(uuid.uuid4())
    async with _transaction() as db:
        await db.execute(
            """INSERT INTO research_studies
                (id, title, hypothesis, sources_json, protocol_json, protocol_hash,
                 state, selected_trial_id, universe_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'research', NULL, NULL, ?)""",
            (
                study_id,
                req.title,
                req.hypothesis,
                _json(req.sources),
                protocol_json,
                hashlib.sha256(protocol_json.encode("utf-8")).hexdigest(),
                int(time.time()),
            ),
        )
        return await _study(db, study_id)


async def list_studies() -> list[dict]:
    async with _transaction() as db:
        return await _many(
            db, "SELECT * FROM research_studies ORDER BY created_at DESC, rowid DESC"
        )


async def get_study(study_id: str) -> dict | None:
    async with _transaction() as db:
        row = await _one(db, "SELECT * FROM research_studies WHERE id = ?", (study_id,))
        if row is None:
            return None
        study = _decode(row)
        study["trials"] = await _many(
            db,
            "SELECT * FROM research_trials WHERE study_id = ? ORDER BY rowid",
            (study_id,),
        )
        study["runs"] = await _many(
            db,
            "SELECT * FROM research_runs WHERE study_id = ? ORDER BY rowid",
            (study_id,),
        )
        study["reviews"] = await _many(
            db,
            "SELECT * FROM research_reviews WHERE study_id = ? ORDER BY rowid",
            (study_id,),
        )
        return study


async def register_trial(study_id: str, req: TrialCreate) -> dict:
    req = TrialCreate.model_validate(req.model_dump())
    async with _transaction() as db:
        study = await _study(db, study_id)
        existing = await _one(
            db,
            """SELECT * FROM research_trials
                WHERE study_id = ? AND formula = ? AND direction = ?""",
            (study_id, req.formula, req.direction),
        )
        if existing is not None:
            return _decode(existing)
        if study["selected_trial_id"] is not None:
            raise ValueError("Holdout selection is locked; no new trials are allowed")
        count = await _one(
            db, "SELECT COUNT(*) FROM research_trials WHERE study_id = ?", (study_id,)
        )
        if count[0] >= study["protocol"]["trial_budget"]:
            raise ValueError("Trial budget exhausted")
        trial_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO research_trials (id, study_id, formula, direction, rationale, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
            (
                trial_id,
                study_id,
                req.formula,
                req.direction,
                req.rationale,
                int(time.time()),
            ),
        )
        return await _trial(db, trial_id)


async def begin_run(trial_id: str, phase: str) -> tuple[dict, dict, dict]:
    if phase not in ("validation", "holdout", "monitor"):
        raise ValueError("Unknown research phase")
    async with _transaction() as db:
        trial = await _trial(db, trial_id)
        study = await _study(db, trial["study_id"])
        running = await _one(
            db,
            "SELECT id FROM research_runs WHERE study_id = ? AND status = 'running'",
            (study["id"],),
        )
        if running is not None:
            raise ValueError("Another run is running for this study")
        if phase == "validation":
            if await _completed(db, trial_id, phase) is not None:
                raise ValueError("Validation has already completed for this trial")
        elif phase == "holdout":
            if study["selected_trial_id"] not in (None, trial_id):
                raise ValueError("Holdout selection is locked to another trial")
            if await _completed(db, trial_id, "validation") is None:
                raise ValueError("Holdout requires completed validation for this trial")
            if await _completed(db, trial_id, "holdout") is not None:
                raise ValueError("Holdout has already completed")
            # 必须先提交选择，再由调用方计算；无数据或失败也不解除锁定。
            await db.execute(
                "UPDATE research_studies SET selected_trial_id = ? WHERE id = ?",
                (trial_id, study["id"]),
            )
            study["selected_trial_id"] = trial_id
        else:
            if (
                study["selected_trial_id"] != trial_id
                or await _completed(db, trial_id, "holdout") is None
            ):
                raise ValueError(
                    "Monitor requires the selected trial's completed holdout"
                )
        run = {
            "id": str(uuid.uuid4()),
            "study_id": study["id"],
            "trial_id": trial_id,
            "phase": phase,
            "status": "running",
            "result": {},
            "error": "",
            "created_at": int(time.time()),
        }
        await db.execute(
            """INSERT INTO research_runs
                (id, study_id, trial_id, phase, status, result_json, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run["id"],
                run["study_id"],
                trial_id,
                phase,
                "running",
                "{}",
                "",
                run["created_at"],
            ),
        )
        return study, trial, run


async def finish_run(run_id: str, status: str, result: dict, error: str = "") -> dict:
    if status not in ("completed", "awaiting_data", "failed"):
        raise ValueError("finish_run requires a terminal status")
    # 请求错误统一交给主路由按 ValueError 映射，而非泄漏 TypeError。
    if not isinstance(result, dict) or not isinstance(error, str):
        raise ValueError("result must be a JSON object and error must be a string")  # noqa: TRY004
    result_json = _json(result)
    metrics_json = _json(result.get("summary", {}))
    async with _transaction() as db:
        row = await _one(db, "SELECT * FROM research_runs WHERE id = ?", (run_id,))
        if row is None:
            raise KeyError(f"Run not found: {run_id}")
        run = _decode(row)
        if run["status"] != "running":
            if (
                run["status"] == status
                and _json(run["result"]) == result_json
                and run["error"] == error
            ):
                return run
            raise ValueError("Finished research evidence cannot be overwritten")
        study = await _study(db, run["study_id"])
        trial = await _trial(db, run["trial_id"])
        params = {
            "phase": run["phase"],
            "protocol_hash": study["protocol_hash"],
            "trial": trial,
        }
        await db.execute(
            "UPDATE research_runs SET status = ?, result_json = ?, error = ? WHERE id = ?",
            (status, result_json, error, run_id),
        )
        # 不调用会新开连接的 experiment_service；任一写入失败则两表一并回滚。
        await db.execute(
            """INSERT INTO experiments
                (id, source, source_id, name, note, tags, params_json, metrics_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                "research",
                run_id,
                study["title"],
                error,
                _json(["research", run["phase"]]),
                _json(params),
                metrics_json,
                status,
                int(time.time()),
            ),
        )
        run.update(status=status, result=json.loads(result_json), error=error)
        return run


async def freeze_universe(study_id: str, codes: list[str]) -> list[str]:
    normalized = sorted(normalize_codes(codes))
    async with _transaction() as db:
        row = await _one(
            db, "SELECT universe_json FROM research_studies WHERE id = ?", (study_id,)
        )
        if row is None:
            raise KeyError(f"Study not found: {study_id}")
        if row["universe_json"] is not None:
            if json.loads(row["universe_json"]) != normalized:
                raise ValueError("Study universe is already frozen")
        else:
            await db.execute(
                "UPDATE research_studies SET universe_json = ? WHERE id = ?",
                (_json(normalized), study_id),
            )
        return normalized


async def review_study(study_id: str, req: ReviewRequest) -> dict:
    """记录人工复核并更新研究状态，返回 review 记录；不触发交易。"""
    req = ReviewRequest.model_validate(req.model_dump())
    async with _transaction() as db:
        study = await _study(db, study_id)
        if study["state"] == "retired" and req.target_state != "retired":
            raise ValueError("Retired is terminal; create a new study instead")
        if req.target_state == "active":
            evidence = await _completed(db, study["selected_trial_id"], "holdout")
            if (
                evidence is None
                or _decode(evidence)["result"].get("decision") != "supported"
            ):
                raise ValueError(
                    "Active requires a supported completed holdout for the selected trial"
                )
        elif study["state"] == "research":
            evidence = await _one(
                db,
                "SELECT id FROM research_runs WHERE study_id = ? AND status = 'completed' LIMIT 1",
                (study_id,),
            )
            if evidence is None:
                raise ValueError(
                    "A completed research run is required before changing state"
                )
        review = {
            "id": str(uuid.uuid4()),
            "study_id": study_id,
            "from_state": study["state"],
            "target_state": req.target_state,
            "note": req.note,
            "created_at": int(time.time()),
        }
        await db.execute(
            """INSERT INTO research_reviews
                (id, study_id, from_state, target_state, note, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                review["id"],
                study_id,
                review["from_state"],
                req.target_state,
                req.note,
                review["created_at"],
            ),
        )
        await db.execute(
            "UPDATE research_studies SET state = ? WHERE id = ?",
            (req.target_state, study_id),
        )
        return review
