"""分析溯源（provenance）服务

记录每个因子研究 / 回测 / 工作流结果的 universe、日期区间、复权、基准、
样本与关键参数，保证任何数字都能被复现。写入 provenance 表。
"""

from __future__ import annotations

import json
import time

from backend.database import get_db


async def record_provenance(
    kind: str,
    entity_id: str = "",
    entity_name: str = "",
    params: dict | None = None,
    metrics: dict | None = None,
    notes: str = "",
    source: str = "manual",
) -> int:
    """写入一条 provenance 记录，返回其 id"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO provenance "
            "(kind, entity_id, entity_name, params_json, metrics_json, notes, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                kind,
                entity_id,
                entity_name,
                json.dumps(params or {}, ensure_ascii=False),
                json.dumps(metrics or {}, ensure_ascii=False),
                notes,
                source,
                int(time.time()),
            ),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def list_provenance(
    kind: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """按 kind / entity 查询 provenance 记录，倒序"""
    db = await get_db()
    try:
        sql = "SELECT * FROM provenance"
        conds: list[str] = []
        args: list = []
        if kind:
            conds.append("kind = ?")
            args.append(kind)
        if entity_id:
            conds.append("entity_id = ?")
            args.append(entity_id)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        cursor = await db.execute(sql, args)
        rows = await cursor.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            # 反序列化 JSON 字段，便于前端直接展示
            for k in ("params_json", "metrics_json"):
                try:
                    d[k] = json.loads(d[k] or "{}")
                except Exception:
                    d[k] = {}
            out.append(d)
        return out
    finally:
        await db.close()


async def latest_provenance(kind: str, entity_id: str) -> dict | None:
    """获取某个实体的最新一条 provenance"""
    res = await list_provenance(kind=kind, entity_id=entity_id, limit=1)
    return res[0] if res else None