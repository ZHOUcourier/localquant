"""运行上下文 - 管理工作流执行状态 + SSE 事件推送"""
import asyncio
import json
import time
from typing import Any, Optional

from loguru import logger


class WorkflowContext:
    """工作流运行上下文

    支持：
    - 节点输入/输出管理
    - 日志记录
    - SSE 事件队列（供前端实时进度推送）
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.started_at = int(time.time())
        self.node_outputs: dict[str, dict[str, Any]] = {}
        self.logs: list[dict[str, Any]] = []
        self.status = "running"
        self._pending_inputs: dict[str, dict[str, Any]] = {}
        # SSE 事件队列（asyncio.Queue）
        self._sse_queue: Optional[asyncio.Queue] = None

    def attach_sse_queue(self, queue: asyncio.Queue):
        """绑定 SSE 事件队列"""
        self._sse_queue = queue

    async def emit_sse(self, event_type: str, data: dict[str, Any]):
        """推送一条 SSE 事件"""
        if self._sse_queue is not None:
            payload = {"event": event_type, "data": data}
            await self._sse_queue.put(payload)

    # ------------------------------------------------------------------
    # 节点输入/输出
    # ------------------------------------------------------------------

    def set_node_output(self, node_uuid: str, output: dict[str, Any]):
        """设置节点输出"""
        self.node_outputs[node_uuid] = output
        self._log(f"Node {node_uuid} output saved")

    def get_node_output(self, node_uuid: str) -> Optional[dict[str, Any]]:
        """获取节点输出"""
        return self.node_outputs.get(node_uuid)

    def get_input(self, node_uuid: str, slot: str) -> Any:
        """获取节点某个 slot 的输入（来自上游节点输出）"""
        return self._pending_inputs.get(node_uuid, {}).get(slot)

    def set_pending_inputs(self, node_uuid: str, inputs: dict[str, Any]):
        """设置节点待执行的输入（由 runner 在执行前调用）"""
        self._pending_inputs[node_uuid] = inputs

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def _log(self, message: str, level: str = "info", node_uuid: str = ""):
        """添加日志"""
        entry = {
            "time": int(time.time()),
            "level": level,
            "message": message,
            "node_uuid": node_uuid,
        }
        self.logs.append(entry)
        getattr(logger, level if level in ("debug", "info", "warning", "error") else "info")(
            f"[Run {self.run_id}] {message}"
        )

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def finish(self, status: str = "completed"):
        """标记运行完成（同步版本，向后兼容）"""
        self.status = status
        self._log(f"Workflow run {status}")
