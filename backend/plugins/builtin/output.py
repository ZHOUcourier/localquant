"""输出相关内置工作流节点"""

import json
import pickle
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from backend.config import settings
from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui

# ────────────────────────────────────────────────────────────
# 1. 输出节点
# ────────────────────────────────────────────────────────────


class OutputInput(BaseModel):
    """输出节点输入"""

    data: dict  # DataFrame dict: {col: {index: value}}
    output_name: str = "output"
    format: str = "table"  # "table" / "csv" / "json"


@ui(
    data={"input_type": "None"},
    output_name={"input_type": "text_field"},
    format={"input_type": "combobox", "options": ["table", "csv", "json"]},
)
class OutputInputUI(OutputInput):
    pass


class OutputOutput(BaseModel):
    """输出节点输出"""

    output_path: str = ""
    row_count: int = 0
    columns: list[str] = []
    preview: list[dict] = []


@work_node(
    name="输出",
    group="09-输出",
    box_color="purple",
    description="将上游数据保存到本地 outputs 目录，支持 table(pickle)/csv/json 格式并输出预览",
    example="任意数据节点 → 输出",
    notes=[
        "data 需连线提供；始终额外保存一份 pickle 副本",
        "预览仅展示前 10 行",
    ],
)
class OutputNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return OutputInputUI

    @classmethod
    def output_model(cls):
        return OutputOutput

    def run(self, input: OutputInputUI) -> OutputOutput:
        df = pd.DataFrame(input.data)
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            pass

        output_name = input.output_name or "output"
        fmt = input.format or "table"

        # 始终保存 pickle 格式
        out_dir = settings.output_dir / "manual"
        out_dir.mkdir(parents=True, exist_ok=True)
        pkl_path = out_dir / f"{output_name}.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(df, f)

        output_path = str(pkl_path)

        # 根据格式额外导出
        if fmt == "csv":
            csv_path = out_dir / f"{output_name}.csv"
            df.to_csv(csv_path, encoding="utf-8-sig")
            output_path = str(csv_path)
        elif fmt == "json":
            json_path = out_dir / f"{output_name}.json"
            df.to_json(
                json_path, orient="records", force_ascii=False, date_format="iso"
            )
            output_path = str(json_path)

        # 构造预览（前 10 行）
        preview_df = df.head(10)
        preview = preview_df.reset_index(drop=True).to_dict(orient="records")

        return OutputOutput(
            output_path=output_path,
            row_count=len(df),
            columns=list(df.columns),
            preview=_sanitize_preview(preview),
        )


# ────────────────────────────────────────────────────────────
# 2. 股票排名节点
# ────────────────────────────────────────────────────────────


class StockRankInput(BaseModel):
    """股票排名输入"""

    factor_data_1: dict = {}  # DataFrame dict
    factor_data_2: dict = {}  # DataFrame dict
    top_n: int = 30
    sort_field: str = ""  # 排序字段（空则取最后一列）
    ascending: bool = False  # 默认降序（得分高的在前）


@ui(
    factor_data_1={"input_type": "None"},
    factor_data_2={"input_type": "None"},
    top_n={"input_type": "number_field"},
    sort_field={"input_type": "text_field"},
    ascending={"input_type": "None"},
)
class StockRankInputUI(StockRankInput):
    pass


class StockRankOutput(BaseModel):
    """股票排名输出"""

    result: dict  # DataFrame dict: {col: {index: value}}
    row_count: int = 0
    columns: list[str] = []


@work_node(
    name="股票排名",
    group="09-输出",
    box_color="purple",
    description="合并最多两路因子数据，按指定字段排序并输出前 N 名股票",
    example="因子构建 ×2 → 股票排名 → 输出",
    notes=[
        "factor_data_1 / factor_data_2 需连线提供，可只连一路",
        "排序字段留空时默认取最后一列，默认降序（得分高在前）",
    ],
)
class StockRankNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return StockRankInputUI

    @classmethod
    def output_model(cls):
        return StockRankOutput

    def run(self, input: StockRankInputUI) -> StockRankOutput:
        # 合并多个因子数据
        dfs = []
        for fd in [input.factor_data_1, input.factor_data_2]:
            if fd:
                df_part = pd.DataFrame(fd)
                try:
                    df_part.index = pd.to_datetime(df_part.index)
                except Exception:
                    pass
                dfs.append(df_part)

        if not dfs:
            return StockRankOutput(result={}, row_count=0, columns=[])

        # 合并（按列拼接）
        merged = pd.concat(dfs, axis=1)
        # 去除重复列
        merged = merged.loc[:, ~merged.columns.duplicated()]

        # 确定排序字段
        sort_field = input.sort_field
        if not sort_field or sort_field not in merged.columns:
            sort_field = merged.columns[-1]

        # 排序并取 Top N
        merged = merged.sort_values(by=sort_field, ascending=input.ascending)
        top_df = merged.head(input.top_n)

        # 转为 dict（与 runner 中 DataFrame 序列化方式一致）
        result_dict = {
            col: {str(idx): val for idx, val in top_df[col].items()}
            for col in top_df.columns
        }

        return StockRankOutput(
            result=result_dict,
            row_count=len(top_df),
            columns=list(top_df.columns),
        )


# ────────────────────────────────────────────────────────────
# 辅助函数
# ────────────────────────────────────────────────────────────


def _sanitize_preview(data: list[dict]) -> list[dict]:
    """清理预览数据，确保 JSON 可序列化"""
    sanitized = []
    for row in data:
        clean_row = {}
        for k, v in row.items():
            if isinstance(v, (pd.Timestamp,)):
                clean_row[k] = str(v)
            elif pd.isna(v) if isinstance(v, float) else False:
                clean_row[k] = None
            else:
                try:
                    json.dumps(v)
                    clean_row[k] = v
                except (TypeError, ValueError):
                    clean_row[k] = str(v)
        sanitized.append(clean_row)
    return sanitized
