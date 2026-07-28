"""因子构建节点 — 公式/代码构建因子、标准化、中性化"""
import pandas as pd
import numpy as np
from pydantic import BaseModel, ConfigDict
from typing import Optional, Type

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui


# ────────────────────────── 1. 因子构建（公式） ──────────────────────────

@ui(
    stock_pool={"input_type": "stock_picker"},
    start_date={"input_type": "date_picker"},
    end_date={"input_type": "date_picker"},
    formula={"input_type": "code_editor", "language": "python"},
)
class FactorFormulaInput(BaseModel):
    stock_pool: list[str] = []
    start_date: str = "20200101"
    end_date: str = "20231231"
    formula: str = ""
    factor_name: str = "factor"


class FactorFormulaOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None


@work_node(name="因子构建（公式）", group="04-因子构建", box_color="#4CAF50")
class FactorFormulaNode(BaseWorkNode):
    """通过公式表达式构建因子"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorFormulaInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorFormulaOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        formula = params.get("formula", "")
        factor_name = params.get("factor_name", "factor")
        stock_pool = params.get("stock_pool", [])
        start_date = params.get("start_date", "20200101")
        end_date = params.get("end_date", "20231231")

        if not formula:
            return {"factor_data": pd.DataFrame()}

        # 尝试从上游获取数据
        data = params.get("data")
        if data is None or (isinstance(data, pd.DataFrame) and data.empty):
            # 无上游数据时返回空
            return {"factor_data": pd.DataFrame()}

        result = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame()

        # 在数据上下文中执行公式
        eval_ctx = {
            "df": result,
            "np": np,
            "pd": pd,
            "stock_pool": stock_pool,
            "start_date": start_date,
            "end_date": end_date,
        }
        for col in result.columns:
            eval_ctx[col.lower()] = result[col]

        try:
            expr_result = eval(formula, {"__builtins__": {}}, eval_ctx)  # noqa: S307
            if isinstance(expr_result, pd.DataFrame):
                return {"factor_data": expr_result}
            elif isinstance(expr_result, pd.Series):
                result[factor_name] = expr_result
                return {"factor_data": result}
            else:
                result[factor_name] = expr_result
                return {"factor_data": result}
        except Exception:
            return {"factor_data": pd.DataFrame()}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 2. 因子构建（代码） ──────────────────────────

@ui(code={"input_type": "code_editor", "language": "python"})
class FactorCodeInput(BaseModel):
    code: str = "# 请编写因子计算代码\n# 可用变量: df (DataFrame), np, pd\n# 返回: factor_data (DataFrame)\nfactor_data = df.copy()\n"
    factor_name: str = "factor"


class FactorCodeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None


@work_node(name="因子构建（代码）", group="04-因子构建", box_color="#4CAF50")
class FactorCodeNode(BaseWorkNode):
    """通过 Python 代码构建因子"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCodeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCodeOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        code = params.get("code", "")
        factor_name = params.get("factor_name", "factor")

        if not code:
            return {"factor_data": pd.DataFrame()}

        data = params.get("data")
        df = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame()

        exec_ctx = {
            "df": df,
            "np": np,
            "pd": pd,
            "factor_data": None,
        }

        try:
            exec(code, {"__builtins__": {"print": print, "range": range, "len": len,
                                          "list": list, "dict": dict, "set": set,
                                          "tuple": tuple, "int": int, "float": float,
                                          "str": str, "bool": bool, "abs": abs,
                                          "min": min, "max": max, "sum": sum,
                                          "enumerate": enumerate, "zip": zip,
                                          "map": map, "filter": filter}}, exec_ctx)  # noqa: S102
            factor_data = exec_ctx.get("factor_data")
            if isinstance(factor_data, pd.DataFrame):
                return {"factor_data": factor_data}
            elif isinstance(factor_data, pd.Series):
                return {"factor_data": factor_data.to_frame(name=factor_name)}
            else:
                return {"factor_data": df}
        except Exception:
            return {"factor_data": pd.DataFrame()}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 3. 因子标准化 ──────────────────────────

@ui(method={"input_type": "combobox", "options": ["zscore", "minmax", "rank"]})
class FactorStandardizeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    method: str = "zscore"
    factor_cols: list[str] = []  # 空 = 对所有数值列


class FactorStandardizeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None


@work_node(name="因子标准化", group="04-因子构建", box_color="#4CAF50")
class FactorStandardizeNode(BaseWorkNode):
    """因子标准化（Z-Score / MinMax / Rank）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorStandardizeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorStandardizeOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        factor_data: pd.DataFrame = params.get("factor_data")
        if factor_data is None or factor_data.empty:
            return {"factor_data": pd.DataFrame()}

        method = params.get("method", "zscore")
        factor_cols = params.get("factor_cols", [])
        result = factor_data.copy()

        # 确定要处理的列
        if not factor_cols:
            factor_cols = result.select_dtypes(include=[np.number]).columns.tolist()

        for col in factor_cols:
            if col not in result.columns:
                continue
            series = result[col].astype(float)
            if method == "zscore":
                mean, std = series.mean(), series.std()
                result[col] = (series - mean) / std if std != 0 else 0.0
            elif method == "minmax":
                mn, mx = series.min(), series.max()
                result[col] = (series - mn) / (mx - mn) if (mx - mn) != 0 else 0.0
            elif method == "rank":
                result[col] = series.rank(pct=True)

        return {"factor_data": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__


# ────────────────────────── 4. 因子中性化 ──────────────────────────

class FactorNeutralizeInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    industry_data: Optional[pd.DataFrame] = None
    market_cap_data: Optional[pd.DataFrame] = None
    factor_col: str = "factor"


class FactorNeutralizeOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None


@work_node(name="因子中性化", group="04-因子构建", box_color="#4CAF50")
class FactorNeutralizeNode(BaseWorkNode):
    """因子中性化（回归残差法）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorNeutralizeInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorNeutralizeOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        factor_data: pd.DataFrame = params.get("factor_data")
        if factor_data is None or factor_data.empty:
            return {"factor_data": pd.DataFrame()}

        industry_data: pd.DataFrame = params.get("industry_data")
        market_cap_data: pd.DataFrame = params.get("market_cap_data")
        factor_col = params.get("factor_col", "factor")

        result = factor_data.copy()
        y = result[factor_col].astype(float) if factor_col in result.columns else None
        if y is None:
            return {"factor_data": result}

        # 构建自变量矩阵 X
        X_parts = []

        # 行业哑变量
        if industry_data is not None and not industry_data.empty:
            # 取第一个数值列作为行业编码
            ind_col = industry_data.columns[0] if len(industry_data.columns) > 0 else None
            if ind_col:
                dummies = pd.get_dummies(industry_data[ind_col], prefix="ind", drop_first=True)
                dummies.index = result.index if len(dummies) == len(result) else None
                X_parts.append(dummies.astype(float))

        # 市值变量
        if market_cap_data is not None and not market_cap_data.empty:
            cap_col = market_cap_data.columns[0] if len(market_cap_data.columns) > 0 else None
            if cap_col:
                cap_series = market_cap_data[cap_col].astype(float)
                if len(cap_series) == len(result):
                    X_parts.append(cap_series.to_frame("log_cap").assign(
                        log_cap=lambda x: np.log(x["log_cap"].clip(lower=1))
                    ))

        if not X_parts:
            # 无行业/市值数据，仅去均值
            result[factor_col] = y - y.mean()
            return {"factor_data": result}

        X = pd.concat(X_parts, axis=1)
        # 对齐索引
        common_idx = result.index.intersection(X.index)
        if len(common_idx) == 0:
            return {"factor_data": result}

        y_aligned = y.loc[common_idx]
        X_aligned = X.loc[common_idx]

        # OLS 回归取残差
        try:
            X_with_const = X_aligned.copy()
            X_with_const["const"] = 1.0
            beta = np.linalg.lstsq(X_with_const.values, y_aligned.values, rcond=None)[0]
            residuals = y_aligned.values - X_with_const.values @ beta
            result.loc[common_idx, factor_col] = residuals
        except Exception:
            result[factor_col] = y - y.mean()

        return {"factor_data": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {**self.__dict__, **{k: v for k, v in inputs.items() if v is not None}}
        return self.__dict__
