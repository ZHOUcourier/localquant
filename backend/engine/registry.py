"""节点注册表 - 代理到 plugins/registry.py 的 ALL_WORK_NODES

保持向后兼容：其他模块仍可从 backend.engine.registry 导入 registry。
"""
from typing import Any, Optional, Type

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import ALL_WORK_NODES, get_node_by_name


class NodeRegistry:
    """全局节点注册表（代理到 ALL_WORK_NODES）"""

    def get(self, node_type: str) -> Optional[Type[BaseWorkNode]]:
        """根据类名获取节点类"""
        return get_node_by_name(node_type)

    def list_all(self) -> list[str]:
        """列出所有已注册节点类型名"""
        return list(ALL_WORK_NODES.keys())

    def create_node(self, node_type: str) -> BaseWorkNode:
        """创建节点实例"""
        cls = self.get(node_type)
        if not cls:
            raise ValueError(f"Unknown node type: {node_type}")
        return cls()


# 全局单例（代理到 ALL_WORK_NODES）
registry = NodeRegistry()
