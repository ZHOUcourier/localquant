# SPDX-License-Identifier: GPL-3.0-or-later
"""节点反射适配器 — ALL_WORK_NODES → ComfyUI object_info（V1 schema）

不改现有 work_node 本体：读取 pydantic input/output model + @ui 元数据，
生成 ComfyUI 前端可渲染的节点定义。

映射规则（与方案 B.4 一致）：
  @ui input_type          → ComfyUI INPUT_TYPES
  ------------------------------------------------
  date_picker             → ("STRING", {})
  text_field              → ("STRING", {"multiline": False})
  code_editor             → ("STRING", {"multiline": True})
  combobox(options)       → (options 列表, {})
  number_field            → ("INT"/"FLOAT", {"default", "min", "max"})
  stock_picker            → ("STRING", {})
  None（仅连线）           → 自定义类型输入槽（无 widget）
  无 @ui 的非标量字段       → 按注解推导的自定义类型（DICT/DATAFRAME/...）

连线类型即字符串，同名可连（ComfyUI 原生语义）。
输出索引 ↔ 字段名 的映射由 get_return_names() 提供，供 graph.py 转换连线。
"""

from typing import Any, Optional, Type, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import ALL_WORK_NODES

# ---------------------------------------------------------------------------
# 类型注解 → ComfyUI 类型字符串
# ---------------------------------------------------------------------------


def _unwrap_optional(annotation: Any) -> Any:
    """Optional[X] / Union[X, None] → X"""
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _annotation_to_type(annotation: Any) -> str:
    """python 注解 → ComfyUI 连线类型字符串"""
    annotation = _unwrap_optional(annotation)
    if annotation is str:
        return "STRING"
    if annotation is int:
        return "INT"
    if annotation is float:
        return "FLOAT"
    if annotation is bool:
        return "BOOLEAN"
    origin = get_origin(annotation)
    if annotation is dict or origin is dict:
        return "DICT"
    if annotation is list or origin is list:
        return "LIST"
    # pandas 对象按名称判断，避免对注解做 isinstance
    name = getattr(annotation, "__name__", "")
    if name == "DataFrame":
        return "DATAFRAME"
    if name == "Series":
        return "SERIES"
    if annotation is Any or name in ("Any", "object"):
        return "*"
    return "*"


def _field_default(field) -> Any:
    """提取字段默认值（无默认值返回 None）"""
    if field.default is not PydanticUndefined and field.default is not None:
        return field.default
    if field.default_factory is not None:
        try:
            return field.default_factory()
        except Exception:
            return None
    return None


def _number_constraints(field) -> dict[str, Any]:
    """从 pydantic FieldInfo.metadata 提取 min/max（annotated_types）"""
    out: dict[str, Any] = {}
    for meta in getattr(field, "metadata", []):
        for attr, key in (("ge", "min"), ("gt", "min"), ("le", "max"), ("lt", "max")):
            v = getattr(meta, attr, None)
            if v is not None:
                out[key] = v
    return out


# ---------------------------------------------------------------------------
# 单字段 → ComfyUI 输入定义
# ---------------------------------------------------------------------------

_SCALAR_TYPES = ("STRING", "INT", "FLOAT", "BOOLEAN")


