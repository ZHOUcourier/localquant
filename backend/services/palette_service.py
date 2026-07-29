"""节点面板偏好服务 — 节点/类目的隐藏（回收站）与还原

设计：
- 隐藏内置节点/类目不会删除任何代码，只是把它们记入 data/palette_prefs.json，
  插件列表接口返回时过滤掉；回收站可随时还原。
- 自定义节点的"删除"由 custom_node_service 负责（文件移入 trash 目录），
  这里统一汇总为一份回收站清单。
"""

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

_PREFS_PATH = Path("./data/palette_prefs.json")


def _load_prefs() -> dict[str, Any]:
    if _PREFS_PATH.exists():
        try:
            return json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load palette prefs: {e}")
    return {"hidden_nodes": {}, "hidden_groups": {}}


def _save_prefs(prefs: dict[str, Any]) -> None:
    _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PREFS_PATH.write_text(
        json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def hidden_nodes() -> set[str]:
    return set(_load_prefs().get("hidden_nodes", {}).keys())


def hidden_groups() -> set[str]:
    return set(_load_prefs().get("hidden_groups", {}).keys())


def hide_items(nodes: list[dict], groups: list[dict]) -> dict:
    """批量隐藏节点/类目（进入回收站）

    nodes: [{"key": 节点类名, "label": 显示名}]
    groups: [{"key": 分组名}]
    """
    prefs = _load_prefs()
    now = int(time.time())
    for n in nodes:
        key = n.get("key", "")
        if key:
            prefs.setdefault("hidden_nodes", {})[key] = {
                "label": n.get("label", key),
                "deleted_at": now,
            }
    for g in groups:
        key = g.get("key", "")
        if key:
            prefs.setdefault("hidden_groups", {})[key] = {
                "label": g.get("label", key),
                "deleted_at": now,
            }
    _save_prefs(prefs)
    return {
        "hidden_nodes": len(prefs.get("hidden_nodes", {})),
        "hidden_groups": len(prefs.get("hidden_groups", {})),
    }


def restore_items(node_keys: list[str], group_keys: list[str]) -> dict:
    """从回收站还原节点/类目"""
    prefs = _load_prefs()
    for key in node_keys:
        prefs.get("hidden_nodes", {}).pop(key, None)
    for key in group_keys:
        prefs.get("hidden_groups", {}).pop(key, None)
    _save_prefs(prefs)
    return {"restored_nodes": node_keys, "restored_groups": group_keys}


def list_trash() -> list[dict]:
    """回收站清单（隐藏的节点/类目，含隐藏时间）"""
    prefs = _load_prefs()
    items: list[dict] = []
    for key, meta in prefs.get("hidden_groups", {}).items():
        items.append(
            {
                "type": "group",
                "key": key,
                "label": meta.get("label", key),
                "deleted_at": meta.get("deleted_at", 0),
            }
        )
    for key, meta in prefs.get("hidden_nodes", {}).items():
        items.append(
            {
                "type": "node",
                "key": key,
                "label": meta.get("label", key),
                "deleted_at": meta.get("deleted_at", 0),
            }
        )
    items.sort(key=lambda x: -x["deleted_at"])
    return items
