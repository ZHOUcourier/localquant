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

# ComfyUI 前端会为其建 widget 的输入类型；其余（DATAFRAME/DICT/SERIES/...）为连线槽
_WIDGET_TYPES = ("STRING", "INT", "FLOAT", "BOOLEAN")


def _is_widget_type(spec_type: Any) -> bool:
    """combobox（options 列表）或标量类型 → 前端渲染为 widget"""
    return isinstance(spec_type, list) or spec_type in _WIDGET_TYPES


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
            # 仅当列表同时命中源节点存在时才按连线处理，避免字面量 [a,b] 被误判
            if _is_link(value) and str(value[0]) in prompt:
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


def workflow_to_comfy_graph(nodes: list[dict], links: list[dict]) -> dict:
    """localquant 工作流（nodes/links）→ ComfyUI 前端图 JSON（供 app.loadGraphData 加载）

    是 convert_prompt 的逆向：打开已保存工作流时编辑器 iframe 借此还原画布。

    widget 值不按位置写入 widgets_values（分析节点带 serialize=false 的按钮
    widget，位置会错位），而是随 properties.localquant_static_input 下发，
    由前端扩展在加载后按字段名回填 widget 值。

    槽位判定与前端建槽规则一致：
      连线槽 = optional 中非 widget 类型（DATAFRAME/DICT/SERIES/...），定义序即槽位序；
      output 槽位 = output_name 顺序（即 get_return_names 索引）。
    """
    from backend.comfy.adapter import node_to_object_info

    node_list = [dict(n) for n in nodes]
    id_map = {str(n["uuid"]): i + 1 for i, n in enumerate(node_list)}
    if len(id_map) != len(node_list):
        raise ValueError("节点 uuid 存在重复")

    infos: dict[str, dict] = {}
    for n in node_list:
        cls = str(n["name"])
        if cls not in ALL_WORK_NODES:
            raise ValueError(f"未知节点类型: {cls}")
        infos[cls] = node_to_object_info(ALL_WORK_NODES[cls])

    comfy_nodes: list[dict] = []
    link_slot_fields: dict[str, list[str]] = {}
    for n in node_list:
        cls = str(n["name"])
        info = infos[cls]
        optional = info["input"]["optional"]
        slot_fields = [f for f, (t, _e) in optional.items() if not _is_widget_type(t)]
        link_slot_fields[str(n["uuid"])] = slot_fields

        inputs_slots = [
            {"name": f, "type": optional[f][0], "link": None} for f in slot_fields
        ]
        outputs_slots = [
            {"name": name_, "type": t, "links": [], "slot_index": i}
            for i, (name_, t) in enumerate(
                zip(info["output_name"], info["output"])
            )
        ]
        comfy_nodes.append(
            {
                "id": id_map[str(n["uuid"])],
                "type": cls,
                "title": str(n.get("title") or cls),
                "pos": [float(n.get("positionX", 0)), float(n.get("positionY", 0))],
                "size": [float(n.get("width", 240)), float(n.get("height", 180))],
                "flags": {},
                "order": 0,
                "mode": 0,
                "inputs": inputs_slots,
                "outputs": outputs_slots,
                "properties": {"localquant_static_input": dict(n.get("static_input_data") or {})},
            }
        )

    node_by_uuid = {str(n["uuid"]): n for n in node_list}
    comfy_links: list[list] = []
    for i, l in enumerate(links, start=1):
        src = str(l["previous_node_uuid"])
        dst = str(l["next_node_uuid"])
        if src not in node_by_uuid or dst not in node_by_uuid:
            raise ValueError(f"连线引用了不存在的节点: {l}")
        src_cls = str(node_by_uuid[src]["name"])
        dst_cls = str(node_by_uuid[dst]["name"])
        return_names = get_return_names(src_cls)
        out_field = str(l["output_field_name"])
        if out_field not in return_names:
            raise ValueError(f"{src_cls} 无输出字段 {out_field}")
        in_field = str(l["input_field_name"])
        dst_fields = link_slot_fields[dst]
        if in_field not in dst_fields:
            raise ValueError(
                f"{dst_cls} 无连线输入槽 {in_field}（标量字段应存于 static_input_data）"
            )
        origin_slot = return_names.index(out_field)
        target_slot = dst_fields.index(in_field)
        comfy_links.append(
            [i, id_map[src], origin_slot, id_map[dst], target_slot, infos[src_cls]["output"][origin_slot]]
        )
        comfy_nodes[id_map[src] - 1]["outputs"][origin_slot]["links"].append(i)
        comfy_nodes[id_map[dst] - 1]["inputs"][target_slot]["link"] = i

    return {
        "nodes": comfy_nodes,
        "links": comfy_links,
        "groups": [],
        "config": {},
        "extra": {"ds": {"offset": [0.0, 0.0], "scale": 1.0}},
        "version": 0.4,
    }
