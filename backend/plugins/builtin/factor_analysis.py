"""因子分析节点 — IC / 分组收益 / 相关性 / 衰减 / 多因子合成

关键设计：
- 修正调用约定 —— run(self, input) 直接读取 input 字段（此前 _get_params 读取
  空的 self.__dict__，导致节点在工作流中恒为空，属底层缺陷，已修复）。
- 因子分析节点直接复用 factor_research 服务的截面计算逻辑，保证「工作流因子分析节点」
  与「因子研究页」结果完全一致。
- 输入 factor_data / return_data 均为面板 DataFrame（index=交易日, columns=股票代码），
  由上游「因子构建」节点产出；数据全部源自 QMT 行情，绝不引入外部数据。
"""

from typing import Optional, Type

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui
from backend.services.factor_research import factor_research

# 因子分析（综合报告）—— 对齐官网单个「因子分析」节点，一个节点产出完整报告


@ui(
    periods={"input_type": "text_field"},
    n_groups={"input_type": "number_field"},
    method={"input_type": "combobox", "options": ["rank_ic", "normal_ic"]},
    factor_data={"input_type": "None"},
    return_data={"input_type": "None"},
)
class FactorAnalysisInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None
    periods: str = "1,5,10,20"
    n_groups: int = 5
    method: str = "rank_ic"


class FactorAnalysisOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    summary: Optional[dict] = (
        None  # 数据卡指标（因子收益/夏普/IC/Rank_IC/t/p/单调性等）
    )
    group_perf: Optional[pd.DataFrame] = (
        None  # 分组绩效表（含多空组合、超额、跟踪误差、信息比率）
    )
    ic_summary: Optional[pd.DataFrame] = None  # 各周期 IC 汇总
    group_cumulative: Optional[pd.DataFrame] = None  # 各组累计收益曲线
    group_excess_cumulative: Optional[pd.DataFrame] = None  # 各组超额累计收益
    ic_series: Optional[pd.DataFrame] = None  # IC / Rank_IC 逐日时序
    ic_cumulative: Optional[pd.DataFrame] = None  # IC / Rank_IC 累计
    ic_decay: Optional[pd.DataFrame] = None  # IC / Rank_IC 衰减
    ic_distribution: Optional[pd.DataFrame] = None  # IC / Rank_IC 分布直方图
    ic_autocorr: Optional[pd.DataFrame] = None  # IC / Rank_IC 自相关
    latest_ranking: Optional[pd.DataFrame] = None  # 最新一期因子值排名


