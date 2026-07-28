"""基础工具节点 — Python代码输入、自定义股票池、公式输入、数据下载"""

import os
from typing import Optional, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui

# ────────────────────────── 通用 DataFrame I/O ──────────────────────────


class DataFrameInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


class DataFrameOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


# ============================================================
# 1. Python代码输入节点
# ============================================================


@ui(
    code={"input_type": "code_editor", "language": "python"},
    data={"input_type": "None"},
)
class PythonCodeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    code: str = Field(
        default="# 自定义Python代码\n# 可用变量: df (DataFrame), pd, np\n# 请修改 df 变量作为输出\ndf = df.copy() if df is not None else pd.DataFrame()\n",
        title="Python代码",
    )


class PythonCodeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="Python代码输入", group="10-基础工具", box_color="#607D8B")
class PythonCodeInputNode(BaseWorkNode):
    """自定义Python代码编写，接收DataFrame，输出DataFrame"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return PythonCodeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return PythonCodeOutput

    def run(self, input: PythonCodeInput) -> Optional[BaseModel]:
        df = input.data if input.data is not None else pd.DataFrame()
        if not input.code.strip():
            return PythonCodeOutput(data=df.copy())

        exec_ctx = {
            "df": df.copy(),
            "pd": pd,
            "np": np,
        }
        try:
            exec(
                input.code,
                {
                    "__builtins__": {
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
                        "True": True,
                        "False": False,
                        "None": None,
                    }
                },
                exec_ctx,
            )  # noqa: S102
            result = exec_ctx.get("df", df)
            if not isinstance(result, pd.DataFrame):
                result = df.copy()
        except Exception as e:
            print(f"Python代码执行错误: {e}")
            result = df.copy()

        return PythonCodeOutput(data=result)


# ============================================================
# 2. 自定义股票池节点
# ============================================================


@ui(
    stock_codes={
        "input_type": "text_field",
        "placeholder": "000001.SZ,600000.SH,000002.SZ",
    },
)
class StockPoolInput(BaseModel):
    stock_codes: str = Field(default="", title="股票代码(逗号分隔)")


class StockPoolOutput(BaseModel):
    stock_list: list = Field(default_factory=list, title="股票池")
    count: int = Field(default=0, title="数量")


@work_node(name="自定义股票池", group="10-基础工具", box_color="#607D8B")
class StockPoolNode(BaseWorkNode):
    """定义股票选择范围（股票代码列表），输出股票池"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return StockPoolInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return StockPoolOutput

    def run(self, input: StockPoolInput) -> Optional[BaseModel]:
        codes = [c.strip() for c in input.stock_codes.split(",") if c.strip()]
        return StockPoolOutput(stock_list=codes, count=len(codes))


# ============================================================
# 3. 公式输入节点
# ============================================================


@ui(
    formula={"input_type": "code_editor", "language": "python"},
    output_col={"input_type": "text_field"},
    data={"input_type": "None"},
)
class FormulaInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    formula: str = Field(default="df['close'] * 2", title="数学公式")
    output_col: str = Field(default="result", title="输出列名")


class FormulaOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None


@work_node(name="公式输入", group="10-基础工具", box_color="#607D8B")
class FormulaInputNode(BaseWorkNode):
    """数学公式定义，输入DataFrame+公式，输出计算结果"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FormulaInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FormulaOutput

    def run(self, input: FormulaInput) -> Optional[BaseModel]:
        df = input.data
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return FormulaOutput(data=pd.DataFrame())

        result = df.copy()
        eval_ctx = {"df": result, "np": np, "pd": pd}
        for col in result.columns:
            eval_ctx[col.lower()] = result[col]

        try:
            expr_result = eval(input.formula, {"__builtins__": {}}, eval_ctx)  # noqa: S307
            if isinstance(expr_result, pd.Series):
                result[input.output_col] = expr_result
            elif isinstance(expr_result, pd.DataFrame):
                result = expr_result
            else:
                result[input.output_col] = expr_result
        except Exception:
            result[input.output_col] = float("nan")

        return FormulaOutput(data=result)


# ============================================================
# 4. 数据下载节点
# ============================================================


@ui(
    data_url={"input_type": "text_field", "placeholder": "数据文件URL"},
    save_path={"input_type": "text_field", "placeholder": "本地保存路径"},
)
class DataDownloadInput(BaseModel):
    data_url: str = Field(default="", title="数据文件URL")
    save_path: str = Field(default="", title="本地保存路径")
    file_type: str = Field(default="csv", title="文件类型")


class DataDownloadOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    file_path: str = Field(default="", title="文件路径")
    success: bool = Field(default=False, title="是否成功")


@work_node(name="数据下载", group="10-基础工具", box_color="#607D8B")
class DataDownloadNode(BaseWorkNode):
    """下载行情数据到本地"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return DataDownloadInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return DataDownloadOutput

    def run(self, input: DataDownloadInput) -> Optional[BaseModel]:
        if not input.data_url.strip():
            return DataDownloadOutput(success=False)

        try:
            import urllib.request

            save_path = input.save_path.strip()
            if not save_path:
                save_path = f"/tmp/downloaded_data.{input.file_type}"
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            urllib.request.urlretrieve(input.data_url, save_path)

            # 读取为 DataFrame
            df = pd.DataFrame()
            if input.file_type == "csv":
                df = pd.read_csv(save_path)
            elif input.file_type in ("parquet", "pq"):
                df = pd.read_parquet(save_path)
            elif input.file_type == "excel":
                df = pd.read_excel(save_path)
            elif input.file_type == "json":
                df = pd.read_json(save_path)

            return DataDownloadOutput(data=df, file_path=save_path, success=True)
        except Exception as e:
            print(f"数据下载错误: {e}")
            return DataDownloadOutput(success=False)
