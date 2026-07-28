"""插件服务 - 管理插件列表和动态加载"""
from typing import Any

from backend.plugins.registry import get_all_nodes_grouped


def list_plugins() -> dict[str, list[dict[str, Any]]]:
    """列出所有插件，按分组返回"""
    return get_all_nodes_grouped()


def get_plugin_schema(name: str) -> dict[str, Any] | None:
    """获取插件 schema"""
    from backend.engine.registry import registry
    meta = registry.get(name)
    if meta:
        instance = meta()
        return instance.get_schema()
    return None
