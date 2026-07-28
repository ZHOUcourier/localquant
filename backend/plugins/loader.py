import importlib
import importlib.util
from pathlib import Path

from loguru import logger


def load_all_nodes():
    """加载所有内置节点和自定义节点"""
    # 1. 确保注册表和基类已导入
    from backend.plugins.base import BaseWorkNode
    from backend.plugins.registry import ALL_WORK_NODES

    # 2. 加载内置节点模块
    builtin_modules = [
        "backend.plugins.builtin.data_sources",
        "backend.plugins.builtin.data_processing",
        "backend.plugins.builtin.indicators",
        "backend.plugins.builtin.feature_engineering",
        "backend.plugins.builtin.factor_build",
        "backend.plugins.builtin.factor_analysis",
        "backend.plugins.builtin.backtest",
        "backend.plugins.builtin.output",
        "backend.plugins.builtin.ml_models",
        "backend.plugins.builtin.basic_tools",
        "backend.plugins.builtin.notification",
    ]

    for module_path in builtin_modules:
        try:
            importlib.import_module(module_path)
        except Exception as e:
            logger.warning(f"Failed to load builtin module {module_path}: {e}")

    logger.info(f"Loaded {len(ALL_WORK_NODES)} built-in nodes")

    # 3. 加载持久化的自定义节点（带 .json 元数据，由 custom_node_service 重命名注册）
    from backend.services.custom_node_service import load_persisted_custom_nodes

    load_persisted_custom_nodes()

    # 4. 动态加载遗留的裸 .py 自定义节点（无元数据，直接 exec 自注册）
    custom_dir = Path("./data/custom_nodes")
    if custom_dir.exists():
        for py_file in custom_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            # 有同名 .json 元数据的已在上一步加载
            if py_file.with_suffix(".json").exists():
                continue
            try:
                spec = importlib.util.spec_from_file_location(
                    f"custom_nodes.{py_file.stem}", py_file
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    logger.info(f"Custom node loaded: {py_file.name}")
            except Exception as e:
                logger.error(f"Failed to load custom node {py_file.name}: {e}")

    return ALL_WORK_NODES


def get_custom_nodes() -> list[dict]:
    """获取已加载的自定义节点列表"""
    result = []
    custom_dir = Path("./data/custom_nodes")
    if custom_dir.exists():
        for py_file in custom_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            result.append({"file": py_file.name, "name": py_file.stem})
    return result
