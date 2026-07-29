"""因子构建节点 — 公式/代码构建因子、标准化(权重调整)、中性化

设计要点（对齐官网「线性因子构建 / 自定义因子构建 / 因子权重调整」的功能）：
- 因子构建节点可独立运行：给定股票池 + 时间区间即从 QMT 行情面板计算因子，
  无需强制上游数据；也可接收上游已构建好的因子面板继续加工。
- 公式/代码求值环境注入全部量化算子（RANK/DELAY/CORR/TS_RANK/DECAYLINEAR...）与
  基础字段（open/high/low/close/volume/amount/vwap），因子库 Alpha 公式可直接运行。
- 支持因子方向（正向/负向），负向自动取相反数。
- 同时输出 return_data（次日收益面板），供下游 IC/分组收益节点直接消费。

所有数据均来自 QMT 行情缓存，绝不引入 QMT 以外的数据源。
"""

from typing import Optional, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui
from backend.services import market_data
from backend.services.factor_operators import build_operator_namespace


def _build_eval_ns(
    data: Optional[pd.DataFrame],
    stock_pool: list[str],
    start_date: str,
    end_date: str,
) -> tuple[dict, Optional[pd.DataFrame]]:
    """构建公式/代码求值命名空间

    优先使用上游传入的行情面板字典（若 data 为面板则并入）；否则按股票池+区间
    从 QMT 行情缓存加载 open/high/low/close/volume/amount 面板。

    Returns:
        (namespace, close_panel)；close_panel 用于计算 return_data，可能为 None。
    """
    # 上游若直接给了一个面板 DataFrame（index=date, columns=stock），作为 close 兜底
    panels = market_data.load_price_panels(
        codes=stock_pool or [],
        start_date=start_date,
        end_date=end_date,
    )
    ns = build_operator_namespace(panels)
    if isinstance(data, pd.DataFrame) and not data.empty:
        # 允许上游面板作为额外变量 df 参与公式（不覆盖基础字段）
        ns["df"] = data
    return ns, panels.get("close")


def _apply_direction(factor: pd.DataFrame, direction: str) -> pd.DataFrame:
    """因子方向：负向取相反数（不改变结构）"""
    if direction in ("负向", "negative", "-1", "0"):
        return -factor
    return factor


# ────────────────────────── 1. 因子构建（公式） ──────────────────────────


@ui(
    stock_pool={"input_type": "stock_picker"},
    start_date={"input_type": "date_picker"},
    end_date={"input_type": "date_picker"},
    formula={"input_type": "code_editor", "language": "python"},
    direction={"input_type": "combobox", "options": ["正向", "负向"]},
    data={"input_type": "None"},
)
class FactorFormulaInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    # 可选上游行情/因子面板；留空则按股票池+区间从 QMT 加载
    data: Optional[pd.DataFrame] = None
    stock_pool: list[str] = []
    start_date: str = "20200101"
    end_date: str = "20231231"
    formula: str = ""
    factor_name: str = "factor"
    direction: str = "正向"


class FactorFormulaOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None


