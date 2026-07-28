"""Pydantic 模型定义"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# ========== 工作流相关（统一使用前端格式） ==========


class NodeModel(BaseModel):
    """工作流节点模型（与前端一致）"""

    uuid: str
    name: str  # 对应 BaseWorkNode 子类名
    title: str = ""
    positionX: float = 0
    positionY: float = 0
    width: float = 240
    height: float = 180
    static_input_data: dict[str, Any] = Field(default_factory=dict)
    output_path: Optional[str] = None


class LinkModel(BaseModel):
    """节点连线模型（与前端一致）"""

    uuid: str = ""
    previous_node_uuid: str
    output_field_name: str  # 前驱节点的输出字段名
    next_node_uuid: str
    input_field_name: str  # 后继节点的输入字段名


class WorkflowCreate(BaseModel):
    id: Optional[str] = None  # 有 id 时为更新，无 id 时为创建
    name: str
    description: str = ""
    is_favorite: bool = False
    nodes: list[NodeModel] = Field(default_factory=list)
    links: list[LinkModel] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[list[NodeModel]] = None
    links: Optional[list[LinkModel]] = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    nodes: list[NodeModel]
    links: list[LinkModel]
    created_at: int
    updated_at: int
    last_run_id: Optional[str] = None
    is_favorite: bool = False


class WorkflowListItem(BaseModel):
    id: str
    name: str
    description: str
    updated_at: int
    is_favorite: bool = False


# ========== 运行记录相关 ==========


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    logs: list[dict[str, Any]] = Field(default_factory=list)


# ========== 插件相关 ==========


class SlotSchema(BaseModel):
    name: str
    type: str


class PluginMeta(BaseModel):
    type: str
    name: str
    display: str
    category: str
    inputs: list[SlotSchema] = Field(default_factory=list)
    outputs: list[SlotSchema] = Field(default_factory=list)
    params: list[dict[str, Any]] = Field(default_factory=list)
    description: str = ""


class PluginListResponse(BaseModel):
    builtins: list[PluginMeta]
    customs: list[PluginMeta]


# ========== 运行请求 ==========


class RunRequest(BaseModel):
    nodes: list[NodeModel] = Field(default_factory=list)
    links: list[LinkModel] = Field(default_factory=list)


# ========== SSE 事件 ==========


class NodeExecutionStatus(BaseModel):
    """节点执行状态（SSE 推送用）"""

    node_uuid: str
    status: str  # pending/running/success/failed
    message: str = ""
    output_path: Optional[str] = None
