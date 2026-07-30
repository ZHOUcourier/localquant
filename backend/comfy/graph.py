# SPDX-License-Identifier: GPL-3.0-or-later
"""图格式转换 — ComfyUI API(prompt) 格式 → runner nodes/links

ComfyUI API 格式：
  { "<node_id>": { "class_type": "...",
                   "inputs": { 字段: 字面值 或 [上游node_id, 输出索引] },
                   "_meta": {"title": "..."} } }

runner 格式（与 DB/现有引擎一致）：
  node: {uuid, name, title, static_input_data}
  link: {previous_node_uuid, output_field_name, next_node_uuid, input_field_name}

关键点（方案 B.2）：ComfyUI 连线使用**输出索引**，须经 RETURN_NAMES
（= output_model 字段顺序）映射回 localquant 的 output_field_name。
"""

from typing import Any

from backend.comfy.adapter import get_return_names
from backend.plugins.registry import ALL_WORK_NODES


class PromptConversionError(Exception):
    """图转换失败，携带 ComfyUI node_errors 结构"""

    def __init__(self, message: str, node_errors: dict[str, Any] | None = None):
        super().__init__(message)
        self.node_errors = node_errors or {}


def _is_link(value: Any) -> bool:
    """[node_id, output_index] 形态即为连线"""
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    )


def convert_prompt(prompt: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """API prompt → (nodes, links)；类型未知/索引越界时抛 PromptConversionError"""
    nodes: list[dict] = []
    links: list[dict] = []
    node_errors: dict[str, Any] = {}

    for node_id, node_data in prompt.items():
        if not isinstance(node_data, dict) or "class_type" not in node_data:
            continue
        class_type = node_data["class_type"]
        if class_type not in ALL_WORK_NODES:
            node_errors[str(node_id)] = {
                "errors": [
                    {
                        "type": "invalid_prompt",
                        "message": f"未知节点类型: {class_type}",
                        "details": "",
                        "extra_info": {},
                    }
                ],
                "class_type": class_type,
                "dependent_outputs": [],
            }
            continue

        title = (node_data.get("_meta") or {}).get("title") or class_type
        static_input: dict[str, Any] = {}

        for field, value in (node_data.get("inputs") or {}).items():
            if _is_link(value):
                src_id, out_idx = str(value[0]), int(value[1])
                src_class = (prompt.get(src_id) or {}).get("class_type", "")
                return_names = get_return_names(src_class)
                if out_idx >= len(return_names):
                    node_errors[str(node_id)] = {
                        "errors": [
                            {
                                "type": "invalid_prompt",
                                "message": (
                                    f"连线输出索引越界: {src_class}[{out_idx}]"
                                ),
                                "details": field,
                                "extra_info": {},
                            }
                        ],
                        "class_type": class_type,
                        "dependent_outputs": [],
                    }
                    continue
                links.append(
                    {
                        "previous_node_uuid": src_id,
                        "output_field_name": return_names[out_idx],
                        "next_node_uuid": str(node_id),
                        "input_field_name": field,
                    }
                )
            else:
                static_input[field] = value

        nodes.append(
            {
                "uuid": str(node_id),
                "name": class_type,
                "title": title,
                "static_input_data": static_input,
            }
        )

    if node_errors:
        raise PromptConversionError("prompt 校验失败", node_errors)

    return nodes, links
