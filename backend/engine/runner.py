"""工作流运行器 - 执行 DAG 调度

数据模型（与前端/DB 一致）：
  Node: {uuid, name, title, static_input_data, ...}
  Link: {previous_node_uuid, input_field_name, next_node_uuid, output_field_name}

执行流程：
  1. Kahn 拓扑排序
  2. 逐节点：查找节点类 → 合并输入(static_input_data + 上游输出) → 构造 input_model → 调用 run() → 保存输出
  3. SSE 事件推送（节点开始/完成/失败/整体完成）
"""

import asyncio
import hashlib
import json
import pickle
import time
from datetime import datetime
from typing import Any

from loguru import logger

from backend.config import settings
from backend.engine.context import WorkflowContext
from backend.plugins.registry import ALL_WORK_NODES

# ---------------------------------------------------------------------------
# 运行取消：request_cancel(run_id) 后，流式执行在下一个节点边界终止
# （节点内部为同步计算，无法中途打断，与 ComfyUI 的 Interrupt 语义一致）
# ---------------------------------------------------------------------------

CANCELLED_RUNS: set[str] = set()

# 节点级输出缓存目录：跨运行复用（cache_key = 节点类名+参数+上游输出内容哈希）
_NODE_CACHE_DIR = settings.output_dir / "_node_cache"


def request_cancel(run_id: str) -> None:
    """标记某次运行请求取消"""
    CANCELLED_RUNS.add(run_id)


def _consume_cancel(run_id: str) -> bool:
    """检查并消费取消标记"""
    if run_id in CANCELLED_RUNS:
        CANCELLED_RUNS.discard(run_id)
        return True
    return False


# ---------------------------------------------------------------------------
# 节点级输出缓存（对标 ComfyUI 输出复用）
# ---------------------------------------------------------------------------


