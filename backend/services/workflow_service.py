"""工作流服务 - 处理工作流 CRUD 和运行逻辑"""

import asyncio
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


async def list_workflows(tab: str = "my", search: str = "") -> list[dict[str, Any]]:
    """列出工作流，支持 tab 筛选和搜索

    tab:
      - "preset": 返回预置模板（从 templates/ 目录读取）
      - "my": 我创建的工作流
      - "favorite": 收藏的工作流
    search: 按名称模糊搜索
    """
    if tab == "preset":
        return await list_templates()

    db = await get_db()
    try:
        conditions = []
        params = []

        if tab == "favorite":
            conditions.append("is_favorite = 1")

        if search:
            conditions.append("name LIKE ?")
            params.append(f"%{search}%")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        cursor = await db.execute(
            f"SELECT id, name, description, updated_at, is_favorite FROM workflows {where_clause} ORDER BY updated_at DESC",
            params,
        )
        rows = await cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["is_favorite"] = bool(d.get("is_favorite", 0))
            results.append(d)
        return results
    finally:
        await db.close()


async def create_workflow(
    name: str,
    description: str = "",
    nodes: list | None = None,
    links: list | None = None,
    is_favorite: bool = False,
) -> dict[str, Any]:
    """创建工作流"""
    wf_id = str(uuid.uuid4())
    now = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO workflows (id, name, description, nodes_json, links_json, created_at, updated_at, is_favorite)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                wf_id,
                name,
                description,
                json.dumps(nodes or [], ensure_ascii=False),
                json.dumps(links or [], ensure_ascii=False),
                now,
                now,
                1 if is_favorite else 0,
            ),
        )
        await db.commit()
        return {
            "id": wf_id,
            "name": name,
            "description": description,
            "nodes": nodes or [],
            "links": links or [],
            "created_at": now,
            "updated_at": now,
            "last_run_id": None,
            "is_favorite": is_favorite,
        }
    finally:
        await db.close()


