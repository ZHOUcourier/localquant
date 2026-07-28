"""插件路由"""

import inspect
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.services import plugin_service

router = APIRouter()


@router.get("/")
async def list_plugins():
    return plugin_service.list_plugins()


@router.get("/{name}/schema")
async def get_plugin_schema(name: str):
    schema = plugin_service.get_plugin_schema(name)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return schema


@router.get("/{name}/source")
async def get_plugin_source(name: str):
    """返回节点的 Python 源文件内容"""
    from backend.plugins.registry import ALL_WORK_NODES

    node_cls = ALL_WORK_NODES.get(name)
    if not node_cls:
        raise HTTPException(status_code=404, detail=f"Node '{name}' not found")
    try:
        file_path = inspect.getfile(node_cls)
        source = Path(file_path).read_text(encoding="utf-8")
        return {
            "source": source,
            "file_path": file_path,
            "node_name": name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取源码: {e}")