def _stable_hash(obj: Any) -> str:
    """对任意对象求稳定哈希：优先 JSON（顺序无关），回退 pickle"""
    try:
        payload = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
        data = payload.encode("utf-8")
    except Exception:
        try:
            data = pickle.dumps(obj)
        except Exception:
            data = repr(obj).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _compute_cache_key(node_name: str, merged_input: dict[str, Any]) -> str:
    """节点缓存键 = 节点类名 + 合并输入（含静态参数与上游输出）的内容哈希

    合并输入已包含代码/公式文本（在 static_input_data 中）与上游输出内容，
    故代码类节点改代码即失效、上游变化即失效。
    """
    parts: list[str] = [node_name]
    for key in sorted(merged_input.keys()):
        val = merged_input[key]
        if hasattr(val, "to_parquet"):  # DataFrame/Series：按内容 pickle 哈希
            try:
                parts.append(f"{key}={hashlib.sha256(pickle.dumps(val)).hexdigest()}")
                continue
            except Exception:
                pass
        parts.append(f"{key}={_stable_hash(val)}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _cache_load(cache_key: str) -> dict[str, Any] | None:
    """命中则加载缓存输出，否则 None"""
    path = _NODE_CACHE_DIR / f"{cache_key}.pkl"
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning(f"节点缓存读取失败 {path}: {e}")
        return None


def _cache_store(cache_key: str, output: dict[str, Any]) -> None:
    """存储节点输出到缓存"""
    _NODE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(_NODE_CACHE_DIR / f"{cache_key}.pkl", "wb") as f:
            pickle.dump(output, f)
    except Exception as e:
        logger.warning(f"节点缓存写入失败: {e}")


def clear_node_cache() -> int:
    """清空节点缓存，返回删除文件数"""
    if not _NODE_CACHE_DIR.exists():
        return 0
    n = 0
    for f in _NODE_CACHE_DIR.glob("*.pkl"):
        try:
            f.unlink()
            n += 1
        except Exception:
            pass
    return n


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


def _topological_sort(
    nodes: list[dict], links: list[dict]
) -> tuple[list[str], dict[str, list[dict]]]:
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


def _merge_node_input(
    node_def: dict,
    ctx: WorkflowContext,
    incoming_links: list[dict],
) -> tuple[str, dict[str, Any]]:
    """合并节点输入（static_input_data + 上游输出），返回 (节点类名, merged_input)"""
    node_name = node_def["name"]
    static_input = node_def.get("static_input_data", {}) or {}
    upstream_data: dict[str, Any] = {}
    for link in incoming_links:
        src_uuid = link["previous_node_uuid"]
        src_field = link.get("output_field_name", "")
        tgt_field = link.get("input_field_name", "")
        src_output = ctx.get_node_output(src_uuid)
        if src_output is not None and src_field:
            upstream_data[tgt_field] = src_output.get(src_field)
    return node_name, {**static_input, **upstream_data}


def _run_node(node_name: str, merged_input: dict[str, Any]) -> dict[str, Any]:
    """构造输入模型并执行节点，返回输出 dict"""
    node_cls = ALL_WORK_NODES.get(node_name)
    if node_cls is None:
        raise ValueError(f"未知节点类型: {node_name}")

    input_cls = node_cls.input_model()
    if input_cls is not None:
        try:
            input_obj = input_cls(**merged_input)
        except Exception as e:
            raise ValueError(f"节点 {node_name} 输入构造失败: {e}") from e
    else:
        input_obj = None

    node_instance = node_cls()
    output_obj = node_instance.run(input_obj)

    if output_obj is None:
        return {}
    if hasattr(output_obj, "model_dump"):
        return output_obj.model_dump()
    if hasattr(output_obj, "dict"):
        return output_obj.dict()
    if isinstance(output_obj, dict):
        return output_obj
    return {}


def _execute_node(
    node_def: dict,
    ctx: WorkflowContext,
    incoming_links: list[dict],
) -> dict[str, Any]:
    """执行单个节点（无缓存，向后兼容），返回输出 dict"""
    node_name, merged_input = _merge_node_input(node_def, ctx, incoming_links)
    return _run_node(node_name, merged_input)


# ---------------------------------------------------------------------------
# 主入口：run_workflow（同步版本，向后兼容）
# ---------------------------------------------------------------------------


async def run_workflow(
    run_id: str, nodes: list[dict], links: list[dict], use_cache: bool = False
) -> WorkflowContext:
    """
    执行工作流（同步等待全部节点完成后返回 context）

    节点数据格式（与 DB/前端一致）：
      node: {uuid, name, title, static_input_data, ...}
      link: {previous_node_uuid, input_field_name, next_node_uuid, output_field_name}
    use_cache: 是否启用节点级输出缓存（参数扫描时开启，共同上游只算一次）。
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
        await ctx.emit_sse(
            "node_start",
            {
                "node_uuid": node_uuid,
                "node_name": node_name,
                "status": "running",
                "message": f"开始执行: {node_def.get('title', node_name)}",
            },
        )
        ctx._log(f"开始执行节点: {node_name}", node_uuid=node_uuid)

        try:
            node_name_cls, merged_input = _merge_node_input(node_def, ctx, incoming)
            cache_key = (
                _compute_cache_key(node_name_cls, merged_input) if use_cache else ""
            )
            cached = _cache_load(cache_key) if cache_key else None
            if cached is not None:
                output = cached
            else:
                # 节点计算放线程池，避免慢节点阻塞事件循环（与 Comfy 队列 worker 对齐）
                output = await asyncio.to_thread(_run_node, node_name_cls, merged_input)
                if cache_key:
                    _cache_store(cache_key, output)

            # 保存输出到文件
            output_path = _save_node_output(run_id, node_uuid, output)
            ctx.set_node_output(node_uuid, output)

            # SSE: 节点完成
            await ctx.emit_sse(
                "node_complete",
                {
                    "node_uuid": node_uuid,
                    "node_name": node_name,
                    "status": "success",
                    "message": f"执行完成: {node_def.get('title', node_name)}",
                    "output_path": output_path,
                },
            )
            ctx._log(f"节点完成: {node_name}", node_uuid=node_uuid)

        except Exception as e:
            err_msg = f"节点 {node_name} 执行失败: {e}"
            ctx._log(err_msg, "error", node_uuid=node_uuid)

            # SSE: 节点失败
            await ctx.emit_sse(
                "node_failed",
                {
                    "node_uuid": node_uuid,
                    "node_name": node_name,
                    "status": "failed",
                    "message": err_msg,
                },
            )
            ctx.finish("failed")
            return ctx

    ctx.finish("completed")

    # SSE: 整体完成
    await ctx.emit_sse(
        "workflow_complete",
        {
            "status": ctx.status,
            "run_id": run_id,
            "message": f"工作流执行完成，共 {len(nodes)} 个节点",
        },
    )

    return ctx


# ---------------------------------------------------------------------------
# SSE 流式版本：run_workflow_stream（生成器，逐节点 yield 事件）
# ---------------------------------------------------------------------------


async def run_workflow_stream(
    run_id: str,
    nodes: list[dict],
    links: list[dict],
    report: dict[str, Any] | None = None,
    use_cache: bool = True,
):
    """
    流式执行工作流，yield SSE 事件 dict

    供 FastAPI StreamingResponse 使用。
    report: 可选的可变字典，执行过程中回填 status/logs/nodes（含每节点耗时），
            供调用方在流结束后持久化运行历史。
    use_cache: 是否启用节点级输出缓存（命中则跳过执行，事件标记 cached=True）。
    """
    ctx = WorkflowContext(run_id)
    if report is None:
        report = {}
    report.setdefault("status", "running")
    node_reports: dict[str, dict[str, Any]] = {}
    report["nodes"] = node_reports
    report["logs"] = ctx.logs

    if not nodes:
        ctx.finish("completed")
        report["status"] = "completed"
        yield _sse_event(
            "workflow_complete",
            {"status": "completed", "run_id": run_id, "message": "空工作流"},
        )
        return

    node_map: dict[str, dict] = {n["uuid"]: n for n in nodes}

    try:
        execution_order, link_map = _topological_sort(nodes, links)
    except ValueError as e:
        ctx._log(str(e), "error")
        ctx.finish("failed")
        report["status"] = "failed"
        yield _sse_event(
            "workflow_failed", {"status": "failed", "run_id": run_id, "message": str(e)}
        )
        return

    # 发送执行顺序
    yield _sse_event(
        "execution_order",
        {
            "run_id": run_id,
            "node_uuids": execution_order,
            "total_nodes": len(execution_order),
        },
    )

    for node_uuid in execution_order:
        # 节点边界检查取消请求（前端「停止」按钮 → POST cancel）
        if _consume_cancel(run_id):
            msg = "运行已被用户取消"
            ctx._log(msg, "warning")
            ctx.finish("cancelled")
            report["status"] = "cancelled"
            yield _sse_event(
                "workflow_cancelled",
                {"status": "cancelled", "run_id": run_id, "message": msg},
            )
            return

        node_def = node_map[node_uuid]
        node_name = node_def["name"]
        node_title = node_def.get("title", node_name)
        incoming = link_map.get(node_uuid, [])

        yield _sse_event(
            "node_start",
            {
                "node_uuid": node_uuid,
                "node_name": node_name,
                "status": "running",
                "message": f"开始执行: {node_title}",
            },
        )
        ctx._log(f"开始执行节点: {node_name}", node_uuid=node_uuid)
        started = time.perf_counter()

        try:
            node_name_cls, merged_input = _merge_node_input(node_def, ctx, incoming)
            cache_key = (
                _compute_cache_key(node_name_cls, merged_input) if use_cache else ""
            )
            cached = _cache_load(cache_key) if cache_key else None
            if cached is not None:
                output = cached
                is_cached = True
            else:
                # 节点计算放线程池，避免慢节点阻塞事件循环与中断响应
                output = await asyncio.to_thread(_run_node, node_name_cls, merged_input)
                is_cached = False
                if cache_key:
                    _cache_store(cache_key, output)
            output_path = _save_node_output(run_id, node_uuid, output)
            ctx.set_node_output(node_uuid, output)
            duration_ms = int((time.perf_counter() - started) * 1000)
            node_reports[node_uuid] = {
                "title": node_title,
                "name": node_name,
                "status": "success",
                "duration_ms": duration_ms,
                "output_path": output_path,
                "cached": is_cached,
            }

            suffix = "（缓存命中）" if is_cached else f"（{duration_ms / 1000:.2f}s）"
            yield _sse_event(
                "node_complete",
                {
                    "node_uuid": node_uuid,
                    "node_name": node_name,
                    "status": "success",
                    "message": f"执行完成: {node_title}{suffix}",
                    "output_path": output_path,
                    "duration_ms": duration_ms,
                    "cached": is_cached,
                },
            )
            ctx._log(
                f"节点完成: {node_name}（{duration_ms}ms{'，缓存命中' if is_cached else ''}）",
                node_uuid=node_uuid,
            )

        except Exception as e:
            duration_ms = int((time.perf_counter() - started) * 1000)
            err_msg = f"节点 {node_name} 执行失败: {e}"
            ctx._log(err_msg, "error", node_uuid=node_uuid)
            node_reports[node_uuid] = {
                "title": node_title,
                "name": node_name,
                "status": "failed",
                "duration_ms": duration_ms,
                "error": str(e),
            }
            yield _sse_event(
                "node_failed",
                {
                    "node_uuid": node_uuid,
                    "node_name": node_name,
                    "status": "failed",
                    "message": err_msg,
                    "duration_ms": duration_ms,
                },
            )
            ctx.finish("failed")
            report["status"] = "failed"
            yield _sse_event(
                "workflow_failed",
                {
                    "status": "failed",
                    "run_id": run_id,
                    "message": err_msg,
                },
            )
            return

    ctx.finish("completed")
    report["status"] = "completed"
    yield _sse_event(
        "workflow_complete",
        {
            "status": "completed",
            "run_id": run_id,
            "message": f"工作流执行完成，共 {len(nodes)} 个节点",
        },
    )


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """构造 SSE 格式字符串（自动附加时间戳与日志级别，供前端筛选/排序）"""
    data.setdefault("timestamp", datetime.now().isoformat())
    if "level" not in data:
        status = data.get("status", "")
        data["level"] = "error" if status == "failed" else "info" if status else "info"
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"
