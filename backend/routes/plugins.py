"""插件路由"""

import inspect
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import custom_node_service, palette_service, plugin_service

router = APIRouter()


class TrashItem(BaseModel):
    type: str  # group | node | custom_node
    key: str
    label: Optional[str] = None


class TrashBatchRequest(BaseModel):
    items: list[TrashItem]


@router.get("/palette/trash")
async def list_palette_trash():
    """回收站清单：隐藏的内置节点/类目 + 删除的自定义节点"""
    items = palette_service.list_trash()
    items.extend(custom_node_service.list_trashed_custom_nodes())
    items.sort(key=lambda x: -x.get("deleted_at", 0))
    return {"items": items}


@router.post("/palette/hide")
async def hide_palette_items(body: TrashBatchRequest):
    """批量隐藏节点/类目（移入回收站）；自定义节点走删除逻辑（文件入回收站）"""
    nodes = [
        {"key": i.key, "label": i.label or i.key}
        for i in body.items
        if i.type == "node"
    ]
    groups = [
        {"key": i.key, "label": i.label or i.key}
        for i in body.items
        if i.type == "group"
    ]
    for i in body.items:
        if i.type == "custom_node":
            custom_node_service.delete_custom_node(i.key)
    palette_service.hide_items(nodes, groups)
    return {"ok": True}


@router.post("/palette/restore")
async def restore_palette_items(body: TrashBatchRequest):
    """从回收站批量还原节点/类目/自定义节点"""
    node_keys = [i.key for i in body.items if i.type == "node"]
    group_keys = [i.key for i in body.items if i.type == "group"]
    palette_service.restore_items(node_keys, group_keys)
    failed = []
    for i in body.items:
        if i.type == "custom_node":
            if not custom_node_service.restore_custom_node(i.key):
                failed.append(i.key)
    return {"ok": True, "failed": failed}


class CustomNodeCreate(BaseModel):
    source: str
    base_name: Optional[str] = None  # fork 时传原节点类名
    display_name: Optional[str] = None
    group: Optional[str] = None


class CustomNodeUpdate(BaseModel):
    source: str
    display_name: Optional[str] = None


class LintRequest(BaseModel):
    source: str


@router.post("/lint")
async def lint_node_code(body: LintRequest):
    """用 ruff 对节点代码做语法/风格检查，返回结构化诊断（供编辑器内联标记）

    运行本地 ruff（stdin 输入），输出 JSON 诊断：
    [{line, column, end_line, end_column, code, message, severity}]
    ruff 不可用时降级为语法编译检查（compile）。
    """
    import ast
    import json as _json
    import os
    import subprocess
    import sys

    source = body.source or ""
    # 先做一次语法编译，捕获硬语法错误（ruff 也会报，但这里给更直接的定位）
    try:
        ast.parse(source)
    except SyntaxError as e:
        return {
            "ok": False,
            "diagnostics": [
                {
                    "line": e.lineno or 1,
                    "column": e.offset or 1,
                    "end_line": e.lineno or 1,
                    "end_column": (e.offset or 1) + 1,
                    "code": "E999",
                    "message": f"语法错误: {e.msg}",
                    "severity": "error",
                }
            ],
        }

    try:
        # 优先用与当前解释器同目录的 ruff（.venv/bin/ruff），避免 PATH 不含 venv
        ruff_bin = os.path.join(os.path.dirname(sys.executable), "ruff")
        if not os.path.exists(ruff_bin):
            ruff_bin = "ruff"
        proc = subprocess.run(
            [
                ruff_bin,
                "check",
                "--output-format",
                "json",
                "--stdin-filename",
                "node.py",
                "-",
            ],
            input=source,
            capture_output=True,
            text=True,
            timeout=15,
        )
        raw = _json.loads(proc.stdout or "[]")
        diagnostics = [
            {
                "line": (d.get("location") or {}).get("row", 1),
                "column": (d.get("location") or {}).get("column", 1),
                "end_line": (d.get("end_location") or {}).get("row", 1),
                "end_column": (d.get("end_location") or {}).get("column", 1),
                "code": d.get("code") or "",
                "message": d.get("message") or "",
                "severity": "error"
                if str(d.get("code") or "").startswith("E")
                else "warning",
            }
            for d in raw
        ]
        return {"ok": len(diagnostics) == 0, "diagnostics": diagnostics}
    except FileNotFoundError:
        return {"ok": True, "diagnostics": [], "note": "ruff 未安装，仅做了语法检查"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"代码检查失败: {e}")


@router.get("/")
async def list_plugins():
    return plugin_service.list_plugins()


@router.post("/custom")
async def create_custom_node(body: CustomNodeCreate):
    """创建自定义节点（fork 内置节点 或 全新节点），不修改原节点源码"""
    try:
        return custom_node_service.create_custom_node(
            source=body.source,
            base_name=body.base_name,
            display_name=body.display_name,
            group=body.group,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"节点代码执行失败: {e}")


@router.put("/custom/{name}")
async def update_custom_node(name: str, body: CustomNodeUpdate):
    """更新自定义节点源码（保持注册名不变）"""
    try:
        return custom_node_service.update_custom_node(
            name, source=body.source, display_name=body.display_name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"节点代码执行失败: {e}")


@router.delete("/custom/{name}")
async def delete_custom_node(name: str):
    """删除自定义节点"""
    ok = custom_node_service.delete_custom_node(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"自定义节点 '{name}' 不存在")
    return {"ok": True}


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
        # 自定义/fork 节点：直接读持久化的源码文件
        custom_file = getattr(node_cls, "__work_node_source_file__", "")
        if custom_file and Path(custom_file).exists():
            file_path = custom_file
        else:
            file_path = inspect.getfile(node_cls)
        source = Path(file_path).read_text(encoding="utf-8")
        return {
            "source": source,
            "file_path": file_path,
            "node_name": name,
            "is_custom": bool(getattr(node_cls, "__work_node_is_custom__", False)),
            "class_name": node_cls.__name__,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法读取源码: {e}")
