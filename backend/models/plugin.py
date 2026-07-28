"""插件相关 Pydantic 模型"""
from pydantic import BaseModel
from typing import Optional


class PluginNodeInfo(BaseModel):
    """单个节点信息"""
    name: str
    display_name: str
    group: str
    type: str
    box_color: str
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None


class PluginGroupResponse(BaseModel):
    """插件分组响应"""
    groups: dict[str, list[PluginNodeInfo]]
    total_count: int
