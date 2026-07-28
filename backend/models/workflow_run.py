"""工作流运行记录 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional


class WorkflowRunResponse(BaseModel):
    """工作流运行记录"""
    id: str
    workflow_id: str
    status: str  # pending/running/success/failed
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    node_outputs: dict = Field(default_factory=dict)  # {node_uuid: output_path}
    logs: list[dict] = Field(default_factory=list)  # [{node_uuid, level, message, timestamp}]

    class Config:
        from_attributes = True


class NodeExecutionStatus(BaseModel):
    """节点执行状态（SSE 推送用）"""
    node_uuid: str
    status: str  # pending/running/success/failed
    message: str = ""
    output_path: Optional[str] = None
