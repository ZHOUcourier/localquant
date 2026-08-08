"""因子构建（分钟）节点 — 日内高频因子研究入口

分钟面板（清洗后）→ 分钟公式求值（ID_*/M_* 算子 + 现成高频因子）→
自动折叠为日频因子面板，输出与「因子构建（公式）」同构
（factor_data + return_data），下游 IC/分组/回测节点直接复用。
"""

from __future__ import annotations

from typing import Optional, Type

import pandas as pd
from pydantic import BaseModel, ConfigDict

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui


@ui(
    stock_pool={"input_type": "stock_picker"},
    start_date={"input_type": "date_picker"},
    end_date={"input_type": "date_picker"},
    period={"input_type": "combobox", "options": ["5m", "1m", "15m", "30m", "60m"]},
    formula={"input_type": "code_editor", "language": "python"},
    direction={"input_type": "combobox", "options": ["正向", "负向"]},
)
class IntradayFactorInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    stock_pool: list[str] = []
    start_date: str = ""
    end_date: str = ""
    period: str = "5m"
    formula: str = ""
    factor_name: str = "intraday_factor"
    direction: str = "正向"


class IntradayFactorOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None
    meta: Optional[dict] = None


@work_node(
    name="因子构建（分钟）",
    group="05-因子构建",
    box_color="#26A69A",
    description="基于分钟行情（5m/1m/15m...）计算日内高频因子：分钟面板自动清洗（竞价bar剔除/半日/一字标记）→ 公式求值 → 折叠为日频面板，下游与日频因子完全同构",
    example="因子构建（分钟）→ IC 计算 / 分组收益 / 回测",
    notes=[
        "数据自动加载：按股票池+区间从本地分钟缓存组装面板（需先在数据管理下载分钟行情）",
        "分钟字段：m_open/m_high/m_low/m_close/m_volume/m_amount（datetime×股票 面板）",
        "聚合算子：ID_LAST/ID_FIRST/ID_SUM/ID_MEAN/ID_MAX/ID_MIN/ID_STD/ID_QUANTILE/ID_COUNT/ID_SLICE；序列算子：M_DELAY/M_MA/M_SUM/M_STD/M_CUMSUM（按日分组不跨日）",
        "现成高频因子：TAIL_RET/OPEN_RET/RV/JUMP_DAY/AMIHUD5/VWAP_DEV/VOLUME_CLOCK/AUC_VOL_RATIO/LIMIT_UP_TIME/OVERNIGHT_RET/INTRADAY_RET",
        "公式结果为分钟级时自动 ID_LAST 折叠为日频；也可直接返回日频面板后套 RANK/ZSCORE 等日频算子",
        "示例：RANK(TAIL_RET(12)) — 尾盘动量因子；RANK(-RV(48)) — 已实现波动率反转",
        "周期建议 5m 起步（数据量与噪音平衡）；1m 数据量是 5m 的 5 倍，请评估磁盘占用",
    ],
)
class IntradayFactorNode(BaseWorkNode):
    """通过分钟公式构建日内高频因子（清洗 → 求值 → 折叠日频）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return IntradayFactorInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return IntradayFactorOutput

    def run(self, input: IntradayFactorInput) -> Optional[BaseModel]:
        from backend.services.intraday_cleaner import load_intraday_panels
        from backend.services.intraday_operators import (
            ID_LAST,
            build_intraday_namespace,
        )

        formula = (input.formula or "").strip()
        if not formula:
            raise ValueError(
                "分钟因子公式为空，示例：RANK(TAIL_RET(12)) / RANK(-RV(48)) / "
                "ID_MEAN(ID_SLICE(m_close, '14:00', '15:00'))"
            )

        loaded = load_intraday_panels(
            codes=input.stock_pool,
            period=input.period or "5m",
            start_date=input.start_date,
            end_date=input.end_date,
        )
        panels, meta = loaded["panels"], loaded["meta"]
        ns = build_intraday_namespace(panels, meta)

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
            raise ValueError(f"分钟因子公式计算失败: {e}") from e

        if isinstance(factor, pd.Series):
            factor = factor.to_frame(name=input.factor_name or "factor")
        if not isinstance(factor, pd.DataFrame) or factor.empty:
            raise ValueError(
                f"分钟公式结果应为 DataFrame/Series，得到 {type(factor).__name__}"
            )

        idx = pd.to_datetime(factor.index)
        if (idx.normalize() != idx).any():
            factor = ID_LAST(factor, 0)
        factor = factor.sort_index()

        if input.direction == "负向":
            factor = -factor

        # 日频收益面板（对次日/未来收益的 IC 口径与日频一致；
        # 前向填充口径：复牌日跳空收益计入）
        close = panels["close"]
        daily_close = close.groupby(close.index.normalize()).last().sort_index()
        daily_close = daily_close.reindex(factor.index, method="ffill").fillna(
            method="ffill"
        )
        from backend.services.market_data import build_return_panel

        return_data = build_return_panel(daily_close)

        return IntradayFactorOutput(
            factor_data=factor,
            return_data=return_data,
            meta={
                "period": loaded["period"],
                "cleaned": loaded["cleaned"],
                "n_stocks": int(factor.shape[1]),
                "start": str(factor.index[0].date()),
                "end": str(factor.index[-1].date()),
                "missing": loaded["missing"],
            },
        )