@work_node(
    name="因子构建（公式）",
    group="05-因子构建",
    box_color="#4CAF50",
    description="在指定股票池与时间区间内，用公式表达式基于 QMT 行情面板计算因子；求值环境内置全部量化算子，因子库 Alpha 公式可直接粘贴运行",
    example="自定义股票池 → 因子构建（公式） → IC 计算 / 分组收益",
    notes=[
        "数据自动加载：按股票池+区间从 QMT 缓存组装为面板 DataFrame（index=交易日, columns=股票代码）",
        "可用字段：open/high/low/close/volume/amount/vwap/returns/adv20；算子：RANK/DELAY/CORR/TS_RANK/SLOPE/RSI 等全部官网函数（大小写均可）",
        "公式示例：RANK(close / DELAY(close, 5) - 1)；支持多行，取最后一行为因子值",
        "股票池留空时使用本地全部已缓存股票；无行情数据会给出明确报错",
        "因子方向为负向时对结果取相反数；同时输出 return_data 供下游分析",
    ],
)
class FactorFormulaNode(BaseWorkNode):
    """通过公式表达式构建因子（基于 QMT 行情面板，内置算子）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorFormulaInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorFormulaOutput

    def run(self, input: FactorFormulaInput) -> Optional[BaseModel]:
        formula = (input.formula or "").strip()
        if not formula:
            raise ValueError(
                "因子公式为空，请输入表达式，如：RANK(close / DELAY(close, 5) - 1)"
            )

        ns, close = _build_eval_ns(
            input.data, input.stock_pool, input.start_date, input.end_date
        )

        # 支持多行公式：前 n-1 行作为中间变量执行，最后一行作为因子值
        lines = [
            ln
            for ln in formula.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        try:
            if len(lines) > 1:
                exec("\n".join(lines[:-1]), {"__builtins__": {}}, ns)  # noqa: S102
                factor = eval(lines[-1], {"__builtins__": {}}, ns)  # noqa: S307
            else:
                factor = eval(formula, {"__builtins__": {}}, ns)  # noqa: S307
        except Exception as e:
            raise ValueError(f"因子公式计算失败: {e}") from e

        if isinstance(factor, pd.Series):
            factor = factor.to_frame(name=input.factor_name or "factor")
        if not isinstance(factor, pd.DataFrame):
            raise ValueError(
                f"公式结果应为 DataFrame/Series，得到 {type(factor).__name__}"
            )

        factor = _apply_direction(factor.dropna(how="all"), input.direction)
        return_data = close.pct_change() if close is not None else None
        return FactorFormulaOutput(factor_data=factor, return_data=return_data)


# ────────────────────────── 2. 因子构建（代码） ──────────────────────────


@ui(
    stock_pool={"input_type": "stock_picker"},
    start_date={"input_type": "date_picker"},
    end_date={"input_type": "date_picker"},
    code={"input_type": "code_editor", "language": "python"},
    direction={"input_type": "combobox", "options": ["正向", "负向"]},
    data={"input_type": "None"},
)
class FactorCodeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    stock_pool: list[str] = []
    start_date: str = "20200101"
    end_date: str = "20231231"
    code: str = (
        "# 数据已自动加载为「面板 DataFrame」：index=交易日(DatetimeIndex), columns=股票代码\n"
        "# 可用字段: open/high/low/close/volume/amount/vwap/returns/adv20（大小写均可）\n"
        "# 可用算子: RANK/DELAY/DELTA/CORR/STD/TS_RANK/DECAYLINEAR/SLOPE/RSI 等全部官网函数\n"
        "# 可用 print(close.shape) / print(close.tail()) 查看数据，输出在运行日志中\n"
        "# 最后把结果（面板 DataFrame）赋值给 factor_data\n"
        "factor_data = RANK(close / DELAY(close, 20) - 1)\n"
    )
    factor_name: str = "factor"
    direction: str = "正向"


class FactorCodeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None


@work_node(
    name="因子构建（代码）",
    group="05-因子构建",
    box_color="#4CAF50",
    description="用自定义 Python 代码基于 QMT 行情面板构建复杂因子；代码需把结果写入 factor_data（或 df_factor），求值环境内置全部量化算子",
    example="自定义股票池 → 因子构建（代码） → IC 计算",
    notes=[
        "数据自动加载：按股票池+区间从 QMT 缓存组装为面板 DataFrame（index=交易日, columns=股票代码），无需自行读数据",
        "可用字段：open/high/low/close/volume/amount/vwap/returns/adv20；算子同公式节点（大小写均可）",
        "可用 print(close.shape)、print(close.tail()) 检查数据，输出显示在运行日志；需对 factor_data 或 df_factor 赋值",
        "股票池留空时使用本地全部已缓存股票；仅支持受限内置函数；同时输出 return_data 供下游分析",
    ],
)
class FactorCodeNode(BaseWorkNode):
    """通过 Python 代码构建因子（基于 QMT 行情面板，内置算子）"""

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
        "True": True,
        "False": False,
        "None": None,
    }

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCodeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCodeOutput

    def run(self, input: FactorCodeInput) -> Optional[BaseModel]:
        code = (input.code or "").strip()
        if not code:
            raise ValueError("因子代码为空，请编写代码并把结果写入 factor_data")

        ns, close = _build_eval_ns(
            input.data, input.stock_pool, input.start_date, input.end_date
        )
        ns["factor_data"] = None
        ns["df_factor"] = None
        try:
            exec(code, {"__builtins__": self._SAFE_BUILTINS}, ns)  # noqa: S102
        except Exception as e:
            raise ValueError(f"因子代码执行失败: {e}") from e

        factor = ns.get("factor_data")
        if factor is None:
            factor = ns.get("df_factor")
        if isinstance(factor, pd.Series):
            factor = factor.to_frame(name=input.factor_name or "factor")
        if not isinstance(factor, pd.DataFrame):
            raise ValueError(
                "代码未生成 factor_data / df_factor（应为 DataFrame 或 Series）"
            )

        factor = _apply_direction(factor.dropna(how="all"), input.direction)
        return_data = close.pct_change() if close is not None else None
        return FactorCodeOutput(factor_data=factor, return_data=return_data)


# ────────────────────────── 3. 因子标准化 / 权重调整 ──────────────────────────


@ui(
    method={"input_type": "combobox", "options": ["zscore", "minmax", "rank"]},
    weight={"input_type": "number_field"},
    factor_data={"input_type": "None"},
)
class FactorStandardizeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    method: str = "zscore"
    weight: float = 1.0
    factor_cols: list[str] = []  # 空 = 对所有数值列


class FactorStandardizeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None


@work_node(
    name="因子标准化",
    group="05-因子构建",
    box_color="#4CAF50",
    description="对因子列做 Z-Score/MinMax/Rank 标准化并按权重缩放（对齐官网「因子权重调整（归一化）」）",
    example="因子构建 → 因子标准化 → 多因子合成 / IC 计算",
    notes=[
        "factor_data 需连线自上游因子构建节点（面板 DataFrame）",
        "factor_cols 留空时对全部数值列处理；标准化后乘以 weight",
        "weight 支持负值用于反向；标准差为 0 的列仅做权重缩放",
    ],
)
class FactorStandardizeNode(BaseWorkNode):
    """因子标准化 + 权重调整（Z-Score / MinMax / Rank）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorStandardizeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorStandardizeOutput

    def run(self, input: FactorStandardizeInput) -> Optional[BaseModel]:
        factor_data = input.factor_data
        if (
            factor_data is None
            or not isinstance(factor_data, pd.DataFrame)
            or factor_data.empty
        ):
            raise ValueError(
                "因子标准化：未接收到有效的 factor_data（请连线上游因子构建节点）"
            )

        method = input.method or "zscore"
        weight = float(input.weight if input.weight is not None else 1.0)
        result = factor_data.copy()
        cols = (
            input.factor_cols
            or result.select_dtypes(include=[np.number]).columns.tolist()
        )

        for col in cols:
            if col not in result.columns:
                continue
            series = result[col].astype(float)
            if method == "zscore":
                std = series.std()
                result[col] = ((series - series.mean()) / std if std else 0.0) * weight
            elif method == "minmax":
                mn, mx = series.min(), series.max()
                rng = mx - mn
                result[col] = ((series - mn) / rng if rng else 0.0) * weight
            elif method == "rank":
                result[col] = series.rank(pct=True) * weight
            else:
                result[col] = series * weight

        return FactorStandardizeOutput(factor_data=result)


