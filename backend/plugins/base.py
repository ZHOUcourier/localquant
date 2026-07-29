from abc import ABC, abstractmethod
from typing import Optional, Type

from pydantic import BaseModel


class BaseWorkNode(ABC):
    """工作流节点抽象基类 — 复刻 panda_quantflow 的 BaseWorkNode"""

    # 类属性（由 @work_node 装饰器设置）
    __work_node_name__: str = ""  # 类名，内部标识
    __work_node_display_name__: str = ""  # 显示名称
    __work_node_group__: str = ""  # 分组（如 "01-数据获取"）
    __work_node_type__: str = "general"  # 节点类型
    __work_node_box_color__: str = "black"  # 节点颜色标识
    __work_node_description__: str = ""  # 节点描述
    __work_node_example__: str = ""  # 典型工作流示例
    __work_node_notes__: list = []  # 使用注意事项
    __work_node_is_custom__: bool = False  # 是否为自定义/fork 节点
    __work_node_source_file__: str = ""  # 自定义节点的源码文件路径
    __work_node_base_name__: str = ""  # fork 来源节点类名

    @classmethod
    @abstractmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        """返回定义节点输入的 Pydantic Model 类"""
        ...

    @classmethod
    @abstractmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        """返回定义节点输出的 Pydantic Model 类"""
        ...

    @abstractmethod
    def run(self, input: BaseModel) -> Optional[BaseModel]:
        """执行节点逻辑"""
        ...

    def get_schema(self) -> dict:
        """返回节点的完整 schema（供前端使用）"""
        input_cls = self.input_model()
        output_cls = self.output_model()
        return {
            "name": self.__work_node_name__,
            "display_name": self.__work_node_display_name__,
            "group": self.__work_node_group__,
            "type_name": self.__work_node_type__,
            "description": self.__work_node_description__,
            "example": self.__work_node_example__,
            "notes": self.__work_node_notes__,
            "box_color": self.__work_node_box_color__,
            "is_custom": self.__work_node_is_custom__,
            "base_name": self.__work_node_base_name__,
            "input_schema": _safe_json_schema(input_cls) if input_cls else None,
            "output_schema": _safe_json_schema(output_cls) if output_cls else None,
        }


def _safe_json_schema(model_cls: type) -> dict:
    """安全生成 JSON schema，跳过无法序列化的字段（如 pd.DataFrame）"""
    try:
        return model_cls.model_json_schema()
    except Exception:
        # 回退：手动构建 schema，跳过不可序列化字段
        schema = {"type": "object", "properties": {}, "title": model_cls.__name__}
        for name, field in model_cls.model_fields.items():
            try:
                field_schema = field.annotation
                # 对基本类型做简单映射
                type_map = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                }
                if field.annotation in type_map:
                    schema["properties"][name] = {"type": type_map[field.annotation]}
                else:
                    schema["properties"][name] = {
                        "type": "object",
                        "description": "non-serializable",
                    }
            except Exception:
                schema["properties"][name] = {
                    "type": "object",
                    "description": "non-serializable",
                }
        return schema
