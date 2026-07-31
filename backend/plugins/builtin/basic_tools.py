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


@work_node(
    name="Python代码输入",
    group="10-基础工具",
    box_color="#607D8B",
    description="输入并执行自定义 Python 代码，对上游 DataFrame 做任意加工，主要用于因子编写 / 策略编写场景",
    example="QMT行情数据 → Python代码输入 → 因子构建 / 策略回测",
    notes=[
        "代码中可用变量：df（上游 DataFrame）、pd、np；需把结果写回 df 变量",
        "仅支持受限的内置函数，不允许 os.system、文件读写等危险操作",
        "代码执行报错时会回退为原样输出上游数据",
    ],
)
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
    mode={
        "input_type": "combobox",
        "options": ["手工列表", "指数成分(as-of逐日)"],
    },
    stock_codes={
        "input_type": "text_field",
        "placeholder": "000001.SZ,600000.SH,000002.SZ",
    },
    index_name={"input_type": "text_field", "placeholder": "如：沪深300"},
)
class StockPoolInput(BaseModel):
    mode: str = Field(default="手工列表", title="股票池模式")
    stock_codes: str = Field(default="", title="股票代码(逗号分隔)")
    index_name: str = Field(default="", title="指数/板块名")


class StockPoolOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    stock_list: list = Field(default_factory=list, title="股票池")
    count: int = Field(default=0, title="数量")
    membership: Optional[pd.DataFrame] = Field(default=None, title="逐日成员掩码")
    assumptions: list = Field(default_factory=list, title="假设清单")


@work_node(
    name="自定义股票池",
    group="10-基础工具",
    box_color="#607D8B",
    description="定义股票选择范围：手工列表或按指数成分 as-of 逐日重建（去幸存者偏差），输出股票代码列表供下游使用",
    example="自定义股票池 → 因子构建（公式） → IC 分析",
    notes=[
        "手工列表：股票代码用逗号分隔，如 000001.SZ,600000.SH",
        "指数成分(as-of逐日)：按指数历史成分快照重建逐日股票池，输出 membership 掩码（index=日期, columns=股票）避免幸存者偏差",
        "成分快照不足时回退为最新成分静态列表并在 assumptions 中明示（早于首次快照的区间仍有幸存者偏差）",
    ],
)
class StockPoolNode(BaseWorkNode):
    """定义股票选择范围（手工列表 / 指数成分 as-of）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return StockPoolInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return StockPoolOutput

    def run(self, input: StockPoolInput) -> Optional[BaseModel]:
        if input.mode.startswith("指数成分"):
            return self._index_membership(input.index_name.strip())
        codes = [c.strip() for c in input.stock_codes.split(",") if c.strip()]
        return StockPoolOutput(stock_list=codes, count=len(codes))

    @staticmethod
    def _index_membership(index_name: str) -> "StockPoolOutput":
        """按指数成分快照重建逐日股票池；快照不足时回退静态并标记假设"""
        from backend.services import reference_data

        if not index_name:
            raise ValueError("指数成分模式：请填写指数/板块名")
        mask = reference_data.load_index_membership(index_name)
        if mask is None or mask.empty:
            raise ValueError(
                f"无「{index_name}」的成分快照 — 请先在数据管理页按该指数批量下载以积累成分快照"
            )
        # 当前（最新快照）成分作为静态列表输出；完整逐日成员在 membership
        latest = mask.iloc[-1]
        codes = sorted(latest.index[latest].tolist())
        n_snapshots = len(mask.index)
        assumptions = [
            f"指数成分由快照积累（共 {n_snapshots} 个快照日），早于首次快照的区间仍为当前成分"
        ]
        return StockPoolOutput(
            stock_list=codes,
            count=len(codes),
            membership=mask,
            assumptions=assumptions,
        )


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


@work_node(
    name="公式输入",
    group="10-基础工具",
    box_color="#607D8B",
    description="对上游 DataFrame 按数学公式计算新列，公式中可直接引用列名（小写）",
    example="QMT行情数据 → 公式输入 → 数据筛选",
    notes=[
        "公式示例：df['close'] * 2 或 close / open - 1",
        "公式计算失败时输出列为 NaN，不会中断工作流",
    ],
)
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


@work_node(
    name="数据下载",
    group="10-基础工具",
    box_color="#607D8B",
    description="从 URL 下载数据文件到本地并读入为 DataFrame，支持 csv/parquet/excel/json",
    example="数据下载 → 数据筛选 → 因子构建",
    notes=[
        "未填保存路径时默认存到临时目录",
        "下载失败时 success 输出 false，不会中断工作流",
    ],
)
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
