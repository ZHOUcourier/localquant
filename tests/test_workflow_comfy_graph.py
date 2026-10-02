"""工作流 → ComfyUI 图转换往返一致性（编辑器加载已保存工作流，P0 修复）

链路：DB nodes/links → /comfy-graph → 前端 loadGraphData → 用户运行 →
prompt → convert_prompt → runner nodes/links。往返测试锁定「最后一跳
还原出的管线与原工作流等价」，即画布加载不改语义。
"""

import json
from pathlib import Path

import pytest

from backend.comfy.adapter import get_return_names, node_to_object_info
from backend.comfy.graph import convert_prompt, workflow_to_comfy_graph
from backend.plugins.loader import load_all_nodes
from backend.plugins.registry import ALL_WORK_NODES

load_all_nodes()

TEMPLATES = sorted(Path("templates").glob("*.json"))


def _is_widget_type(spec_type) -> bool:
    return isinstance(spec_type, list) or spec_type in ("STRING", "INT", "FLOAT", "BOOLEAN")


def _simulate_frontend_serialize(graph: dict) -> dict:
    """模拟 ComfyUI 前端画布 → API prompt：widget 当前值 + 连线 [node_id, out_slot]"""
    infos = {name: node_to_object_info(cls) for name, cls in ALL_WORK_NODES.items()}
    prompt = {}
    for n in graph["nodes"]:
        info = infos[n["type"]]
        props = n["properties"]["localquant_static_input"]
        inputs: dict = {}
        for section in ("required", "optional"):
            for fname, (spec_type, _extra) in info["input"][section].items():
                if _is_widget_type(spec_type) and fname in props:
                    inputs[fname] = props[fname]
        for slot in n["inputs"]:
            if slot["link"] is not None:
                link = next(l for l in graph["links"] if l[0] == slot["link"])
                inputs[slot["name"]] = [str(link[1]), link[2]]
        prompt[str(n["id"])] = {
            "class_type": n["type"],
            "inputs": inputs,
            "_meta": {"title": n["title"]},
        }
    return prompt


def _assert_graph_shape(graph: dict, nodes: list[dict]) -> None:
    ids = [n["id"] for n in graph["nodes"]]
    assert len(ids) == len(nodes) and len(set(ids)) == len(ids)
    assert all(isinstance(i, int) for i in ids)
    by_id = {n["id"]: n for n in graph["nodes"]}
    for n in graph["nodes"]:
        info = node_to_object_info(ALL_WORK_NODES[n["type"]])
        slot_fields = [
            f for f, (t, _e) in info["input"]["optional"].items() if not _is_widget_type(t)
        ]
        assert [s["name"] for s in n["inputs"]] == slot_fields
        assert [o["name"] for o in n["outputs"]] == list(info["output_name"])
    for link in graph["links"]:
        _lid, src, src_slot, dst, dst_slot, _t = link
        src_type = by_id[src]["type"]
        assert 0 <= src_slot < len(get_return_names(src_type))
        assert 0 <= dst_slot < len(by_id[dst]["inputs"])
    # outputs[].links 与 inputs[].link 双向回填一致
    for link in graph["links"]:
        lid, src, src_slot, dst, dst_slot, _t = link
        assert lid in by_id[src]["outputs"][src_slot]["links"]
        assert by_id[dst]["inputs"][dst_slot]["link"] == lid


@pytest.mark.parametrize("tpl_path", TEMPLATES, ids=lambda p: p.stem)
def test_template_roundtrip(tpl_path):
    """三模板：转换 → 模拟前端序列化 → convert_prompt 还原，管线与原工作流等价"""
    tpl = json.loads(tpl_path.read_text(encoding="utf-8"))
    nodes, links = tpl["nodes"], tpl["links"]

    graph = workflow_to_comfy_graph(nodes, links)
    _assert_graph_shape(graph, nodes)

    prompt = _simulate_frontend_serialize(graph)
    rt_nodes, rt_links = convert_prompt(prompt)

    # convert_prompt 的 uuid 即 prompt id（= 转换器生成的 int id 的字符串形式）
    id2uuid = {n["id"]: orig["uuid"] for n, orig in zip(graph["nodes"], nodes)}
    orig_by_uuid = {n["uuid"]: n for n in nodes}
    assert len(rt_nodes) == len(nodes)
    for rn in rt_nodes:
        uuid = id2uuid[int(rn["uuid"])]
        orig = orig_by_uuid[uuid]
        assert rn["name"] == orig["name"], uuid
        assert rn["title"] == orig["title"], uuid
        assert rn["static_input_data"] == orig["static_input_data"], uuid

    got = {
        (
            id2uuid[int(l["previous_node_uuid"])],
            l["output_field_name"],
            id2uuid[int(l["next_node_uuid"])],
            l["input_field_name"],
        )
        for l in rt_links
    }
    want = {
        (
            l["previous_node_uuid"],
            l["output_field_name"],
            l["next_node_uuid"],
            l["input_field_name"],
        )
        for l in links
    }
    assert got == want


def test_unknown_class_rejected():
    with pytest.raises(ValueError, match="未知节点类型"):
        workflow_to_comfy_graph(
            [{"uuid": "a", "name": "NoSuchNode", "static_input_data": {}}], []
        )


def test_dangling_link_rejected():
    with pytest.raises(ValueError, match="不存在的节点"):
        workflow_to_comfy_graph(
            [{"uuid": "a", "name": "ICNode", "static_input_data": {}}],
            [
                {
                    "uuid": "l1",
                    "previous_node_uuid": "ghost",
                    "output_field_name": "factor_data",
                    "next_node_uuid": "a",
                    "input_field_name": "factor_data",
                }
            ],
        )


def test_scalar_field_as_link_rejected():
    """标量字段不能当连线目标（应存 static_input_data）——错误尽早暴露"""
    with pytest.raises(ValueError, match="无连线输入槽"):
        workflow_to_comfy_graph(
            [
                {"uuid": "a", "name": "ICNode", "static_input_data": {}},
                {"uuid": "b", "name": "ICNode", "static_input_data": {}},
            ],
            [
                {
                    "uuid": "l1",
                    "previous_node_uuid": "a",
                    "output_field_name": "ic_result",
                    "next_node_uuid": "b",
                    "input_field_name": "periods",  # STRING widget，非连线槽
                }
            ],
        )
