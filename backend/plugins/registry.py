from typing import Optional, Type

from loguru import logger

from backend.plugins.base import BaseWorkNode

# 全局节点注册表
ALL_WORK_NODES: dict[str, Type[BaseWorkNode]] = {}


def work_node(
    name: Optional[str] = None,
    group: str = "99-自定义节点",
    type: str = "general",
    box_color: str = "black",
    description: str = "",
    example: str = "",
    notes: Optional[list[str]] = None,
):
    """装饰器 — 注册工作流节点到全局注册表

    用法：
        @work_node(name="因子构建", group="05-因子构建", box_color="green")
        class FactorBuildNode(BaseWorkNode):
            ...

    example: 典型工作流示例（如 "代码输入 → 因子构建 / 策略回测"）
    notes: 使用注意事项列表（供侧边栏悬停说明与节点详情展示）
    """

    def decorator(cls: Type[BaseWorkNode]) -> Type[BaseWorkNode]:
        if not issubclass(cls, BaseWorkNode):
            raise TypeError(f"{cls.__name__} must inherit from BaseWorkNode")

        cls.__work_node_name__ = cls.__name__
        cls.__work_node_display_name__ = name or cls.__name__
        cls.__work_node_group__ = group
        cls.__work_node_type__ = type
        cls.__work_node_box_color__ = box_color
        cls.__work_node_description__ = description
        cls.__work_node_example__ = example
        cls.__work_node_notes__ = list(notes) if notes else []

        ALL_WORK_NODES[cls.__name__] = cls
        logger.debug(f"Registered node: {cls.__name__} ({name})")
        return cls

    return decorator


def get_node_by_name(name: str) -> Optional[Type[BaseWorkNode]]:
    """根据类名获取节点类"""
    return ALL_WORK_NODES.get(name)


def get_all_nodes_grouped() -> dict[str, list[dict]]:
    """获取所有节点，按分组分类"""
    grouped: dict[str, list[dict]] = {}
    for node_cls in ALL_WORK_NODES.values():
        group = node_cls.__work_node_group__
        if group not in grouped:
            grouped[group] = []
        instance = node_cls()
        grouped[group].append(instance.get_schema())

    # 按分组名排序
    return dict(sorted(grouped.items()))
