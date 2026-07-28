"""工作流运行器 - 执行 DAG 调度

数据模型（与前端/DB 一致）：
  Node: {uuid, name, title, static_input_data, ...}
  Link: {previous_node_uuid, input_field_name, next_node_uuid, output_field_name}

执行流程：
  1. Kahn 拓扑排序
  2. 逐节点：查找节点类 → 合并输入(static_input_data + 上游输出) → 构造 input_model → 调用 run() → 保存输出
  3. SSE 事件推送（节点开始/完成/失败/整体完成）
"""
import json
import pickle
from typing import Any

from backend.config import settings
from backend.engine.context import WorkflowContext
from backend.plugins.registry import ALL_WORK_NODES


# ---------------------------------------------------------------------------
# 辅助：保存节点输出到文件
# ---------------------------------------------------------------------------

def _save_node_output(run_id: str, node_uuid: str, output: dict[str, Any]) -> str:
    """将节点输出序列化保存到 data/outputs/{run_id}/{node_uuid}.pkl，返回路径"""
    out_dir = settings.output_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{node_uuid}.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(output, f)
    return str(out_path)


# ---------------------------------------------------------------------------
# 拓扑排序（Kahn 算法）
# ---------------------------------------------------------------------------

def _topological_sort(nodes: list[dict], links: list[dict]) -> tuple[list[str], dict[str, list[dict]]]:
    """
    Kahn 拓扑排序

    Returns:
        execution_order: 节点 uuid 列表（拓扑序）
        link_map: {target_uuid: [link, ...]}  入边映射
    Raises:
        ValueError: 存在环
    """
    node_uuids = [n["uuid"] for n in nodes]
    in_degree: dict[str, int] = {uid: 0 for uid in node_uuids}
    dependents: dict[str, list[str]] = {uid: [] for uid in node_uuids}
    link_map: dict[str, list[dict]] = {uid: [] for uid in node_uuids}

    for link in links:
        src = link["previous_node_uuid"]
        tgt = link["next_node_uuid"]
        if src not in in_degree or tgt not in in_degree:
            continue
        in_degree[tgt] += 1
        dependents[src].append(tgt)
        link_map[tgt].append(link)

    queue = [uid for uid, deg in in_degree.items() if deg == 0]
    execution_order: list[str] = []

    while queue:
        uid = queue.pop(0)
        execution_order.append(uid)
        for dep in dependents.get(uid, []):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if len(execution_order) != len(nodes):
        raise ValueError("DAG 存在环，无法执行")

    return execution_order, link_map


# ---------------------------------------------------------------------------
# 单节点执行
# ---------------------------------------------------------------------------

def _execute_node(
    node_def: dict,
    ctx: WorkflowContext,
    incoming_links: list[dict],
) -> dict[str, Any]:
    """
    执行单个节点，返回输出 dict

    node_def: {uuid, name, title, static_input_data, ...}
    """
    node_uuid = node_def["uuid"]
    node_name = node_def["name"]  # 类名，如 "TradingCalendarNode"
    static_input = node_def.get("static_input_data", {}) or {}

    # 1. 查找节点类
    node_cls = ALL_WORK_NODES.get(node_name)
    if node_cls is None:
        raise ValueError(f"未知节点类型: {node_name}")

    # 2. 收集上游输出，按 output_field_name → 上游节点输出的对应字段
    upstream_data: dict[str, Any] = {}
    for link in incoming_links:
        src_uuid = link["previous_node_uuid"]
        src_field = link.get("output_field_name", "")  # 上游输出的字段名
        tgt_field = link.get("input_field_name", "")    # 当前节点的输入字段名
        src_output = ctx.get_node_output(src_uuid)
        if src_output is not None and src_field:
            upstream_data[tgt_field] = src_output.get(src_field)

    # 3. 合并 static_input_data + 上游数据
    merged_input = {**static_input, **upstream_data}

    # 4. 构造 input_model 实例
    input_cls = node_cls.input_model()
    if input_cls is not None:
        try:
            input_obj = input_cls(**merged_input)
        except Exception as e:
            raise ValueError(f"节点 {node_name} 输入构造失败: {e}") from e
    else:
        input_obj = None

    # 5. 创建节点实例并执行
    node_instance = node_cls()
    output_obj = node_instance.run(input_obj)

    # 6. 将输出转为 dict
    if output_obj is None:
        return {}
    if hasattr(output_obj, "model_dump"):
        return output_obj.model_dump()
    if hasattr(output_obj, "dict"):
        return output_obj.dict()
    if isinstance(output_obj, dict):
        return output_obj
    return {}


# ---------------------------------------------------------------------------
# 主入口：run_workflow（同步版本，向后兼容）
# ---------------------------------------------------------------------------

