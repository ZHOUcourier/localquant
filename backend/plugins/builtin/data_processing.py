# 数据处理节点
from typing import Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui

# ============================================================
# 1. 数据筛选节点
# ============================================================


@ui(
    column={"input_type": "text_field", "placeholder": "列名"},
    operator={
        "input_type": "combobox",
        "options": [">", "<", ">=", "<=", "==", "!=", "contains", "not_contains"],
    },
    value={"input_type": "text_field", "placeholder": "筛选值"},
    data={"input_type": "None"},
)
class DataFilterInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    column: str = Field(default="", title="列名")
    operator: str = Field(default=">", title="运算符")
    value: str = Field(default="", title="筛选值")


class DataFilterOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(
    name="数据筛选",
    group="02-数据处理",
    box_color="blue",
    description="按单个条件筛选 DataFrame 行，支持比较运算与包含/不包含判断；多条件可串联多个筛选节点",
    example="QMT行情数据 → 数据筛选 → 排序过滤",
    notes=[
        "筛选值会尝试转为数字，失败时按字符串比较",
        "列名不存在时原样返回数据，不会报错",
    ],
)
class DataFilterNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return DataFilterInput

    @classmethod
    def output_model(cls):
        return DataFilterOutput

    def run(self, input: DataFilterInput) -> Optional[BaseModel]:
        df = input.data
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return DataFilterOutput(data=pd.DataFrame())
        if not input.column:
            return DataFilterOutput(data=df.copy())

        df = df.copy()
        try:
            val = input.value
            try:
                val = float(val)
            except ValueError:
                pass

            col = input.column
            op = input.operator

            if col not in df.columns:
                return DataFilterOutput(data=df)

            if op == ">":
                df = df[df[col] > val]
            elif op == "<":
                df = df[df[col] < val]
            elif op == ">=":
                df = df[df[col] >= val]
            elif op == "<=":
                df = df[df[col] <= val]
            elif op == "==":
                df = df[df[col] == val]
            elif op == "!=":
                df = df[df[col] != val]
            elif op == "contains":
                df = df[df[col].astype(str).str.contains(str(val), na=False)]
            elif op == "not_contains":
                df = df[~df[col].astype(str).str.contains(str(val), na=False)]
        except Exception as e:
            print(f"数据筛选错误: {e}")

        return DataFilterOutput(data=df)


# ============================================================
# 2. 列选择节点
# ============================================================


@ui(
    columns={"input_type": "text_field", "placeholder": "列名1,列名2,列名3"},
    data={"input_type": "None"},
)
class ColumnSelectInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    columns: str = Field(default="", title="选择列(逗号分隔)")


class ColumnSelectOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(
    name="列选择",
    group="02-数据处理",
    box_color="blue",
    description="从 DataFrame 中选取指定列，不存在的列名会被自动忽略",
    example="QMT行情数据 → 列选择 → 因子构建",
    notes=[
        "列名用逗号分隔；留空时原样输出全部列",
    ],
)
class ColumnSelectNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return ColumnSelectInput

    @classmethod
    def output_model(cls):
        return ColumnSelectOutput

    def run(self, input: ColumnSelectInput) -> Optional[BaseModel]:
        df = input.data
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return ColumnSelectOutput(data=pd.DataFrame())
        if not input.columns.strip():
            return ColumnSelectOutput(data=df.copy())

        df = df.copy()
        try:
            cols = [c.strip() for c in input.columns.split(",") if c.strip()]
            existing_cols = [c for c in cols if c in df.columns]
            if existing_cols:
                df = df[existing_cols]
        except Exception as e:
            print(f"列选择错误: {e}")

        return ColumnSelectOutput(data=df)


# ============================================================
# 3. 公式计算节点
# ============================================================


@ui(
    formula={
        "input_type": "code_editor",
        "language": "python",
        "placeholder": "df['new_col'] = df['col1'] * df['col2']",
    },
    output_column={"input_type": "text_field", "placeholder": "输出列名"},
    data={"input_type": "None"},
)
class FormulaCalcInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    formula: str = Field(default="", title="计算公式(Python表达式)")
    output_column: str = Field(default="result", title="输出列名")


class FormulaCalcOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


# 公式/代码节点只提供受限内置函数，防止执行任意系统操作（与因子构建节点同款白名单）
_SAFE_BUILTINS = {
    "print": print,
    "range": range,
    "len": len,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "round": round,
}


@work_node(
    name="公式计算",
    group="02-数据处理",
    box_color="blue",
    description="对 DataFrame 执行自定义赋值语句生成新列，如 df['new'] = df['a'] * df['b']",
    example="合并数据 → 公式计算 → 排序过滤",
    notes=[
        "公式中可用 df、pd、np 三个变量，需直接对 df 赋值",
        "计算失败时原样返回输入数据，不会中断工作流",
    ],
)
class FormulaCalcNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return FormulaCalcInput

    @classmethod
    def output_model(cls):
        return FormulaCalcOutput

    def run(self, input: FormulaCalcInput) -> Optional[BaseModel]:
        df = input.data
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return FormulaCalcOutput(data=pd.DataFrame())
        if not input.formula.strip():
            return FormulaCalcOutput(data=df.copy())

        df = df.copy()
        try:
            exec(input.formula, {"__builtins__": _SAFE_BUILTINS, "df": df, "pd": pd, "np": np})  # noqa: S102
        except Exception as e:
            print(f"公式计算错误: {e}")

        return FormulaCalcOutput(data=df)


