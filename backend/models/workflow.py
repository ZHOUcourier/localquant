"""工作流相关 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional


class WorkNodeModel(BaseModel):
    """工作流节点模型"""
    uuid: str
    name: str  # 对应 BaseWorkNode 子类名
    title: str = ""
    positionX: float = 0
    positionY: float = 0
    width: float = 240
    height: float = 180
    static_input_data: dict = Field(default_factory=dict)
    output_path: Optional[str] = None


class LinkModel(BaseModel):
    """节点连线模型"""
    uuid: str
    previous_node_uuid: str
    input_field_name: str  # 前驱节点的输出字段名
    next_node_uuid: str
    output_field_name: str  # 后继节点的输入字段名


class WorkflowCreate(BaseModel):
    """创建工作流请求"""
    name: str
    description: str = ""
    nodes: list[WorkNodeModel] = Field(default_factory=list)
    links: list[LinkModel] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    """更新工作流请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[list[WorkNodeModel]] = None
    links: Optional[list[LinkModel]] = None


class WorkflowResponse(BaseModel):
    """工作流响应"""
    id: str
    name: str
    description: str
    nodes: list[WorkNodeModel]
    links: list[LinkModel]
    created_at: int
    updated_at: int
    last_run_id: Optional[str] = None

    class Config:
        from_attributes = True


class WorkflowListItem(BaseModel):
    """工作流列表项（简化版）"""
    id: str
    name: str
    description: str
    node_count: int
    created_at: int
    updated_at: int
    last_run_id: Optional[str] = None