async def run_workflow(run_id: str, nodes: list[dict], links: list[dict]) -> WorkflowContext:
    """
    执行工作流（同步等待全部节点完成后返回 context）

    节点数据格式（与 DB/前端一致）：
      node: {uuid, name, title, static_input_data, ...}
      link: {previous_node_uuid, input_field_name, next_node_uuid, output_field_name}
    """
    ctx = WorkflowContext(run_id)

    if not nodes:
        ctx.finish("completed")
        return ctx

    # 构建节点映射
    node_map: dict[str, dict] = {n["uuid"]: n for n in nodes}

    try:
        execution_order, link_map = _topological_sort(nodes, links)
    except ValueError as e:
        ctx._log(str(e), "error")
        ctx.finish("failed")
        return ctx

    # 按拓扑顺序执行
    for node_uuid in execution_order:
        node_def = node_map[node_uuid]
        node_name = node_def["name"]
        incoming = link_map.get(node_uuid, [])

        # SSE: 节点开始
        await ctx.emit_sse("node_start", {
            "node_uuid": node_uuid,
            "node_name": node_name,
            "status": "running",
            "message": f"开始执行: {node_def.get('title', node_name)}",
        })
        ctx._log(f"开始执行节点: {node_name}", node_uuid=node_uuid)

        try:
            output = _execute_node(node_def, ctx, incoming)

            # 保存输出到文件
            output_path = _save_node_output(run_id, node_uuid, output)
            ctx.set_node_output(node_uuid, output)

            # SSE: 节点完成
            await ctx.emit_sse("node_complete", {
                "node_uuid": node_uuid,
                "node_name": node_name,
                "status": "success",
                "message": f"执行完成: {node_def.get('title', node_name)}",
                "output_path": output_path,
            })
            ctx._log(f"节点完成: {node_name}", node_uuid=node_uuid)

        except Exception as e:
            err_msg = f"节点 {node_name} 执行失败: {e}"
            ctx._log(err_msg, "error", node_uuid=node_uuid)

            # SSE: 节点失败
            await ctx.emit_sse("node_failed", {
                "node_uuid": node_uuid,
                "node_name": node_name,
                "status": "failed",
                "message": err_msg,
            })
            ctx.finish("failed")
            return ctx

    ctx.finish("completed")

    # SSE: 整体完成
    await ctx.emit_sse("workflow_complete", {
        "status": ctx.status,
        "run_id": run_id,
        "message": f"工作流执行完成，共 {len(nodes)} 个节点",
    })

    return ctx


# ---------------------------------------------------------------------------
# SSE 流式版本：run_workflow_stream（生成器，逐节点 yield 事件）
# ---------------------------------------------------------------------------

async def run_workflow_stream(
    run_id: str,
    nodes: list[dict],
    links: list[dict],
):
    """
    流式执行工作流，yield SSE 事件 dict

    供 FastAPI StreamingResponse 使用。
    """
    ctx = WorkflowContext(run_id)

    if not nodes:
        ctx.finish("completed")
        yield _sse_event("workflow_complete", {"status": "completed", "run_id": run_id, "message": "空工作流"})
        return

    node_map: dict[str, dict] = {n["uuid"]: n for n in nodes}

    try:
        execution_order, link_map = _topological_sort(nodes, links)
    except ValueError as e:
        ctx._log(str(e), "error")
        ctx.finish("failed")
        yield _sse_event("workflow_failed", {"status": "failed", "run_id": run_id, "message": str(e)})
        return

    # 发送执行顺序
    yield _sse_event("execution_order", {
        "run_id": run_id,
        "node_uuids": execution_order,
        "total_nodes": len(execution_order),
    })

    for node_uuid in execution_order:
        node_def = node_map[node_uuid]
        node_name = node_def["name"]
        incoming = link_map.get(node_uuid, [])

        yield _sse_event("node_start", {
            "node_uuid": node_uuid,
            "node_name": node_name,
            "status": "running",
            "message": f"开始执行: {node_def.get('title', node_name)}",
        })
        ctx._log(f"开始执行节点: {node_name}", node_uuid=node_uuid)

        try:
            output = _execute_node(node_def, ctx, incoming)
            output_path = _save_node_output(run_id, node_uuid, output)
            ctx.set_node_output(node_uuid, output)

            yield _sse_event("node_complete", {
                "node_uuid": node_uuid,
                "node_name": node_name,
                "status": "success",
                "message": f"执行完成: {node_def.get('title', node_name)}",
                "output_path": output_path,
            })
            ctx._log(f"节点完成: {node_name}", node_uuid=node_uuid)

        except Exception as e:
            err_msg = f"节点 {node_name} 执行失败: {e}"
            ctx._log(err_msg, "error", node_uuid=node_uuid)
            yield _sse_event("node_failed", {
                "node_uuid": node_uuid,
                "node_name": node_name,
                "status": "failed",
                "message": err_msg,
            })
            ctx.finish("failed")
            yield _sse_event("workflow_failed", {
                "status": "failed",
                "run_id": run_id,
                "message": err_msg,
            })
            return

    ctx.finish("completed")
    yield _sse_event("workflow_complete", {
        "status": "completed",
        "run_id": run_id,
        "message": f"工作流执行完成，共 {len(nodes)} 个节点",
    })


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """构造 SSE 格式字符串"""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"
