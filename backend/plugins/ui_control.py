from typing import Any
from functools import wraps


def ui(**field_ui_config):
    """装饰器 — 为 Pydantic Model 的字段注入 UI 元数据

    用法：
        @ui(
            start_date={"input_type": "date_picker"},
            formula={"input_type": "code_editor", "language": "python"},
            stock_pool={"input_type": "None"},  # 仅通过连线输入
        )
        class FactorBuildInput(BaseModel):
            start_date: str = "20200101"
            formula: str = ""
            stock_pool: list[str] = []

    前端根据 input_type 渲染对应控件：
        - date_picker: 日期选择器
        - text_field: 文本输入（支持 min_lines, max_lines）
        - code_editor: Monaco Editor（支持 language）
        - combobox: 下拉选择（支持 options）
        - number_field: 数字输入
        - stock_picker: 股票选择器
        - None: 不渲染（仅通过连线输入）
    """
    def decorator(cls):
        # 在 model_config 或自定义属性中存储 UI 元数据
        if not hasattr(cls, '__ui_metadata__'):
            cls.__ui_metadata__ = {}
        cls.__ui_metadata__.update(field_ui_config)

        # 同时注入到 model_json_schema 的 extra 中
        original_schema = cls.model_json_schema if hasattr(cls, 'model_json_schema') else None
        if original_schema:
            @classmethod
            def enhanced_schema(klass, **kwargs):
                schema = original_schema(**kwargs)
                properties = schema.get("properties", {})
                for field_name, ui_config in field_ui_config.items():
                    if field_name in properties:
                        properties[field_name]["ui"] = ui_config
                return schema
            cls.model_json_schema = enhanced_schema

        return cls
    return decorator


def get_ui_metadata(model_cls) -> dict:
    """获取模型的 UI 元数据"""
    return getattr(model_cls, '__ui_metadata__', {})
