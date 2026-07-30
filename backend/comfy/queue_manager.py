# SPDX-License-Identifier: GPL-3.0-or-later
"""执行队列 — ComfyUI 队列语义（真队列，非即时跑）

- POST /prompt 入队 → 单 worker 顺序消费（与 ComfyUI 一致）
- 执行复用现有 runner 内核（拓扑排序 + _execute_node），节点计算跑在线程池
- 进度经 ws_manager 推送 ComfyUI 协议消息（方案 B.3 映射表）
- 历史保存在内存 + 持久化到 workflow_runs 表（run_id = prompt_id，
  节点产物落 data/outputs/{prompt_id}/，兼容现有产物预览接口）
"""

import asyncio
import json
import time
from collections import OrderedDict
from typing import Any, Optional

from loguru import logger

from backend.comfy.ws import ws_manager
from backend.database import get_db
from backend.engine.context import WorkflowContext
from backend.engine.runner import (
    _consume_cancel,
    _execute_node,
    _save_node_output,
    _topological_sort,
    request_cancel,
)

# 历史最多保留条数（与 ComfyUI MAXIMUM_HISTORY_SIZE 语义一致）
MAX_HISTORY = 10000


class QueueItem:
    """一次入队的执行任务"""

    def __init__(
        self,
        number: int,
        prompt_id: str,
        prompt: dict[str, Any],
        extra_data: dict[str, Any],
        client_id: str | None,
        nodes: list[dict],
        links: list[dict],
    ):
        self.number = number
        self.prompt_id = prompt_id
        self.prompt = prompt
        self.extra_data = extra_data
        self.client_id = client_id
        self.nodes = nodes
        self.links = links

    def outputs_to_execute(self) -> list[str]:
        """输出节点集合：无出边的叶子节点"""
        has_out = {l["previous_node_uuid"] for l in self.links}
        return [n["uuid"] for n in self.nodes if n["uuid"] not in has_out] or [
            n["uuid"] for n in self.nodes
        ]

    def to_queue_tuple(self) -> list:
        """ComfyUI /queue 条目格式 [number, prompt_id, prompt, extra_data, outputs]"""
        return [
            self.number,
            self.prompt_id,
            self.prompt,
            self.extra_data,
            self.outputs_to_execute(),
        ]


def _output_summary(output: dict[str, Any]) -> dict[str, Any]:
    """节点输出 → 轻量 UI 摘要（真实 shape/类型，不做任何模拟渲染）"""
    texts = []
    for key, value in output.items():
        shape = getattr(value, "shape", None)
        if shape is not None:
            texts.append(f"{key}: {type(value).__name__}{tuple(shape)}")
        elif isinstance(value, (dict, list)):
            texts.append(f"{key}: {type(value).__name__}(len={len(value)})")
        else:
            texts.append(f"{key}: {str(value)[:120]}")
    return {"text": texts}