# ────────────────────────── 4. 因子中性化 ──────────────────────────


@ui(
    factor_col={"input_type": "text_field"},
    factor_data={"input_type": "None"},
    industry_data={"input_type": "None"},
    market_cap_data={"input_type": "None"},
)
class FactorNeutralizeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    industry_data: Optional[pd.DataFrame] = None
    market_cap_data: Optional[pd.DataFrame] = None
    factor_col: str = "factor"


class FactorNeutralizeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None


@work_node(
    name="因子中性化",
    group="05-因子构建",
    box_color="#4CAF50",
    description="用行业哑变量/对数市值对因子做 OLS 回归取残差，剥离风格暴露；行业与市值数据可来自 QMT 板块/财务数据",
    example="因子标准化 → 因子中性化 → IC 计算",
    notes=[
        "factor_data 必连；industry_data / market_cap_data 为可选连线输入",
        "都未提供时仅做截面去均值；行业数据取第一列作行业编码，市值取对数参与回归",
    ],
)
class FactorNeutralizeNode(BaseWorkNode):
    """因子中性化（回归残差法）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorNeutralizeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorNeutralizeOutput

    def run(self, input: FactorNeutralizeInput) -> Optional[BaseModel]:
        factor_data = input.factor_data
        if (
            factor_data is None
            or not isinstance(factor_data, pd.DataFrame)
            or factor_data.empty
        ):
            raise ValueError("因子中性化：未接收到有效的 factor_data")

        factor_col = input.factor_col or "factor"
        result = factor_data.copy()
        if factor_col not in result.columns:
            # 面板因子：无指定列时按行(截面)去均值中性化
            return FactorNeutralizeOutput(
                factor_data=result.sub(result.mean(axis=1), axis=0)
            )

        y = result[factor_col].astype(float)
        X_parts = []
        industry_data = input.industry_data
        market_cap_data = input.market_cap_data

        if isinstance(industry_data, pd.DataFrame) and not industry_data.empty:
            ind_col = industry_data.columns[0]
            dummies = pd.get_dummies(
                industry_data[ind_col], prefix="ind", drop_first=True
            )
            if len(dummies) == len(result):
                dummies.index = result.index
                X_parts.append(dummies.astype(float))

        if isinstance(market_cap_data, pd.DataFrame) and not market_cap_data.empty:
            cap_col = market_cap_data.columns[0]
            cap = market_cap_data[cap_col].astype(float)
            if len(cap) == len(result):
                cap.index = result.index
                X_parts.append(np.log(cap.clip(lower=1)).to_frame("log_cap"))

        if not X_parts:
            result[factor_col] = y - y.mean()
            return FactorNeutralizeOutput(factor_data=result)

        X = pd.concat(X_parts, axis=1)
        common_idx = result.index.intersection(X.index)
        if len(common_idx) == 0:
            result[factor_col] = y - y.mean()
            return FactorNeutralizeOutput(factor_data=result)

        y_a = y.loc[common_idx]
        X_a = X.loc[common_idx].copy()
        X_a["const"] = 1.0
        try:
            beta = np.linalg.lstsq(X_a.values, y_a.values, rcond=None)[0]
            result.loc[common_idx, factor_col] = y_a.values - X_a.values @ beta
        except Exception:
            result[factor_col] = y - y.mean()

        return FactorNeutralizeOutput(factor_data=result)
