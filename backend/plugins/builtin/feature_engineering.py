"""特征工程节点 — 特征构建、变换、选择"""

from typing import Optional, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui

# ============================================================
# 8. 特征工程构建节点
# ============================================================


@ui(
    feature_cols={
        "input_type": "text_field",
        "placeholder": "特征列名(逗号分隔)，留空则使用全部数值列",
    },
    target_col={"input_type": "text_field", "placeholder": "目标列名(可选)"},
    method={
        "input_type": "combobox",
        "options": ["standardize", "normalize", "pca", "none"],
    },
    lag_periods={
        "input_type": "text_field",
        "placeholder": "滞后阶数(逗号分隔)，如 1,3,5,10",
    },
    data={"input_type": "None"},
)
class FeatureEngineeringInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    feature_cols: str = Field(default="", title="特征列名(逗号分隔)")
    target_col: str = Field(default="", title="目标列名(可选)")
    method: str = Field(default="standardize", title="特征变换方法")
    lag_periods: str = Field(default="", title="滞后阶数(逗号分隔)")
    add_rolling: bool = Field(default=False, title="是否添加滚动统计量")
    rolling_windows: str = Field(default="5,10,20", title="滚动窗口(逗号分隔)")


class FeatureEngineeringOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    data: Optional[pd.DataFrame] = None
    feature_names: list = Field(default_factory=list, title="特征名列表")


@work_node(
    name="特征工程构建",
    group="02-特征工程",
    box_color="#9C27B0",
    description="基于原始数据自动构建多类特征因子，包括技术指标、统计量、时序特征等",
)
class FeatureEngineeringNode(BaseWorkNode):
    """输入DataFrame，配置特征列和参数，输出特征矩阵"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FeatureEngineeringInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FeatureEngineeringOutput

    def run(self, input: FeatureEngineeringInput) -> Optional[BaseModel]:
        df = input.data
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return FeatureEngineeringOutput(data=pd.DataFrame(), feature_names=[])

        result = df.copy()

        # 确定特征列
        if input.feature_cols.strip():
            feat_cols = [c.strip() for c in input.feature_cols.split(",") if c.strip()]
            feat_cols = [c for c in feat_cols if c in result.columns]
        else:
            feat_cols = result.select_dtypes(include=[np.number]).columns.tolist()

        if input.target_col.strip() and input.target_col in result.columns:
            feat_cols = [c for c in feat_cols if c != input.target_col]

        new_cols = {}

        # 滞后特征
        if input.lag_periods.strip():
            lags = [int(l.strip()) for l in input.lag_periods.split(",") if l.strip()]
            for col in feat_cols:
                for lag in lags:
                    new_cols[f"{col}_lag{lag}"] = result[col].shift(lag)

        # 滚动统计量
        if input.add_rolling:
            windows = [
                int(w.strip()) for w in input.rolling_windows.split(",") if w.strip()
            ]
            for col in feat_cols:
                for w in windows:
                    new_cols[f"{col}_roll_mean_{w}"] = result[col].rolling(w).mean()
                    new_cols[f"{col}_roll_std_{w}"] = result[col].rolling(w).std()

        # 添加新列
        for name, series in new_cols.items():
            result[name] = series

        # 更新特征列名
        all_feature_names = feat_cols + list(new_cols.keys())

        # 特征变换
        method = input.method
        for col in feat_cols + list(new_cols.keys()):
            if col not in result.columns:
                continue
            series = result[col].astype(float)
            if method == "standardize":
                mean, std = series.mean(), series.std()
                result[col] = (series - mean) / std if std != 0 else 0.0
            elif method == "normalize":
                mn, mx = series.min(), series.max()
                result[col] = (series - mn) / (mx - mn) if (mx - mn) != 0 else 0.0

        # 去除 NaN 行
        result = result.dropna()

        return FeatureEngineeringOutput(data=result, feature_names=all_feature_names)
