"""因子分析节点 — IC / 分组收益 / 相关性 / 衰减 / 多因子合成"""

from typing import Optional, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui

# ────────────────────────── 1. IC 计算 ──────────────────────────


@ui(
    periods={"input_type": "text_field"},
    method={"input_type": "combobox", "options": ["rank_ic", "normal_ic"]},
)
class ICInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None
    factor_col: str = "factor"
    periods: str = "1,5,10,20"
    method: str = "rank_ic"


class ICOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    ic_result: Optional[pd.DataFrame] = None


@work_node(
    name="IC 计算",
    group="05-因子分析",
    box_color="#FF9800",
    description="计算因子IC/RankIC，评估因子预测能力",
)
class ICNode(BaseWorkNode):
    """计算因子 IC / Rank IC 序列"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return ICInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return ICOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        factor_data: pd.DataFrame = params.get("factor_data")
        return_data: pd.DataFrame = params.get("return_data")
        if factor_data is None or return_data is None:
            return {"ic_result": pd.DataFrame()}
        if factor_data.empty or return_data.empty:
            return {"ic_result": pd.DataFrame()}

        factor_col = params.get("factor_col", "factor")
        method = params.get("method", "rank_ic")
        periods_str = params.get("periods", "1,5,10,20")
        periods = [int(p.strip()) for p in periods_str.split(",") if p.strip()]

        results = {}
        for period in periods:
            # 对齐索引
            common_idx = factor_data.index.intersection(return_data.index)
            if len(common_idx) == 0:
                continue

            f = (
                factor_data.loc[common_idx, factor_col].astype(float)
                if factor_col in factor_data.columns
                else pd.Series(dtype=float)
            )
            # 取第 period 列作为远期收益
            ret_cols = [c for c in return_data.columns if str(period) in c]
            if ret_cols:
                r = return_data.loc[common_idx, ret_cols[0]].astype(float)
            elif len(return_data.columns) > 0:
                r = return_data.iloc[:, 0].astype(float)
            else:
                continue

            # 计算 IC
            if method == "rank_ic":
                ic = f.rank().corr(r.rank())
            else:
                ic = f.corr(r)
            results[f"IC_{period}"] = ic

        ic_df = pd.DataFrame([results])
        return {"ic_result": ic_df}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {
                **self.__dict__,
                **{k: v for k, v in inputs.items() if v is not None},
            }
        return self.__dict__


# ────────────────────────── 2. 分组收益 ──────────────────────────


@ui(n_groups={"input_type": "number_field"})
class GroupReturnInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None
    factor_col: str = "factor"
    n_groups: int = 5


class GroupReturnOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    group_return: Optional[pd.DataFrame] = None


@work_node(
    name="分组收益",
    group="05-因子分析",
    box_color="#FF9800",
    description="按因子值分组计算各组收益率，分析因子单调性",
)
class GroupReturnNode(BaseWorkNode):
    """按因子值分组计算分层收益"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return GroupReturnInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return GroupReturnOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        factor_data: pd.DataFrame = params.get("factor_data")
        return_data: pd.DataFrame = params.get("return_data")
        if factor_data is None or return_data is None:
            return {"group_return": pd.DataFrame()}
        if factor_data.empty or return_data.empty:
            return {"group_return": pd.DataFrame()}

        factor_col = params.get("factor_col", "factor")
        n_groups = int(params.get("n_groups", 5))

        if factor_col not in factor_data.columns:
            return {"group_return": pd.DataFrame()}

        common_idx = factor_data.index.intersection(return_data.index)
        f = factor_data.loc[common_idx, factor_col].astype(float)
        ret_col = return_data.columns[0] if len(return_data.columns) > 0 else None
        if ret_col is None:
            return {"group_return": pd.DataFrame()}
        r = return_data.loc[common_idx, ret_col].astype(float)

        # 分组
        try:
            groups = pd.qcut(
                f,
                q=n_groups,
                labels=[f"G{i + 1}" for i in range(n_groups)],
                duplicates="drop",
            )
        except Exception:
            return {"group_return": pd.DataFrame()}

        result_df = pd.DataFrame({"factor": f, "return": r, "group": groups})
        group_means = result_df.groupby("group")["return"].mean()

        return {"group_return": group_means.to_frame("mean_return")}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {
                **self.__dict__,
                **{k: v for k, v in inputs.items() if v is not None},
            }
        return self.__dict__


# ────────────────────────── 3. 因子相关性 ──────────────────────────


class FactorCorrelationInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factors: Optional[pd.DataFrame] = None  # 多列因子数据
    method: str = "pearson"


class FactorCorrelationOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    correlation_matrix: Optional[pd.DataFrame] = None