@work_node(
    name="因子分析",
    group="06-因子分析",
    box_color="#FF9800",
    description="对因子做一站式截面分析，输出 IC 统计/时序、IC 衰减、分层平均与累计收益、多空曲线、换手率与关键指标（与因子研究页同源、结果一致）",
    example="因子构建（公式） → 因子分析 → 输出",
    notes=[
        "factor_data / return_data 均需从上游因子构建节点连线（面板：index=日期, columns=股票）",
        "一个节点即输出完整报告；periods 多周期逗号分隔，n_groups 为分层数",
        "与右侧“因子研究”页使用同一套 factor_research 服务，口径完全一致",
    ],
)
class FactorAnalysisNode(BaseWorkNode):
    """一站式因子分析（复用 factor_research.full_factor_analysis）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorAnalysisInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorAnalysisOutput

    def run(self, input: FactorAnalysisInput) -> Optional[BaseModel]:
        if not _valid(input.factor_data) or not _valid(input.return_data):
            raise ValueError(
                "因子分析：需要上游连线提供 factor_data 与 return_data（面板 DataFrame）"
            )

        periods = [
            int(p.strip())
            for p in (input.periods or "1,5,10,20").split(",")
            if p.strip()
        ]
        rep = factor_research.full_factor_analysis(
            input.factor_data,
            input.return_data,
            periods,
            int(input.n_groups or 5),
            input.method or "rank_ic",
        )
        ic_rep, ric_rep = rep["ic"], rep["rank_ic"]

        def _wide(mapping: dict) -> pd.DataFrame:
            """{列名: {date: value}} → 宽表（index=日期）"""
            if not mapping:
                return pd.DataFrame()
            df = pd.DataFrame({k: pd.Series(v) for k, v in mapping.items()})
            return df.sort_index() if not df.empty else df

        # IC / Rank_IC 时序、累计
        ic_series = _wide({"IC": ic_rep["series"], "Rank_IC": ric_rep["series"]})
        ic_cumulative = _wide(
            {"IC_累计": ic_rep["cumulative"], "Rank_IC_累计": ric_rep["cumulative"]}
        )

        # 衰减：IC 与 Rank_IC 合并一表
        decay_rows = []
        ic_decay_map = {d["period"]: d["ic"] for d in ic_rep["decay"]}
        ric_decay_map = {d["period"]: d["ic"] for d in ric_rep["decay"]}
        for p in sorted(set(ic_decay_map) | set(ric_decay_map)):
            decay_rows.append(
                {
                    "period": p,
                    "IC": ic_decay_map.get(p),
                    "Rank_IC": ric_decay_map.get(p),
                }
            )

        # 分布直方图（含偏度/峰度）
        ic_dist, ric_dist = ic_rep["distribution"], ric_rep["distribution"]
        dist_df = (
            pd.DataFrame(
                {
                    "ic_bin": ic_dist["centers"],
                    "ic_count": ic_dist["counts"],
                }
            )
            if ic_dist["centers"]
            else pd.DataFrame()
        )

        # 自相关
        ac_rows = []
        ic_ac = {d["lag"]: d["acf"] for d in ic_rep["autocorr"]}
        ric_ac = {d["lag"]: d["acf"] for d in ric_rep["autocorr"]}
        for lag in sorted(set(ic_ac) | set(ric_ac)):
            ac_rows.append(
                {"lag": lag, "IC": ic_ac.get(lag), "Rank_IC": ric_ac.get(lag)}
            )

        # 数据卡（中文标签，对齐官网）
        s = rep["summary"]
        summary = {
            "因子收益": round(s["factor_return"], 4),
            "年化收益": round(s["annual_return"], 4),
            "夏普比率": round(s["sharpe_ratio"], 4),
            "最大回撤": round(s["max_drawdown"], 4),
            "IC_mean": round(s["ic_mean"], 4),
            "Rank_IC": round(s["rank_ic"], 4),
            "IC_std": round(s["ic_std"], 4),
            "IC_IR": round(s["ic_ir"], 4),
            "IR": round(s["ir"], 4),
            "P(IC<-0.02)": round(s["p_ic_lt_neg"], 4),
            "P(IC>0.02)": round(s["p_ic_gt_pos"], 4),
            "t统计量": round(s["t_stat"], 4),
            "p-value": round(s["p_value"], 4),
            "单调性": round(s["monotonicity"], 4),
        }

        return FactorAnalysisOutput(
            summary=summary,
            group_perf=pd.DataFrame(rep["group_perf"]),
            ic_summary=pd.DataFrame(rep["ic_summary"]),
            group_cumulative=_wide(rep["group_cumulative"]),
            group_excess_cumulative=_wide(rep["group_excess_cumulative"]),
            ic_series=ic_series,
            ic_cumulative=ic_cumulative,
            ic_decay=pd.DataFrame(decay_rows),
            ic_distribution=dist_df,
            ic_autocorr=pd.DataFrame(ac_rows),
            latest_ranking=pd.DataFrame(rep["latest"]),
        )


# ────────────────────────── 1. IC 计算 ──────────────────────────


@ui(
    periods={"input_type": "text_field"},
    method={"input_type": "combobox", "options": ["rank_ic", "normal_ic"]},
    factor_data={"input_type": "None"},
    return_data={"input_type": "None"},
)
class ICInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None
    periods: str = "1,5,10,20"
    method: str = "rank_ic"


class ICOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    ic_result: Optional[pd.DataFrame] = (
        None  # 各周期 IC 汇总（均值/标准差/ICIR/t值/胜率）
    )
    ic_series: Optional[pd.DataFrame] = None  # 逐日 IC 时序（AlphaLens 风格）


@work_node(
    name="IC 计算",
    group="06-因子分析",
    box_color="#FF9800",
    description="对因子面板做截面 IC/RankIC 分析，输出各预测周期的 IC 汇总（均值/标准差/ICIR/t值/胜率）与逐日 IC 时序；与因子研究页同源计算",
    example="因子构建（公式） → IC 计算 → 输出",
    notes=[
        "factor_data / return_data 均需从上游因子构建节点连线（面板：index=日期, columns=股票）",
        "periods 支持多周期（逗号分隔），按 T 日因子对 T+period 日收益做截面相关",
        "method: rank_ic（斯皮尔曼）或 normal_ic（皮尔逊）",
    ],
)
class ICNode(BaseWorkNode):
    """截面 IC / RankIC 分析（复用 factor_research 服务）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return ICInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return ICOutput

    def run(self, input: ICInput) -> Optional[BaseModel]:
        factor_data = input.factor_data
        return_data = input.return_data
        if not _valid(factor_data) or not _valid(return_data):
            raise ValueError(
                "IC 计算：需要上游连线提供 factor_data 与 return_data（面板 DataFrame）"
            )

        periods = [
            int(p.strip())
            for p in (input.periods or "1,5,10,20").split(",")
            if p.strip()
        ]
        result = factor_research.ic_analysis(factor_data, return_data, periods)

        # 汇总表 + 逐日时序（method 决定取 ic 还是 rank_ic）
        use_rank = (input.method or "rank_ic") == "rank_ic"
        summary_rows, series_cols = [], {}
        for period in periods:
            item = result.get(f"period_{period}")
            if not item:
                continue
            summary_rows.append(
                {
                    "period": period,
                    "ic_mean": item.get("rank_ic_mean" if use_rank else "ic_mean", 0.0),
                    "ic_std": item.get("ic_std", 0.0),
                    "ic_ir": item.get("rank_ic_ir" if use_rank else "ic_ir", 0.0),
                    "ic_tstat": item.get("ic_tstat", 0.0),
                    "positive_ratio": item.get("ic_positive_ratio", 0.0),
                }
            )
            key = "rank_ic_series" if use_rank else "ic_series"
            val_key = "rank_ic" if use_rank else "ic"
            s = {
                r["date"][:10]: r[val_key]
                for r in item.get(key, [])
                if r.get(val_key) is not None
            }
            if s:
                series_cols[f"IC_{period}"] = pd.Series(s)

        return ICOutput(
            ic_result=pd.DataFrame(summary_rows),
            ic_series=pd.DataFrame(series_cols).sort_index()
            if series_cols
            else pd.DataFrame(),
        )


