"""插件路由"""
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
