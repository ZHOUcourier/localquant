"""插件相关 Pydantic 模型"""

from pydantic import BaseModel


class PluginNodeInfo(BaseModel):
    """单个节点信息"""
    name: str
    display_name: str
    group: str
    type: str
    box_color: str
    input_schema: dict | None = None
    output_schema: dict | None = None


class PluginGroupResponse(BaseModel):
    """插件分组响应"""
    groups: dict[str, list[PluginNodeInfo]]
    total_count: int
