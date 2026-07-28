"""自定义节点服务 — 节点代码 fork 与用户自定义节点管理

设计原则（底层代码保护）：
- 用户在前端修改节点代码时，绝不改写内置节点的源文件；
- 而是把修改后的源码在隔离的注册表中执行，取出目标类，
  以新的注册名（原类名 + 随机后缀）注册为一个全新节点；
- 源码 + 元数据持久化到 data/custom_nodes/，重启后由 loader 重新加载。

文件布局：
    data/custom_nodes/{register_name}.py    节点源码
    data/custom_nodes/{register_name}.json  元数据（注册名/基类名/显示名/分组等）
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Type

from loguru import logger

import backend.plugins.registry as reg
from backend.plugins.base import BaseWorkNode

CUSTOM_GROUP = "99-自定义节点"


def _custom_dir() -> Path:
    d = Path("./data/custom_nodes")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _exec_in_isolated_registry(source: str) -> dict[str, Type[BaseWorkNode]]:
    """在隔离注册表中执行源码，返回其中定义的所有 @work_node 类

    通过临时替换 registry 模块的全局 ALL_WORK_NODES，
    保证执行过程不会覆盖/污染真正的全局注册表。
    """
    captured: dict[str, Type[BaseWorkNode]] = {}
    original = reg.ALL_WORK_NODES
    reg.ALL_WORK_NODES = captured
    try:
        namespace: dict[str, Any] = {"__name__": f"custom_node_{uuid.uuid4().hex[:8]}"}
        exec(compile(source, "<custom_node>", "exec"), namespace)
    finally:
        reg.ALL_WORK_NODES = original
    return captured


def _pick_node_class(
    captured: dict[str, Type[BaseWorkNode]], base_name: Optional[str]
) -> Type[BaseWorkNode]:
    """从隔离注册表中挑选目标节点类"""
    if not captured:
        raise ValueError("源码中未找到 @work_node 装饰的节点类")
    if base_name:
        if base_name not in captured:
            raise ValueError(
                f"源码中未找到节点类 {base_name}（不要修改类名，或去掉 base_name 参数）"
            )
        return captured[base_name]
    if len(captured) == 1:
        return next(iter(captured.values()))
    raise ValueError(
        f"源码中包含多个节点类 {list(captured)}，请指定 base_name 或只保留一个节点类"
    )


def _apply_meta(
    cls: Type[BaseWorkNode],
    register_name: str,
    display_name: Optional[str],
    group: Optional[str],
    source_file: Path,
    base_name: Optional[str],
) -> None:
    """将注册名/显示名等元数据绑定到类上"""
    cls.__work_node_name__ = register_name
    if display_name:
        cls.__work_node_display_name__ = display_name
    cls.__work_node_group__ = group or CUSTOM_GROUP
    cls.__work_node_is_custom__ = True
    cls.__work_node_source_file__ = str(source_file)
    cls.__work_node_base_name__ = base_name or ""


def _unique_register_name(base: str) -> str:
    name = f"{base}_c{uuid.uuid4().hex[:6]}"
    while name in reg.ALL_WORK_NODES:
        name = f"{base}_c{uuid.uuid4().hex[:6]}"
    return name


def create_custom_node(
    source: str,
    base_name: Optional[str] = None,
    display_name: Optional[str] = None,
    group: Optional[str] = None,
) -> dict:
    """创建自定义节点（fork 内置节点 或 全新节点），返回节点 schema

    base_name: fork 场景传原节点类名；全新自定义节点可不传（要求源码中恰好一个节点类）
    """
    captured = _exec_in_isolated_registry(source)
    cls = _pick_node_class(captured, base_name)

    register_name = _unique_register_name(cls.__name__)
    d = _custom_dir()
    py_path = d / f"{register_name}.py"

    # fork 时默认显示名加后缀，与原始节点区分
    if not display_name:
        base_display = cls.__work_node_display_name__ or cls.__name__
        display_name = f"{base_display}（改）" if base_name else base_display

    _apply_meta(cls, register_name, display_name, group, py_path, base_name)
    reg.ALL_WORK_NODES[register_name] = cls

    # 持久化源码 + 元数据
    py_path.write_text(source, encoding="utf-8")
    meta = {
        "register_name": register_name,
        "class_name": cls.__name__,
        "base_name": base_name or "",
        "display_name": display_name,
        "group": cls.__work_node_group__,
        "created_at": int(time.time()),
    }
    (d / f"{register_name}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"Custom node created: {register_name} ({display_name})")
    return cls().get_schema()


def update_custom_node(
    register_name: str,
    source: str,
    display_name: Optional[str] = None,
) -> dict:
    """更新已存在的自定义节点源码（保持注册名不变）"""
    d = _custom_dir()
    meta_path = d / f"{register_name}.json"
    if not meta_path.exists() or register_name not in reg.ALL_WORK_NODES:
        raise ValueError(f"自定义节点 {register_name} 不存在")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    captured = _exec_in_isolated_registry(source)
    cls = _pick_node_class(captured, meta.get("class_name") or None)

    py_path = d / f"{register_name}.py"
    final_display = (
        display_name or meta.get("display_name") or cls.__work_node_display_name__
    )
    _apply_meta(
        cls,
        register_name,
        final_display,
        meta.get("group"),
        py_path,
        meta.get("base_name") or None,
    )
    reg.ALL_WORK_NODES[register_name] = cls

    py_path.write_text(source, encoding="utf-8")
    meta["display_name"] = final_display
    meta["updated_at"] = int(time.time())
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"Custom node updated: {register_name}")
    return cls().get_schema()


def delete_custom_node(register_name: str) -> bool:
    """删除自定义节点（注册表 + 磁盘文件）"""
    d = _custom_dir()
    meta_path = d / f"{register_name}.json"
    py_path = d / f"{register_name}.py"
    existed = register_name in reg.ALL_WORK_NODES or meta_path.exists()
    reg.ALL_WORK_NODES.pop(register_name, None)
    if meta_path.exists():
        meta_path.unlink()
    if py_path.exists():
        py_path.unlink()
    if existed:
        logger.info(f"Custom node deleted: {register_name}")
    return existed


def load_persisted_custom_nodes() -> int:
    """启动时加载 data/custom_nodes/ 下持久化的自定义节点（带 .json 元数据的）"""
    d = _custom_dir()
    count = 0
    for meta_path in sorted(d.glob("*.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            register_name = meta["register_name"]
            py_path = d / f"{register_name}.py"
            if not py_path.exists():
                continue
            source = py_path.read_text(encoding="utf-8")
            captured = _exec_in_isolated_registry(source)
            cls = _pick_node_class(captured, meta.get("class_name") or None)
            _apply_meta(
                cls,
                register_name,
                meta.get("display_name"),
                meta.get("group"),
                py_path,
                meta.get("base_name") or None,
            )
            reg.ALL_WORK_NODES[register_name] = cls
            count += 1
        except Exception as e:
            logger.error(f"Failed to load custom node {meta_path.name}: {e}")
    if count:
        logger.info(f"Loaded {count} persisted custom nodes")
    return count