def _input_spec(name: str, field, ui_conf: dict) -> tuple[Any, dict, bool]:
    """
    返回 (type_or_options, extra_options, is_link_only)

    is_link_only=True 的字段没有 widget，只能通过连线输入 → 放入 optional。
    """
    annotation = _unwrap_optional(field.annotation)
    base_type = _annotation_to_type(annotation)
    default = _field_default(field)
    title = field.title or name
    input_type = ui_conf.get("input_type")

    extra: dict[str, Any] = {"tooltip": title}

    # 仅连线输入（@ui input_type: "None" 或非标量类型）
    if input_type in ("None", None) and (
        input_type == "None" or base_type not in _SCALAR_TYPES
    ):
        return base_type, extra, True

    if input_type == "combobox":
        options = list(ui_conf.get("options", []))
        if default is not None and default not in options:
            options = [default, *options]
        if default is not None:
            extra["default"] = default
        return options or ["--"], extra, False

    if input_type == "number_field":
        num_type = "FLOAT" if base_type == "FLOAT" else "INT"
        extra.update(_number_constraints(field))
        if default is not None:
            extra["default"] = default
        if num_type == "FLOAT":
            extra.setdefault("step", 0.01)
        return num_type, extra, False

    if input_type == "code_editor":
        extra["multiline"] = True
        extra["default"] = default if isinstance(default, str) else ""
        return "STRING", extra, False

    if input_type in ("text_field", "date_picker", "stock_picker"):
        extra["multiline"] = False
        extra["default"] = default if isinstance(default, str) else ""
        placeholder = ui_conf.get("placeholder")
        if placeholder:
            extra["placeholder"] = placeholder
        return "STRING", extra, False

    # 无 @ui 的标量字段：按注解推导 widget
    if base_type == "BOOLEAN":
        extra["default"] = bool(default) if default is not None else False
        return "BOOLEAN", extra, False
    if base_type in ("INT", "FLOAT"):
        if default is not None:
            extra["default"] = default
        extra.update(_number_constraints(field))
        return base_type, extra, False
    if base_type == "STRING":
        extra["multiline"] = False
        extra["default"] = default if isinstance(default, str) else ""
        return "STRING", extra, False

    return base_type, extra, True


# ---------------------------------------------------------------------------
# 节点类 → object_info 条目
# ---------------------------------------------------------------------------


def node_to_object_info(node_cls: Type[BaseWorkNode]) -> dict[str, Any]:
    """单个节点类 → ComfyUI object_info 条目（V1 schema）"""
    input_cls: Optional[Type[BaseModel]] = node_cls.input_model()
    output_cls: Optional[Type[BaseModel]] = node_cls.output_model()
    ui_meta: dict = getattr(input_cls, "__ui_metadata__", {}) if input_cls else {}

    required: dict[str, Any] = {}
    optional: dict[str, Any] = {}
    if input_cls is not None:
        for fname, field in input_cls.model_fields.items():
            spec_type, extra, link_only = _input_spec(
                fname, field, ui_meta.get(fname, {}) or {}
            )
            if link_only:
                optional[fname] = (spec_type, extra)
            else:
                required[fname] = (spec_type, extra)

    output_types: list[str] = []
    output_names: list[str] = []
    if output_cls is not None:
        for fname, field in output_cls.model_fields.items():
            output_types.append(_annotation_to_type(field.annotation))
            output_names.append(fname)

    display = node_cls.__work_node_display_name__ or node_cls.__name__
    description = node_cls.__work_node_description__ or ""
    notes = node_cls.__work_node_notes__ or []
    if notes:
        description = description + "\n\n" + "\n".join(f"• {n}" for n in notes)

    return {
        "input": {"required": required, "optional": optional},
        "input_order": {
            "required": list(required.keys()),
            "optional": list(optional.keys()),
        },
        "output": output_types,
        "output_is_list": [False] * len(output_types),
        "output_name": output_names,
        "output_tooltips": output_names,
        "name": node_cls.__name__,
        "display_name": display,
        "description": description,
        "python_module": "nodes",
        "category": node_cls.__work_node_group__ or "99-自定义节点",
        "output_node": len(output_types) == 0,
        "deprecated": False,
        "experimental": False,
    }


def build_object_info() -> dict[str, Any]:
    """全部节点 → object_info 字典 {类名: 定义}"""
    result: dict[str, Any] = {}
    for cls_name, node_cls in ALL_WORK_NODES.items():
        try:
            result[cls_name] = node_to_object_info(node_cls)
        except Exception as e:  # 单节点反射失败不拖垮整体
            from loguru import logger

            logger.warning(f"object_info 反射失败 {cls_name}: {e}")
    return result


def get_return_names(class_type: str) -> list[str]:
    """节点类的输出字段名列表（索引即 ComfyUI 连线的输出索引）"""
    node_cls = ALL_WORK_NODES.get(class_type)
    if node_cls is None:
        return []
    output_cls = node_cls.output_model()
    if output_cls is None:
        return []
    return list(output_cls.model_fields.keys())