class ComfyQueue:
    """单 worker 顺序执行队列 + 运行历史"""

    def __init__(self) -> None:
        self._pending: list[QueueItem] = []
        self._running: Optional[QueueItem] = None
        self._counter = 0
        self._wakeup = asyncio.Event()
        self._history: "OrderedDict[str, dict]" = OrderedDict()
        self._worker_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # 队列操作
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())

    def enqueue(
        self,
        prompt_id: str,
        prompt: dict,
        extra_data: dict,
        client_id: str | None,
        nodes: list[dict],
        links: list[dict],
    ) -> int:
        self._counter += 1
        item = QueueItem(
            self._counter, prompt_id, prompt, extra_data, client_id, nodes, links
        )
        self._pending.append(item)
        self._wakeup.set()
        return self._counter

    @property
    def queue_remaining(self) -> int:
        return len(self._pending) + (1 if self._running else 0)

    def queue_state(self) -> dict[str, list]:
        return {
            "queue_running": (
                [self._running.to_queue_tuple()] if self._running else []
            ),
            "queue_pending": [i.to_queue_tuple() for i in self._pending],
        }

    def clear_pending(self) -> None:
        self._pending.clear()

    def delete_pending(self, targets: list) -> None:
        wanted = {str(t) for t in targets}
        self._pending = [
            i
            for i in self._pending
            if i.prompt_id not in wanted and str(i.number) not in wanted
        ]

    def interrupt(self) -> None:
        """停止当前运行（节点边界生效，与现有 request_cancel 语义一致）"""
        if self._running:
            request_cancel(self._running.prompt_id)

    # ------------------------------------------------------------------
    # 历史
    # ------------------------------------------------------------------

    def history(self, max_items: int | None = None) -> dict:
        items = list(self._history.items())
        if max_items:
            items = items[-max_items:]
        return dict(items)

    def history_one(self, prompt_id: str) -> dict:
        entry = self._history.get(prompt_id)
        return {prompt_id: entry} if entry else {}

    def clear_history(self) -> None:
        self._history.clear()

    def delete_history(self, targets: list) -> None:
        for t in targets:
            self._history.pop(str(t), None)

    # ------------------------------------------------------------------
    # worker
    # ------------------------------------------------------------------

    async def _worker(self) -> None:
        logger.info("ComfyUI 执行队列 worker 已启动")
        while True:
            if not self._pending:
                self._wakeup.clear()
                await self._send_status()
                await self._wakeup.wait()
            self._running = self._pending.pop(0)
            await self._send_status()
            try:
                await self._execute(self._running)
            except Exception as e:  # 保证 worker 永不退出
                logger.exception(f"队列执行异常: {e}")
            self._running = None

    async def _send_status(self, sid: str | None = None) -> None:
        await ws_manager.send(
            "status",
            {"status": {"exec_info": {"queue_remaining": self.queue_remaining}}},
            sid,
        )

    # ------------------------------------------------------------------
    # 执行一个 prompt（B.3 消息映射）
    # ------------------------------------------------------------------

    async def _execute(self, item: QueueItem) -> None:
        prompt_id = item.prompt_id
        sid = item.client_id
        started_at = int(time.time())
        ctx = WorkflowContext(prompt_id)
        outputs_ui: dict[str, Any] = {}
        messages: list = []
        status_str = "success"
        error_payload: dict | None = None

        def _msg(mtype: str, data: dict) -> dict:
            entry = {**data, "timestamp": int(time.time() * 1000)}
            messages.append([mtype, entry])
            return entry

        await ws_manager.send(
            "execution_start", _msg("execution_start", {"prompt_id": prompt_id}), sid
        )

        try:
            order, link_map = _topological_sort(item.nodes, item.links)
        except ValueError as e:
            error_payload = {
                "prompt_id": prompt_id,
                "node_id": "",
                "node_type": "",
                "executed": [],
                "exception_message": str(e),
                "exception_type": "GraphCycleError",
                "traceback": [],
                "current_inputs": {},
                "current_outputs": {},
            }
            _msg("execution_error", error_payload)
            await ws_manager.send("execution_error", error_payload, sid)
            self._finish(item, "error", messages, outputs_ui)
            await self._persist(item, "failed", started_at, ctx)
            return

        node_map = {n["uuid"]: n for n in item.nodes}
        total = len(order)
        executed: list[str] = []

        for i, node_uuid in enumerate(order):
            if _consume_cancel(prompt_id):
                status_str = "error"
                error_payload = {
                    "prompt_id": prompt_id,
                    "node_id": node_uuid,
                    "node_type": node_map[node_uuid]["name"],
                    "executed": executed,
                    "exception_message": "执行被用户中断",
                    "exception_type": "InterruptProcessingException",
                    "traceback": [],
                    "current_inputs": {},
                    "current_outputs": {},
                }
                _msg("execution_interrupted", error_payload)
                await ws_manager.send("execution_interrupted", error_payload, sid)
                break

            node_def = node_map[node_uuid]
            await ws_manager.send(
                "executing",
                _msg("executing", {"node": node_uuid, "prompt_id": prompt_id}),
                sid,
            )
            # 无节点内进度 → 以 i/n 近似（方案 B.3）
            await ws_manager.send(
                "progress",
                {
                    "value": i + 1,
                    "max": total,
                    "prompt_id": prompt_id,
                    "node": node_uuid,
                },
                sid,
            )

            try:
                incoming = link_map.get(node_uuid, [])
                output = await asyncio.to_thread(_execute_node, node_def, ctx, incoming)
                _save_node_output(prompt_id, node_uuid, output)
                ctx.set_node_output(node_uuid, output)
                executed.append(node_uuid)
                ui_out = _output_summary(output)
                outputs_ui[node_uuid] = ui_out
                await ws_manager.send(
                    "executed",
                    _msg(
                        "executed",
                        {
                            "node": node_uuid,
                            "display_node": node_uuid,
                            "output": ui_out,
                            "prompt_id": prompt_id,
                        },
                    ),
                    sid,
                )
            except Exception as e:
                import traceback as tb

                status_str = "error"
                error_payload = {
                    "prompt_id": prompt_id,
                    "node_id": node_uuid,
                    "node_type": node_def["name"],
                    "executed": executed,
                    "exception_message": str(e),
                    "exception_type": type(e).__name__,
                    "traceback": tb.format_exc().splitlines(),
                    "current_inputs": {},
                    "current_outputs": {},
                }
                _msg("execution_error", error_payload)
                await ws_manager.send("execution_error", error_payload, sid)
                break

        # 整体结束：executing(node=null) + success
        await ws_manager.send("executing", {"node": None, "prompt_id": prompt_id}, sid)
        if status_str == "success":
            await ws_manager.send(
                "execution_success",
                _msg("execution_success", {"prompt_id": prompt_id}),
                sid,
            )

        self._finish(item, status_str, messages, outputs_ui)
        ctx.finish("completed" if status_str == "success" else "failed")
        await self._persist(
            item, "completed" if status_str == "success" else "failed", started_at, ctx
        )
        await self._send_status()

    def _finish(
        self, item: QueueItem, status_str: str, messages: list, outputs: dict
    ) -> None:
        """写入内存历史（ComfyUI /history 条目格式）"""
        self._history[item.prompt_id] = {
            "prompt": item.to_queue_tuple(),
            "outputs": outputs,
            "status": {
                "status_str": status_str,
                "completed": status_str == "success",
                "messages": messages,
            },
        }
        while len(self._history) > MAX_HISTORY:
            self._history.popitem(last=False)

    async def _persist(
        self, item: QueueItem, status: str, started_at: int, ctx: WorkflowContext
    ) -> None:
        """持久化到 workflow_runs（run_id = prompt_id），供运行中心/产物预览复用"""
        workflow_id = str(item.extra_data.get("workflow_id") or "comfy")
        node_outputs = {
            uuid: {"title": n.get("title", ""), "name": n.get("name", "")}
            for n in item.nodes
            if (uuid := n["uuid"]) in ctx.node_outputs
        }
        try:
            db = await get_db()
            try:
                await db.execute(
                    """INSERT OR REPLACE INTO workflow_runs
                       (id, workflow_id, status, started_at, finished_at,
                        node_outputs_json, logs_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.prompt_id,
                        workflow_id,
                        status,
                        started_at,
                        int(time.time()),
                        json.dumps(node_outputs, ensure_ascii=False, default=str),
                        json.dumps(ctx.logs, ensure_ascii=False, default=str),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        except Exception as e:
            logger.warning(f"运行记录持久化失败: {e}")


comfy_queue = ComfyQueue()
