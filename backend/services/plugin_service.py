"""插件服务 - 管理插件列表和动态加载"""

from typing import Any

from backend.plugins.registry import get_all_nodes_grouped
from backend.services import palette_service


def list_plugins() -> dict[str, list[dict[str, Any]]]:
    """列出所有插件，按分组返回（过滤回收站中隐藏的节点/类目）"""
    grouped = get_all_nodes_grouped()
    h_nodes = palette_service.hidden_nodes()
    h_groups = palette_service.hidden_groups()
    result: dict[str, list[dict[str, Any]]] = {}
    for group, nodes in grouped.items():
        if group in h_groups:
            continue
        visible = [n for n in nodes if n["name"] not in h_nodes]
        if visible:
            result[group] = visible
    return result


def get_plugin_schema(name: str) -> dict[str, Any] | None:
    """获取插件 schema"""
    from backend.engine.registry import registry

    meta = registry.get(name)
    if meta:
        instance = meta()
        return instance.get_schema()
    return None