# ============================================================
# 4. 合并数据节点
# ============================================================


@ui(
    merge_type={
        "input_type": "combobox",
        "options": ["inner", "left", "right", "outer", "concat"],
    },
    on_column={"input_type": "text_field", "placeholder": "关联列名（merge时使用）"},
    data={"input_type": "None"},
    data2={"input_type": "None"},
)
class MergeDataInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    data2: Optional[pd.DataFrame] = None
    merge_type: str = Field(default="inner", title="合并方式")
    on_column: str = Field(default="", title="关联列")


class MergeDataOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(
    name="合并数据",
    group="02-数据处理",
    box_color="blue",
    description="合并两个 DataFrame，支持 inner/left/right/outer 连接与 concat 拼接",
    example="QMT行情数据 + QMT财务数据 → 合并数据 → 因子构建（代码）",
    notes=[
        "data 与 data2 两个输入口均需连线提供；任一为空时直接返回另一个",
        "merge 方式需指定关联列，concat 方式按行拼接",
    ],
)
class MergeDataNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return MergeDataInput

    @classmethod
    def output_model(cls):
        return MergeDataOutput

    def run(self, input: MergeDataInput) -> Optional[BaseModel]:
        df1 = input.data
        df2 = input.data2

        if df1 is None or (isinstance(df1, pd.DataFrame) and df1.empty):
            return MergeDataOutput(data=df2 if df2 is not None else pd.DataFrame())
        if df2 is None or (isinstance(df2, pd.DataFrame) and df2.empty):
            return MergeDataOutput(data=df1.copy())

        try:
            if input.merge_type == "concat":
                result = pd.concat([df1, df2], ignore_index=True)
            else:
                on_col = input.on_column.strip() if input.on_column.strip() else None
                result = pd.merge(df1, df2, on=on_col, how=input.merge_type)
        except Exception as e:
            print(f"合并数据错误: {e}")
            result = df1.copy()

        return MergeDataOutput(data=result)


# ============================================================
# 5. 排序过滤节点
# ============================================================


@ui(
    sort_column={"input_type": "text_field", "placeholder": "排序列名"},
    ascending={"input_type": "combobox", "options": ["True", "False"]},
    top_n={"input_type": "number_field", "placeholder": "取前N条，0表示全部"},
    data={"input_type": "None"},
)
class SortFilterInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    sort_column: str = Field(default="", title="排序列")
    ascending: str = Field(default="True", title="升序")
    top_n: int = Field(default=0, title="取前N条(0=全部)")


class SortFilterOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(
    name="排序过滤",
    group="02-数据处理",
    box_color="blue",
    description="对 DataFrame 按指定列排序，并可取前 N 条",
    example="数据筛选 → 排序过滤 → 股票排名",
    notes=[
        "top_n 为 0 时返回全部行",
    ],
)
class SortFilterNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return SortFilterInput

    @classmethod
    def output_model(cls):
        return SortFilterOutput

    def run(self, input: SortFilterInput) -> Optional[BaseModel]:
        df = input.data
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return SortFilterOutput(data=pd.DataFrame())

        df = df.copy()
        try:
            if input.sort_column.strip() and input.sort_column in df.columns:
                ascending = input.ascending == "True"
                df = df.sort_values(by=input.sort_column, ascending=ascending)
            if input.top_n > 0:
                df = df.head(input.top_n)
        except Exception as e:
            print(f"排序过滤错误: {e}")

        return SortFilterOutput(data=df)


# ============================================================
# 6. 代码执行节点
# ============================================================


@ui(
    code={
        "input_type": "code_editor",
        "language": "python",
        "placeholder": "# 自定义Python代码\ndf = input_data\ndf['new_col'] = 1",
    },
    data={"input_type": "None"},
)
class CodeExecInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    code: str = Field(default="", title="Python代码")


class CodeExecOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(
    name="代码执行",
    group="02-数据处理",
    box_color="blue",
    description="执行自定义 Python 代码块，对输入数据做任意转换（可用 df/input_data/pd/np）",
    example="QMT行情数据 → 代码执行 → 输出",
    notes=[
        "需把结果写回 df 变量；执行失败时原样返回输入数据",
        "内置函数为受限白名单（无 open/import/os 等），复杂逻辑请使用「自定义节点」",
    ],
)
class CodeExecNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return CodeExecInput

    @classmethod
    def output_model(cls):
        return CodeExecOutput

    def run(self, input: CodeExecInput) -> Optional[BaseModel]:
        df = input.data if input.data is not None else pd.DataFrame()
        if not input.code.strip():
            return CodeExecOutput(data=df.copy())

        try:
            env = {
                "__builtins__": _SAFE_BUILTINS,
                "df": df.copy(),
                "pd": pd,
                "np": np,
                "input_data": df.copy(),
            }
            exec(input.code, env)  # noqa: S102
            result_df = env.get("df", df)
            if not isinstance(result_df, pd.DataFrame):
                result_df = df.copy()
        except Exception as e:
            print(f"代码执行错误: {e}")
            result_df = df.copy()

        return CodeExecOutput(data=result_df)