async def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    """获取单个工作流详情"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
        )
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


async def toggle_favorite(workflow_id: str) -> dict[str, Any] | None:
    """切换工作流收藏状态，返回更新后的工作流"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, is_favorite FROM workflows WHERE id = ?", (workflow_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        new_val = 0 if row["is_favorite"] else 1
        await db.execute(
            "UPDATE workflows SET is_favorite = ? WHERE id = ?", (new_val, workflow_id)
        )
        await db.commit()
        return {"id": workflow_id, "is_favorite": bool(new_val)}
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
            (
                ctx.status,
                finished_at,
                json.dumps(ctx.node_outputs, ensure_ascii=False, default=str),
                json.dumps(ctx.logs, ensure_ascii=False),
                run_id,
            ),
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
# 参数扫描（网格搜索）
# ---------------------------------------------------------------------------

# 从节点输出中提取的关键指标（回测 metrics / 因子分析 summary）
_METRIC_KEYS = [
    "annual_return",
    "sharpe_ratio",
    "max_drawdown",
    "ic_mean",
    "rank_ic",
    "ic_ir",
    "total_return",
    "annualizedReturn",
    "sharpeRatio",
    "maxDrawdown",
]


def _extract_metrics(node_outputs: dict[str, Any]) -> dict[str, float]:
    """从末端分析/回测节点输出中提取数值指标（summary / metrics 字段）"""
    metrics: dict[str, float] = {}
    for out in node_outputs.values():
        if not isinstance(out, dict):
            continue
        for container_key in ("summary", "metrics"):
            block = out.get(container_key)
            if isinstance(block, dict):
                for k in _METRIC_KEYS:
                    if k in block and isinstance(block[k], (int, float)):
                        metrics[k] = float(block[k])
    return metrics


async def run_sweep(
    workflow_id: str,
    param_grid: dict[str, list],
    note: str = "",
) -> dict[str, Any] | None:
    """参数扫描：对 param_grid 做笛卡尔积，逐组合复用 runner 执行（启节点缓存）

    param_grid: {"<node_uuid>.<param>": [值列表]}，对应覆写节点 static_input_data。
    每组合写入 experiments（params=组合, metrics=末端分析/回测指标），
    实验页可直接用现有 compare 对比。
    """
    import itertools
    from copy import deepcopy

    from backend.models.experiment import ExperimentCreate
    from backend.services.experiment_service import experiment_service

    wf = await get_workflow(workflow_id)
    if not wf:
        return None
    if not param_grid:
        return {"error": "param_grid 为空，无可扫描的参数"}

    keys = list(param_grid.keys())
    value_lists = [param_grid[k] for k in keys]
    combos = list(itertools.product(*value_lists))

    results: list[dict] = []
    for combo in combos:
        overrides = dict(zip(keys, combo))
        nodes = deepcopy(wf["nodes"])
        # 将 {node_uuid.param: value} 写入对应节点的 static_input_data
        for spec, val in overrides.items():
            node_uuid, _, param = spec.partition(".")
            for n in nodes:
                if n["uuid"] == node_uuid:
                    n.setdefault("static_input_data", {})
                    n["static_input_data"][param] = val
                    break

        run_id = str(uuid.uuid4())
        ctx = await run_workflow(run_id, nodes, wf["links"], use_cache=True)
        metrics = _extract_metrics(ctx.node_outputs)

        # 写入实验记录（供实验页 compare 对比）
        exp = await experiment_service.create(
            ExperimentCreate(
                source="workflow",
                source_id=workflow_id,
                name=f"{wf.get('name', 'sweep')} | "
                + ", ".join(f"{k.split('.')[-1]}={v}" for k, v in overrides.items()),
                note=note,
                tags=["sweep"],
                params={k: v for k, v in overrides.items()},
                metrics=metrics,
            )
        )
        results.append(
            {
                "run_id": run_id,
                "experiment_id": exp["id"],
                "params": overrides,
                "metrics": metrics,
                "status": ctx.status,
            }
        )

    return {
        "workflow_id": workflow_id,
        "total": len(combos),
        "results": results,
    }


# ---------------------------------------------------------------------------
# 运行（SSE 流式）
# ---------------------------------------------------------------------------


async def run_stream(
    workflow_id: str, use_cache: bool = True
) -> AsyncGenerator[str, None]:
    """
    流式运行工作流，yield SSE 事件字符串。

    调用方（路由层）用 StreamingResponse 包装即可。
    注意：调用前应先通过 get_workflow 验证工作流存在。
    use_cache: 是否启用节点级输出缓存（默认启用；False 为忽略缓存强制重跑）。
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

    # 流式执行：runner 通过 report 回填状态/日志/每节点耗时；
    # 用 try/finally 保证客户端断开连接（生成器被取消）时运行记录也能正确收尾，
    # 避免历史里残留永远处于 running 的脏记录。
    report: dict[str, Any] = {}
    try:
        async for sse_event in run_workflow_stream(
            run_id, wf["nodes"], wf["links"], report, use_cache=use_cache
        ):
            yield sse_event
    finally:
        final_status = report.get("status", "running")
        if final_status == "running":
            # 流未走到自然终点（客户端断开/服务异常），记为已取消
            final_status = "cancelled"
        # 当前任务可能已被取消（客户端断开），finally 内直接 await 会再次抛
        # CancelledError，改用独立任务完成收尾写库
        asyncio.ensure_future(_finalize_run(run_id, workflow_id, final_status, report))


async def _finalize_run(
    run_id: str, workflow_id: str, final_status: str, report: dict[str, Any]
) -> None:
    """流式运行结束后更新运行记录（状态/日志/每节点耗时）"""
    finished_at = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            """UPDATE workflow_runs
               SET status = ?, finished_at = ?, node_outputs_json = ?, logs_json = ?
               WHERE id = ?""",
            (
                final_status,
                finished_at,
                json.dumps(report.get("nodes", {}), ensure_ascii=False, default=str),
                json.dumps(report.get("logs", []), ensure_ascii=False, default=str),
                run_id,
            ),
        )
        await db.execute(
            "UPDATE workflows SET last_run_id = ?, updated_at = ? WHERE id = ?",
            (run_id, finished_at, workflow_id),
        )
        await db.commit()
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# 导入
# ---------------------------------------------------------------------------


async def import_workflow(data: dict[str, Any]) -> dict[str, Any]:
    """从 JSON 数据导入工作流

    支持两种格式：
    - 单个工作流 {name, description, nodes, links}
    - 批量导出文件 {workflows: [{...}, ...]}（返回第一个，附 imported_count）
    """
    if isinstance(data.get("workflows"), list):
        created = []
        for item in data["workflows"]:
            if not isinstance(item, dict):
                continue
            wf = await create_workflow(
                name=item.get("name", "导入的工作流"),
                description=item.get("description", ""),
                nodes=item.get("nodes", []),
                links=item.get("links", []),
            )
            created.append(wf)
        if not created:
            raise ValueError("批量导入文件中没有有效的工作流")
        first = created[0]
        first["imported_count"] = len(created)
        return first

    name = data.get("name", "导入的工作流")
    description = data.get("description", "")
    nodes = data.get("nodes", [])
    links = data.get("links", [])
    return await create_workflow(
        name=name, description=description, nodes=nodes, links=links
    )


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
            results.append(
                {
                    "id": f.stem,
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "nodes": data.get("nodes", []),
                    "links": data.get("links", []),
                }
            )
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
    return await create_workflow(
        name=name, description=description, nodes=nodes, links=links
    )


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


# ---------------------------------------------------------------------------
# 节点输出预览（供前端富媒体展示：表格/曲线/指标卡/图片）
# ---------------------------------------------------------------------------


def _df_preview(df, max_rows: int = 200) -> dict[str, Any]:
    """DataFrame → 预览：时间索引的多数值列 → 多线图；否则表格（NaN → None）"""
    import numpy as np
    import pandas as pd

    # 时间索引 + 多数值列 + 足够行数 → 多线图（对齐官网的曲线展现）
    numeric = df.select_dtypes(include=[np.number])
    if (
        1 <= numeric.shape[1] <= 12
        and numeric.shape[0] >= 8
        and _keys_look_like_dates(list(df.index[:5]))
    ):
        x = [str(i)[:10] for i in df.index]
        series = [
            {
                "name": str(c),
                "y": [None if pd.isna(v) else float(v) for v in numeric[c]],
            }
            for c in numeric.columns
        ]
        return {
            "kind": "multiseries",
            "x": x,
            "series": series,
            "shape": [int(df.shape[0]), int(df.shape[1])],
        }

    head = df.head(max_rows).reset_index()
    rows = json.loads(
        head.to_json(orient="records", force_ascii=False, date_format="iso")
    )
    return {
        "kind": "table",
        "columns": [str(c) for c in head.columns],
        "rows": rows,
        "shape": [int(df.shape[0]), int(df.shape[1])],
    }


def _is_number(v: Any) -> bool:
    import numpy as np

    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(
        v, bool
    )


def _keys_look_like_dates(keys: list) -> bool:
    """采样判断 dict 键是否为日期/时间类型（用于识别时间序列）"""
    import pandas as pd

    sample = [str(k) for k in keys[:5]]
    if not sample:
        return False
    for k in sample:
        try:
            pd.to_datetime(k)
        except Exception:
            return False
    return True


def _field_preview(value: Any) -> dict[str, Any]:
    """将单个输出字段转为前端可渲染的预览结构

    kind:
      - table   表格 {columns, rows, shape}
      - series  数值序列 {x, y}（如净值/回撤曲线）
      - metrics 指标字典 {data}
      - image   base64 图片 {data}
      - scalar  标量 {data}
      - json    其他 {data}
    """
    import pandas as pd

    if isinstance(value, pd.DataFrame):
        return _df_preview(value)
    if isinstance(value, pd.Series):
        return _df_preview(value.to_frame())
    if isinstance(value, str):
        if value.startswith("data:image"):
            return {"kind": "image", "data": value}
        return {"kind": "scalar", "data": value}
    if isinstance(value, bool) or _is_number(value):
        return {"kind": "scalar", "data": float(value) if _is_number(value) else value}
    if isinstance(value, dict):
        if not value:
            return {"kind": "json", "data": {}}
        vals = list(value.values())
        # dict of dict → 表格（如 positions）
        if all(isinstance(v, dict) for v in vals):
            try:
                return _df_preview(pd.DataFrame(value).T)
            except Exception:
                pass
        # 纯数值 dict：日期键长序列 → 曲线，否则 → 指标卡/曲线兜底
        if all(_is_number(v) for v in vals):
            keys = list(value.keys())
            if len(value) >= 8 and (_keys_look_like_dates(keys) or len(value) >= 50):
                return {
                    "kind": "series",
                    "x": [str(k) for k in keys],
                    "y": [float(v) for v in vals],
                }
            return {
                "kind": "metrics",
                "data": {str(k): float(v) for k, v in value.items()},
            }
        return {
            "kind": "json",
            "data": json.loads(json.dumps(value, ensure_ascii=False, default=str)),
        }
    if isinstance(value, list):
        if value and all(isinstance(v, dict) for v in value):
            try:
                return _df_preview(pd.DataFrame(value))
            except Exception:
                pass
        # base64 图片列表
        if value and all(
            isinstance(v, str) and v.startswith("data:image") for v in value
        ):
            return {"kind": "images", "data": value[:10]}
        return {
            "kind": "json",
            "data": json.loads(
                json.dumps(value[:500], ensure_ascii=False, default=str)
            ),
        }
    return {"kind": "json", "data": str(value)[:2000]}


async def get_node_output_preview(run_id: str, node_uuid: str) -> dict[str, Any] | None:
    """读取运行产物 pkl，转为逐字段的预览结构；产物不存在返回 None"""
    import pickle

    pkl_path = settings.output_dir / run_id / f"{node_uuid}.pkl"
    if not pkl_path.exists():
        return None
    with open(pkl_path, "rb") as f:
        output: dict[str, Any] = pickle.load(f)
    if not isinstance(output, dict):
        output = {"output": output}

    fields = []
    for key, value in output.items():
        try:
            preview = _field_preview(value)
        except Exception as e:
            preview = {"kind": "json", "data": f"<无法预览: {e}>"}
        preview["name"] = str(key)
        fields.append(preview)

    return {"run_id": run_id, "node_uuid": node_uuid, "fields": fields}
