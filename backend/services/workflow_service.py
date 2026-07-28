"""工作流服务 - 处理工作流 CRUD 和运行逻辑"""
import json
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from backend.config import settings
from backend.database import get_db
from backend.engine.runner import run_workflow, run_workflow_stream


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def list_workflows() -> list[dict[str, Any]]:
    """列出所有工作流"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, description, updated_at FROM workflows ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def create_workflow(
    name: str,
    description: str = "",
    nodes: list | None = None,
    links: list | None = None,
) -> dict[str, Any]:
    """创建工作流"""
    wf_id = str(uuid.uuid4())
    now = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO workflows (id, name, description, nodes_json, links_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (wf_id, name, description,
             json.dumps(nodes or [], ensure_ascii=False),
             json.dumps(links or [], ensure_ascii=False),
             now, now),
        )
        await db.commit()
        return {
            "id": wf_id, "name": name, "description": description,
            "nodes": nodes or [], "links": links or [],
            "created_at": now, "updated_at": now, "last_run_id": None,
        }
    finally:
        await db.close()


async def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    """获取单个工作流详情"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["nodes"] = json.loads(d.get("nodes_json", "[]"))
        d["links"] = json.loads(d.get("links_json", "[]"))
        return d
    finally:
        await db.close()


async def update_workflow(workflow_id: str, **kwargs) -> dict[str, Any] | None:
    """更新工作流"""
    existing = await get_workflow(workflow_id)
    if not existing:
        return None

    now = int(time.time())
    updates = {}
    if "name" in kwargs and kwargs["name"] is not None:
        updates["name"] = kwargs["name"]
    if "description" in kwargs and kwargs["description"] is not None:
        updates["description"] = kwargs["description"]
    if "nodes" in kwargs and kwargs["nodes"] is not None:
        updates["nodes_json"] = json.dumps(kwargs["nodes"], ensure_ascii=False)
    if "links" in kwargs and kwargs["links"] is not None:
        updates["links_json"] = json.dumps(kwargs["links"], ensure_ascii=False)

    if updates:
        updates["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [workflow_id]
        db = await get_db()
        try:
            await db.execute(f"UPDATE workflows SET {set_clause} WHERE id = ?", values)
            await db.commit()
        finally:
            await db.close()

    return await get_workflow(workflow_id)


async def delete_workflow(workflow_id: str) -> bool:
    """删除工作流"""
    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# 运行（非 SSE，同步返回全部结果）
# ---------------------------------------------------------------------------

async def run(workflow_id: str) -> dict[str, Any] | None:
    """运行工作流（同步等待完成）"""
    wf = await get_workflow(workflow_id)
    if not wf:
        return None

    run_id = str(uuid.uuid4())
    now = int(time.time())

    # 创建运行记录
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO workflow_runs (id, workflow_id, status, started_at)
               VALUES (?, ?, 'running', ?)""",
            (run_id, workflow_id, now),
        )
        await db.commit()
    finally:
        await db.close()

    # 执行工作流
    ctx = await run_workflow(run_id, wf["nodes"], wf["links"])

    # 更新运行记录
    finished_at = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            """UPDATE workflow_runs
               SET status = ?, finished_at = ?, node_outputs_json = ?, logs_json = ?
               WHERE id = ?""",
            (ctx.status, finished_at,
             json.dumps(ctx.node_outputs, ensure_ascii=False, default=str),
             json.dumps(ctx.logs, ensure_ascii=False),
             run_id),
        )
        await db.execute(
            "UPDATE workflows SET last_run_id = ?, updated_at = ? WHERE id = ?",
            (run_id, finished_at, workflow_id),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "id": run_id,
        "workflow_id": workflow_id,
        "status": ctx.status,
        "started_at": now,
        "finished_at": finished_at,
        "node_outputs": ctx.node_outputs,
        "logs": ctx.logs,
    }


# ---------------------------------------------------------------------------
# 运行（SSE 流式）
# ---------------------------------------------------------------------------

async def run_stream(workflow_id: str) -> AsyncGenerator[str, None]:
    """
    流式运行工作流，yield SSE 事件字符串。

    调用方（路由层）用 StreamingResponse 包装即可。
    注意：调用前应先通过 get_workflow 验证工作流存在。
    """
    wf = await get_workflow(workflow_id)
    if not wf:
        # 工作流不存在时 yield 一个错误事件然后结束
        import json as _json
        yield f"event: error\ndata: {_json.dumps({'message': 'Workflow not found'})}\n\n"
        return

    run_id = str(uuid.uuid4())
    now = int(time.time())

    # 创建运行记录
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO workflow_runs (id, workflow_id, status, started_at)
               VALUES (?, ?, 'running', ?)""",
            (run_id, workflow_id, now),
        )
        await db.commit()
    finally:
        await db.close()

    # 流式执行
    final_status = "completed"
    async for sse_event in run_workflow_stream(run_id, wf["nodes"], wf["links"]):
        # 追踪最终状态
        if "workflow_failed" in sse_event:
            final_status = "failed"
        yield sse_event

    # 流结束后更新运行记录（简化：不存完整 node_outputs，只存状态和日志）
    finished_at = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            """UPDATE workflow_runs
               SET status = ?, finished_at = ?
               WHERE id = ?""",
            (final_status, finished_at, run_id),
        )
        await db.execute(
            "UPDATE workflows SET last_run_id = ?, updated_at = ? WHERE id = ?",
            (run_id, finished_at, workflow_id),
        )
        await db.commit()
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------

def _templates_dir() -> Path:
    d = settings.templates_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


async def list_templates() -> list[dict[str, Any]]:
    """列出所有可用模板"""
    d = _templates_dir()
    results = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append({
                "id": f.stem,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "nodes": data.get("nodes", []),
                "links": data.get("links", []),
            })
        except Exception:
            continue
    return results


async def create_from_template(template_id: str) -> dict[str, Any]:
    """从模板创建工作流"""
    d = _templates_dir()
    f = d / f"{template_id}.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text(encoding="utf-8"))
    name = data.get("name", template_id)
    description = data.get("description", "")
    nodes = data.get("nodes", [])
    links = data.get("links", [])
    return await create_workflow(name=name, description=description, nodes=nodes, links=links)


# ---------------------------------------------------------------------------
# 运行记录
# ---------------------------------------------------------------------------

async def list_runs(workflow_id: str) -> list[dict[str, Any]]:
    """列出工作流的运行记录"""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT id, workflow_id, status, started_at, finished_at,
                      node_outputs_json, logs_json
               FROM workflow_runs WHERE workflow_id = ?
               ORDER BY started_at DESC""",
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["node_outputs"] = json.loads(d.pop("node_outputs_json", "{}"))
            d["logs"] = json.loads(d.pop("logs_json", "[]"))
            results.append(d)
        return results
    finally:
        await db.close()
