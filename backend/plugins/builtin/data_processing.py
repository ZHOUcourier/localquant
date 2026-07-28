# 数据处理节点
from pydantic import BaseModel, Field
from typing import Optional
import pandas as pd

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui


# ============================================================
# 1. 数据筛选节点
# ============================================================

@ui(
    column={"input_type": "text_field", "placeholder": "列名"},
    operator={"input_type": "combobox", "options": [">", "<", ">=", "<=", "==", "!=", "contains", "not_contains"]},
    value={"input_type": "text_field", "placeholder": "筛选值"},
)
class DataFilterInput(BaseModel):
    column: str = Field(default="", title="列名")
    operator: str = Field(default=">", title="运算符")
    value: str = Field(default="", title="筛选值")


class DataFilterOutput(BaseModel):
    filtered_data: dict = Field(default_factory=dict, title="筛选后数据")

    class Config:
        arbitrary_types_allowed = True


@work_node(name="数据筛选", group="02-数据处理", box_color="blue")
class DataFilterNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return DataFilterInput

    @classmethod
    def output_model(cls):
        return DataFilterOutput

    def run(self, input: BaseModel) -> Optional[BaseModel]:
        # 从上游获取 DataFrame（假设上游输出包含 dataframe 字段）
        # 这里简化处理，实际需要从 context 获取
        df = pd.DataFrame()  # TODO: 从 context 获取上游数据

        if df.empty or not input.column:
            return DataFilterOutput(filtered_data=df.to_dict())

        try:
            val = input.value
            # 尝试转换为数值
            try:
                val = float(val)
            except ValueError:
                pass

            col = input.column
            op = input.operator

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

        return DataFilterOutput(filtered_data=df.to_dict())


# ============================================================
# 2. 列选择节点
# ============================================================

@ui(
    columns={"input_type": "text_field", "placeholder": "列名1,列名2,列名3"},
)
class ColumnSelectInput(BaseModel):
    columns: str = Field(default="", title="选择列(逗号分隔)")


class ColumnSelectOutput(BaseModel):
    selected_data: dict = Field(default_factory=dict, title="选中列数据")

    class Config:
        arbitrary_types_allowed = True


@work_node(name="列选择", group="02-数据处理", box_color="blue")
class ColumnSelectNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return ColumnSelectInput

    @classmethod
    def output_model(cls):
        return ColumnSelectOutput

    def run(self, input: BaseModel) -> Optional[BaseModel]:
        df = pd.DataFrame()  # TODO: 从 context 获取上游数据

        if df.empty or not input.columns.strip():
            return ColumnSelectOutput(selected_data=df.to_dict())

        try:
            cols = [c.strip() for c in input.columns.split(",") if c.strip()]
            # 只保留存在的列
            existing_cols = [c for c in cols if c in df.columns]
            if existing_cols:
                df = df[existing_cols]
        except Exception as e:
            print(f"列选择错误: {e}")

        return ColumnSelectOutput(selected_data=df.to_dict())


# ============================================================
# 3. 公式计算节点
# ============================================================

@ui(
    formula={"input_type": "code_editor", "language": "python", "placeholder": "df['new_col'] = df['col1'] * df['col2']"},
    output_column={"input_type": "text_field", "placeholder": "输出列名"},
)
class FormulaCalcInput(BaseModel):
    formula: str = Field(default="", title="计算公式(Python表达式)")
    output_column: str = Field(default="result", title="输出列名")


class FormulaCalcOutput(BaseModel):
    result_data: dict = Field(default_factory=dict, title="计算结果")

    class Config:
        arbitrary_types_allowed = True


@work_node(name="公式计算", group="02-数据处理", box_color="blue")
class FormulaCalcNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return FormulaCalcInput

    @classmethod
    def output_model(cls):
        return FormulaCalcOutput

    def run(self, input: BaseModel) -> Optional[BaseModel]:
        df = pd.DataFrame()  # TODO: 从 context 获取上游数据

        if df.empty or not input.formula.strip():
            return FormulaCalcOutput(result_data=df.to_dict())

        try:
            # 执行用户公式
            exec(input.formula, {"df": df, "pd": pd, "np": __import__("numpy")})
        except Exception as e:
            print(f"公式计算错误: {e}")

        return FormulaCalcOutput(result_data=df.to_dict())