# ────────────────────────── 2. 分组收益 ──────────────────────────


@ui(
    n_groups={"input_type": "number_field"},
    factor_data={"input_type": "None"},
    return_data={"input_type": "None"},
)
class GroupReturnInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None
    n_groups: int = 5


class GroupReturnOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    group_return: Optional[pd.DataFrame] = None  # 各组平均单期收益
    group_cumulative: Optional[pd.DataFrame] = None  # 各组累计收益曲线
    group_stats: Optional[pd.DataFrame] = None  # 多空价差/单调性


@work_node(
    name="分组收益",
    group="06-因子分析",
    box_color="#FF9800",
    description="按因子值截面分位数分组，输出各组平均收益、累计收益曲线与多空价差/单调性；与因子研究页同源计算",
    example="因子构建（公式） → 分组收益 → 输出",
    notes=[
        "factor_data / return_data 均需从上游因子构建节点连线（面板）",
        "n_groups 为分组数量（如 5/10），按每日截面因子值等分",
        "多空价差 = 最高组累计收益 - 最低组累计收益；单调性衡量分层有序程度",
    ],
)
class GroupReturnNode(BaseWorkNode):
    """截面分组收益分析（复用 factor_research 服务）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return GroupReturnInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return GroupReturnOutput

    def run(self, input: GroupReturnInput) -> Optional[BaseModel]:
        factor_data = input.factor_data
        return_data = input.return_data
        if not _valid(factor_data) or not _valid(return_data):
            raise ValueError(
                "分组收益：需要上游连线提供 factor_data 与 return_data（面板 DataFrame）"
            )

        n_groups = int(input.n_groups or 5)
        res = factor_research.quantile_analysis(factor_data, return_data, n_groups)

        # 各组平均单期收益
        mrbg = res.get("mean_return_by_group", {})
        group_return = pd.DataFrame(
            [
                {"group": g, "mean_return": v}
                for g, v in sorted(mrbg.items(), key=lambda x: int(x[0]))
            ]
        )

        # 各组累计收益曲线
        cum_cols = {}
        for key, series in (res.get("cumulative_series") or {}).items():
            label = key.replace("group_", "G")
            cum_cols[label] = pd.Series(
                {p["date"][:10]: p["cum_return"] for p in series}
            )
        group_cumulative = (
            pd.DataFrame(cum_cols).sort_index() if cum_cols else pd.DataFrame()
        )

        # 多空价差与单调性
        ls_series = res.get("long_short_series", [])
        long_short = ls_series[-1]["cum_return"] if ls_series else 0.0
        group_stats = pd.DataFrame(
            [
                {
                    "n_groups": res.get("n_groups", n_groups),
                    "long_short_return": long_short,
                    "monotonicity": res.get("monotonicity", 0.0),
                }
            ]
        )

        return GroupReturnOutput(
            group_return=group_return,
            group_cumulative=group_cumulative,
            group_stats=group_stats,
        )


# ────────────────────────── 3. 因子相关性 ──────────────────────────


@ui(
    method={"input_type": "combobox", "options": ["pearson", "spearman"]},
    factors={"input_type": "None"},
)
class FactorCorrelationInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factors: Optional[pd.DataFrame] = None  # 多列因子数据（每列一个因子）
    method: str = "pearson"


class FactorCorrelationOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    correlation_matrix: Optional[pd.DataFrame] = None


@work_node(
    name="因子相关性",
    group="06-因子分析",
    box_color="#FF9800",
    description="计算多列因子间的相关性矩阵（pearson/spearman），辅助剔除冗余因子",
    example="多因子合成 → 因子相关性 → 输出",
    notes=[
        "factors 需连线提供一个多列 DataFrame（每列一个因子）",
        "仅对数值列计算；至少 2 个因子才有意义",
    ],
)
class FactorCorrelationNode(BaseWorkNode):
    """多因子相关性矩阵"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCorrelationInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCorrelationOutput

    def run(self, input: FactorCorrelationInput) -> Optional[BaseModel]:
        factors = input.factors
        if not _valid(factors):
            raise ValueError("因子相关性：需要连线提供多列因子 DataFrame")
        numeric_df = factors.select_dtypes(include=[np.number])
        corr = numeric_df.corr(method=input.method or "pearson")
        return FactorCorrelationOutput(correlation_matrix=corr)