@work_node(
    name="因子相关性",
    group="05-因子分析",
    box_color="#FF9800",
    description="计算多因子间的相关性矩阵，辅助因子筛选",
)
class FactorCorrelationNode(BaseWorkNode):
    """计算多因子之间的相关性矩阵"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCorrelationInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCorrelationOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        factors: pd.DataFrame = params.get("factors")
        if factors is None or factors.empty:
            return {"correlation_matrix": pd.DataFrame()}

        method = params.get("method", "pearson")
        numeric_df = factors.select_dtypes(include=[np.number])
        corr = numeric_df.corr(method=method)
        return {"correlation_matrix": corr}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {
                **self.__dict__,
                **{k: v for k, v in inputs.items() if v is not None},
            }
        return self.__dict__


# ────────────────────────── 4. 因子衰减 ──────────────────────────


@ui(max_period={"input_type": "number_field"})
class FactorDecayInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None
    factor_col: str = "factor"
    max_period: int = 20


class FactorDecayOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    decay_result: Optional[pd.DataFrame] = None


@work_node(
    name="因子衰减",
    group="05-因子分析",
    box_color="#FF9800",
    description="分析因子IC随时间衰减速率，确定调仓周期",
)
class FactorDecayNode(BaseWorkNode):
    """计算因子 IC 随持有期的衰减序列"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorDecayInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorDecayOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        factor_data: pd.DataFrame = params.get("factor_data")
        return_data: pd.DataFrame = params.get("return_data")
        if factor_data is None or return_data is None:
            return {"decay_result": pd.DataFrame()}
        if factor_data.empty or return_data.empty:
            return {"decay_result": pd.DataFrame()}

        factor_col = params.get("factor_col", "factor")
        max_period = int(params.get("max_period", 20))

        if factor_col not in factor_data.columns:
            return {"decay_result": pd.DataFrame()}

        f = factor_data[factor_col].astype(float)
        decay_records = []

        for period in range(1, max_period + 1):
            ret_cols = [c for c in return_data.columns if str(period) in c]
            if ret_cols:
                r = return_data[ret_cols[0]].astype(float)
            elif len(return_data.columns) > 0:
                r = return_data.iloc[:, 0].astype(float)
            else:
                continue

            common_idx = f.index.intersection(r.index)
            if len(common_idx) < 2:
                continue
            ic = f.loc[common_idx].rank().corr(r.loc[common_idx].rank())
            decay_records.append({"period": period, "IC": ic})

        decay_df = pd.DataFrame(decay_records)
        return {"decay_result": decay_df}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {
                **self.__dict__,
                **{k: v for k, v in inputs.items() if v is not None},
            }
        return self.__dict__


# ────────────────────────── 5. 多因子合成 ──────────────────────────


@ui(
    method={
        "input_type": "combobox",
        "options": ["weighted_sum", "equal_weight", "ic_weighted"],
    },
)
class FactorCombineInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factors: Optional[pd.DataFrame] = None  # 多列因子数据
    weights: dict[str, float] = Field(default_factory=dict)  # 因子名 -> 权重
    method: str = "weighted_sum"
    output_name: str = "combined_factor"


class FactorCombineOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    combined_factor: Optional[pd.DataFrame] = None


@work_node(
    name="多因子合成",
    group="05-因子分析",
    box_color="#FF9800",
    description="将多个因子按权重合成为综合因子",
)
class FactorCombineNode(BaseWorkNode):
    """多因子合成（加权求和 / 等权 / IC 加权）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCombineInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCombineOutput

    def run(self, ctx) -> dict:
        params = self._get_params(ctx)
        factors: pd.DataFrame = params.get("factors")
        if factors is None or factors.empty:
            return {"combined_factor": pd.DataFrame()}

        method = params.get("method", "weighted_sum")
        output_name = params.get("output_name", "combined_factor")
        weights = params.get("weights", {})

        numeric_df = factors.select_dtypes(include=[np.number])
        result = factors.copy()

        if method == "equal_weight":
            result[output_name] = numeric_df.mean(axis=1)
        elif method == "weighted_sum":
            combined = pd.Series(0.0, index=numeric_df.index)
            for col in numeric_df.columns:
                w = weights.get(col, 1.0 / len(numeric_df.columns))
                combined += numeric_df[col] * w
            result[output_name] = combined
        elif method == "ic_weighted":
            # IC 加权需要 return_data，此处退化为等权
            result[output_name] = numeric_df.mean(axis=1)
        else:
            result[output_name] = numeric_df.mean(axis=1)

        return {"combined_factor": result}

    def _get_params(self, ctx) -> dict:
        if hasattr(ctx, "_pending_inputs") and hasattr(ctx, "_node_id"):
            inputs = ctx._pending_inputs.get(ctx._node_id, {})
            return {
                **self.__dict__,
                **{k: v for k, v in inputs.items() if v is not None},
            }
        return self.__dict__