# ============================================================
# 4. 合并数据节点
# ============================================================

@ui(
    merge_type={"input_type": "combobox", "options": ["inner", "left", "right", "outer", "concat"]},
    on_column={"input_type": "text_field", "placeholder": "关联列名（merge时使用）"},
)
class MergeDataInput(BaseModel):
    merge_type: str = Field(default="inner", title="合并方式")
    on_column: str = Field(default="", title="关联列")


class MergeDataOutput(BaseModel):
    merged_data: dict = Field(default_factory=dict, title="合并后数据")

    class Config:
        arbitrary_types_allowed = True


@work_node(name="合并数据", group="02-数据处理", box_color="blue")
class MergeDataNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return MergeDataInput

    @classmethod
    def output_model(cls):
        return MergeDataOutput

    def run(self, input: BaseModel) -> Optional[BaseModel]:
        # TODO: 从 context 获取两个上游 DataFrame
        df1 = pd.DataFrame()
        df2 = pd.DataFrame()

        if df1.empty or df2.empty:
            return MergeDataOutput(merged_data=df1.to_dict())

        try:
            if input.merge_type == "concat":
                result = pd.concat([df1, df2], ignore_index=True)
            else:
                on_col = input.on_column.strip() if input.on_column.strip() else None
                result = pd.merge(df1, df2, on=on_col, how=input.merge_type)
        except Exception as e:
            print(f"合并数据错误: {e}")
            result = df1

        return MergeDataOutput(merged_data=result.to_dict())


# ============================================================
# 5. 排序过滤节点
# ============================================================

@ui(
    sort_column={"input_type": "text_field", "placeholder": "排序列名"},
    ascending={"input_type": "combobox", "options": ["True", "False"]},
    top_n={"input_type": "number_field", "placeholder": "取前N条，0表示全部"},
)
class SortFilterInput(BaseModel):
    sort_column: str = Field(default="", title="排序列")
    ascending: str = Field(default="True", title="升序")
    top_n: int = Field(default=0, title="取前N条(0=全部)")


class SortFilterOutput(BaseModel):
    sorted_data: dict = Field(default_factory=dict, title="排序后数据")

    class Config:
        arbitrary_types_allowed = True


@work_node(name="排序过滤", group="02-数据处理", box_color="blue")
class SortFilterNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return SortFilterInput

    @classmethod
    def output_model(cls):
        return SortFilterOutput

    def run(self, input: BaseModel) -> Optional[BaseModel]:
        df = pd.DataFrame()  # TODO: 从 context 获取上游数据

        if df.empty:
            return SortFilterOutput(sorted_data=df.to_dict())

        try:
            if input.sort_column.strip() and input.sort_column in df.columns:
                ascending = input.ascending == "True"
                df = df.sort_values(by=input.sort_column, ascending=ascending)

            if input.top_n > 0:
                df = df.head(input.top_n)
        except Exception as e:
            print(f"排序过滤错误: {e}")

        return SortFilterOutput(sorted_data=df.to_dict())


# ============================================================
# 6. 代码执行节点
# ============================================================

@ui(
    code={"input_type": "code_editor", "language": "python", "placeholder": "# 自定义Python代码\ndf = input_data\ndf['new_col'] = 1"},
)
class CodeExecInput(BaseModel):
    code: str = Field(default="", title="Python代码")


class CodeExecOutput(BaseModel):
    result_data: dict = Field(default_factory=dict, title="执行结果")

    class Config:
        arbitrary_types_allowed = True


@work_node(name="代码执行", group="02-数据处理", box_color="red")
class CodeExecNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return CodeExecInput

    @classmethod
    def output_model(cls):
        return CodeExecOutput

    def run(self, input: BaseModel) -> Optional[BaseModel]:
        df = pd.DataFrame()  # TODO: 从 context 获取上游数据

        if not input.code.strip():
            return CodeExecOutput(result_data=df.to_dict())

        try:
            # 提供常用库
            env = {
                "df": df,
                "pd": pd,
                "np": __import__("numpy"),
                "input_data": df,
            }
            exec(input.code, env)
            # 获取执行后的 df
            result_df = env.get("df", df)
            if not isinstance(result_df, pd.DataFrame):
                result_df = df
        except Exception as e:
            print(f"代码执行错误: {e}")
            result_df = df

        return CodeExecOutput(result_data=result_df.to_dict())