# ────────────────────────── 4. 因子衰减 ──────────────────────────


@ui(
    max_period={"input_type": "number_field"},
    factor_data={"input_type": "None"},
    return_data={"input_type": "None"},
)
class FactorDecayInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    factor_data: Optional[pd.DataFrame] = None
    return_data: Optional[pd.DataFrame] = None
    max_period: int = 20


class FactorDecayOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    decay_result: Optional[pd.DataFrame] = None


@work_node(
    name="因子衰减",
    group="06-因子分析",
    box_color="#FF9800",
    description="计算因子截面 IC 随持有期增长的衰减序列，辅助确定调仓周期；与因子研究页同源计算",
    example="因子构建（公式） → 因子衰减 → 输出",
    notes=[
        "factor_data / return_data 均需连线提供（面板）",
        "max_period 为最大持有期；输出各持有期的平均 IC",
    ],
)
class FactorDecayNode(BaseWorkNode):
    """因子 IC 随持有期衰减（复用 factor_research 服务）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorDecayInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorDecayOutput

    def run(self, input: FactorDecayInput) -> Optional[BaseModel]:
        factor_data = input.factor_data
        return_data = input.return_data
        if not _valid(factor_data) or not _valid(return_data):
            raise ValueError(
                "因子衰减：需要连线提供 factor_data 与 return_data（面板）"
            )
        res = factor_research.factor_decay(
            factor_data, return_data, int(input.max_period or 20)
        )
        return FactorDecayOutput(decay_result=pd.DataFrame(res.get("decay_series", [])))


# ────────────────────────── 5. 多因子合成 ──────────────────────────


@ui(
    method={
        "input_type": "combobox",
        "options": ["weighted_sum", "equal_weight", "ic_weighted"],
    },
    factors={"input_type": "None"},
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
    group="06-因子分析",
    box_color="#FF9800",
    description="将多列因子按权重加权求和或等权合成为综合因子列",
    example="因子标准化 → 多因子合成 → IC 计算",
    notes=[
        "factors 需连线提供多列因子 DataFrame；建议先标准化再合成",
        "ic_weighted 需收益数据支持，当前退化为等权；weights 未指定的因子默认等权",
    ],
)
class FactorCombineNode(BaseWorkNode):
    """多因子合成（加权求和 / 等权 / IC 加权）"""

    @classmethod
    def input_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCombineInput

    @classmethod
    def output_model(cls) -> Optional[Type[BaseModel]]:
        return FactorCombineOutput

    def run(self, input: FactorCombineInput) -> Optional[BaseModel]:
        factors = input.factors
        if not _valid(factors):
            raise ValueError("多因子合成：需要连线提供多列因子 DataFrame")

        method = input.method or "weighted_sum"
        output_name = input.output_name or "combined_factor"
        weights = input.weights or {}

        numeric_df = factors.select_dtypes(include=[np.number])
        result = factors.copy()
        n = max(len(numeric_df.columns), 1)

        if method == "weighted_sum":
            combined = pd.Series(0.0, index=numeric_df.index)
            for col in numeric_df.columns:
                combined += numeric_df[col] * weights.get(col, 1.0 / n)
            result[output_name] = combined
        else:  # equal_weight / ic_weighted(退化等权)
            result[output_name] = numeric_df.mean(axis=1)

        return FactorCombineOutput(combined_factor=result)


def _valid(df) -> bool:
    return isinstance(df, pd.DataFrame) and not df.empty
