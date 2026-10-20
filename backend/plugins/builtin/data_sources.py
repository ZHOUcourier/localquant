# QMT 数据获取节点

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui
from backend.services.universe_policy import UniversePolicy, filter_codes_today

_DEFAULT_POLICY = UniversePolicy.from_settings()

# ============================================================
# 1. QMT K线数据节点
# ============================================================


@ui(
    code_list={"input_type": "text_field", "placeholder": "000001.SZ,600000.SH"},
    period={
        "input_type": "combobox",
        "options": ["1d", "1w", "1mon", "1m", "5m", "15m", "30m", "1h"],
    },
    start_date={"input_type": "date_picker"},
    end_date={"input_type": "date_picker"},
    dividend_type={"input_type": "combobox", "options": ["front", "back", "none"]},
)
class QMTKlineInput(BaseModel):
    code_list: str = Field(default="", title="股票代码(逗号分隔)")
    period: str = Field(default="1d", title="周期")
    start_date: str = Field(default="20200101", title="开始日期")
    end_date: str = Field(default="", title="结束日期")
    dividend_type: str = Field(default="front", title="复权方式")


class QMTKlineOutput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    # 面板 DataFrame（index=交易日, columns=股票代码），可直接连线给回测/因子节点
    open: pd.DataFrame | None = None
    high: pd.DataFrame | None = None
    low: pd.DataFrame | None = None
    close: pd.DataFrame | None = None
    volume: pd.DataFrame | None = None
    amount: pd.DataFrame | None = None
    # 兼容旧连线：{字段: {日期: {代码: 值}}}
    kline_data: dict = Field(default_factory=dict, title="K线数据(兼容)")


@work_node(
    name="QMT行情数据",
    group="01-数据获取",
    box_color="orange",
    description="获取行情K线并组装为面板（本地缓存优先，QMT 在线时增量补齐），输出 open/high/low/close/volume/amount 面板供下游连线",
    example="QMT行情数据 → 因子构建 / 技术指标 / 回测",
    notes=[
        "本地缓存优先：无 QMT 连接时也能从 data/cache 缓存读取；股票代码留空时取该周期全部本地缓存标的",
        "输出 open/high/low/close/volume/amount 面板（index=交易日, columns=股票代码），可直接连线给回测/因子节点",
        "股票代码用逗号分隔，如 000001.SZ,600000.SH；无缓存且无 QMT 时给出明确报错",
    ],
)
class QMTKlineNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return QMTKlineInput

    @classmethod
    def output_model(cls):
        return QMTKlineOutput

    def run(self, input: BaseModel) -> BaseModel | None:
        from backend.services import market_data

        codes = [c.strip() for c in input.code_list.split(",") if c.strip()]
        if not codes:
            codes = market_data.list_cached_codes(input.period, exclude_indices=True)
        if not codes:
            raise ValueError(
                "QMT行情：股票代码为空且本地无该周期缓存 — "
                "请先在数据管理下载行情，或在 code_list 填入代码"
            )

        adjust = {"front": "qfq", "back": "hfq", "none": "none"}.get(
            input.dividend_type, "qfq"
        )
        panels = market_data.load_price_panels(
            codes=codes,
            start_date=input.start_date,
            end_date=input.end_date,
            period=input.period,
            adjust=adjust,
        )
        close = panels.get("close")
        if close is None or close.empty:
            raise ValueError("QMT行情：未取到行情数据，请先下载缓存或连接 QMT")

        kline_data = {
            field: market_data.panel_to_dict(panel)
            for field, panel in panels.items()
            if panel is not None
        }
        return QMTKlineOutput(
            open=panels.get("open"),
            high=panels.get("high"),
            low=panels.get("low"),
            close=close,
            volume=panels.get("volume"),
            amount=panels.get("amount"),
            kline_data=kline_data,
        )


# ============================================================
# 2. QMT 财务数据节点
# ============================================================


@ui(
    code_list={"input_type": "text_field", "placeholder": "000001.SZ,600000.SH"},
    tables={
        "input_type": "combobox",
        "options": [
            "Balance",
            "Income",
            "CashFlow",
            "Top10Holders",
            "Capital",
            "PerShare",
            "Valuation",
        ],
    },
    start_date={"input_type": "date_picker"},
    end_date={"input_type": "date_picker"},
)
class QMTFinancialInput(BaseModel):
    code_list: str = Field(default="", title="股票代码(逗号分隔)")
    tables: str = Field(default="Balance,Income,CashFlow", title="财务表(逗号分隔)")
    start_date: str = Field(default="20200101", title="开始日期")
    end_date: str = Field(default="", title="结束日期")


class QMTFinancialOutput(BaseModel):
    financial_data: dict = Field(default_factory=dict, title="财务数据")

    class Config:
        arbitrary_types_allowed = True


@work_node(
    name="QMT财务数据",
    group="01-数据获取",
    box_color="orange",
    description="获取QMT财务报表数据，包括资产负债表、利润表、现金流量表、估值等多张表",
    example="QMT财务数据 → 合并数据 → 因子构建（代码）",
    notes=[
        "可选表：Balance/Income/CashFlow/Top10Holders/Capital/PerShare/Valuation",
        "输出 financial_data 为嵌套字典，只能通过连线传给下游",
    ],
)
class QMTFinancialNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return QMTFinancialInput

    @classmethod
    def output_model(cls):
        return QMTFinancialOutput

    def run(self, input: BaseModel) -> BaseModel | None:
        from backend.data import qmt_client

        codes = [c.strip() for c in input.code_list.split(",") if c.strip()]
        tables = [t.strip() for t in input.tables.split(",") if t.strip()]
        if not codes:
            return QMTFinancialOutput(financial_data={})

        raw = qmt_client.get_financial(
            codes,
            tables=tables,
            start_time=input.start_date,
            end_time=input.end_date,
        )
        # 将 DataFrame 值转为 dict 以便序列化
        result = {}
        for key, val in raw.items():
            if isinstance(val, pd.DataFrame):
                result[key] = val.to_dict()
            else:
                result[key] = val
        return QMTFinancialOutput(financial_data=result)


# ============================================================
# 3. QMT 板块数据节点
# ============================================================


@ui(
    sector_name={
        "input_type": "text_field",
        "placeholder": "留空获取板块列表，填写板块名获取成分股",
    },
)
class QMTSectorInput(BaseModel):
    sector_name: str = Field(default="", title="板块名称(留空=板块列表)")


class QMTSectorOutput(BaseModel):
    sector_list: list = Field(default_factory=list, title="板块/成分股列表")
    mode: str = Field(default="", title="返回模式")


@work_node(
    name="QMT板块数据",
    group="01-数据获取",
    box_color="orange",
    description="获取QMT板块列表或指定板块的成分股列表",
    example="QMT板块数据 → QMT行情数据（按成分股拉行情）",
    notes=[
        "板块名留空时返回全部板块列表，填写板块名时返回该板块成分股",
        "mode 输出字段标识返回的是板块列表还是成分股",
    ],
)
class QMTSectorNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return QMTSectorInput

    @classmethod
    def output_model(cls):
        return QMTSectorOutput

    def run(self, input: BaseModel) -> BaseModel | None:
        from backend.data import qmt_client

        if input.sector_name.strip():
            stocks = qmt_client.get_sector_stocks(input.sector_name.strip())
            return QMTSectorOutput(sector_list=stocks, mode="sector_stocks")
        else:
            sectors = qmt_client.get_sector_list()
            return QMTSectorOutput(sector_list=sectors, mode="sector_list")


# ============================================================
# 4. 交易日历节点
# ============================================================


@ui(
    market={"input_type": "combobox", "options": ["SH", "SZ"]},
    start_date={"input_type": "date_picker"},
    end_date={"input_type": "date_picker"},
)
class TradingCalendarInput(BaseModel):
    market: str = Field(default="SH", title="市场")
    start_date: str = Field(default="20200101", title="开始日期")
    end_date: str = Field(default="", title="结束日期")


class TradingCalendarOutput(BaseModel):
    trading_dates: list = Field(default_factory=list, title="交易日列表")


@work_node(
    name="交易日历",
    group="01-数据获取",
    box_color="orange",
    description="获取A股交易日历，输出指定区间内的交易日列表",
    example="交易日历 → Python代码输入（按交易日对齐数据）",
    notes=[
        "需本地 QMT 数据支持，无数据时返回空列表",
    ],
)
class TradingCalendarNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return TradingCalendarInput

    @classmethod
    def output_model(cls):
        return TradingCalendarOutput

    def run(self, input: BaseModel) -> BaseModel | None:
        from backend.data import qmt_client

        dates = qmt_client.get_trading_dates(
            market=input.market,
            start_time=input.start_date,
            end_time=input.end_date,
        )
        return TradingCalendarOutput(trading_dates=dates)


# ============================================================
# 5. 股票列表节点
# ============================================================


@ui(
    sector={
        "input_type": "text_field",
        "placeholder": "留空获取全市场A股，填写板块名获取板块成分股",
    },
    exclude_st={"input_type": "boolean"},
    exclude_new={"input_type": "boolean"},
    min_list_days={"input_type": "number_field"},
    include_bj={"input_type": "boolean"},
    exclude_delisting={"input_type": "boolean"},
)
class StockListInput(BaseModel):
    sector: str = Field(default="", title="板块名称(可选)")
    exclude_st: bool = Field(default=_DEFAULT_POLICY.exclude_st, title="剔除ST")
    exclude_new: bool = Field(default=_DEFAULT_POLICY.exclude_new, title="剔除次新")
    min_list_days: int = Field(
        default=_DEFAULT_POLICY.min_list_days, title="上市至少天数"
    )
    include_bj: bool = Field(default=_DEFAULT_POLICY.include_bj, title="包含北交所")
    exclude_delisting: bool = Field(
        default=_DEFAULT_POLICY.exclude_delisting, title="剔除退市整理期"
    )


class StockListOutput(BaseModel):
    stock_list: list = Field(default_factory=list, title="股票列表")
    count: int = Field(default=0, title="数量")
    excluded_counts: dict = Field(default_factory=dict, title="按原因剔除数量")
    assumptions: list = Field(default_factory=list, title="假设与覆盖警告")


@work_node(
    name="股票列表",
    group="01-数据获取",
    box_color="orange",
    description="获取股票列表：填写板块名返回板块成分股，留空返回全市场A股；默认剔除ST/*ST、上市不足两年、退市整理期，可包含北交所",
    example="股票列表 → QMT行情数据",
    notes=[
        "留空时返回全市场A股（优先沪深A股板块，回退各市场A股并集）；填写板块名返回该板块成分股",
        "默认约束：exclude_st=true / exclude_new=true / min_list_days=730（自然日）/ include_bj=true / exclude_delisting=true；取自设置页全局默认，可在节点上单次覆盖",
        "ST/退市/上市日取自 instrument 合约快照（需先在数据管理页下载并积累快照）；无快照时过滤不生效，assumptions 会明确提示",
        "这是“当前选股”口径；历史回测请使用工作流回测节点内置的逐日 as-of 约束，不能把今天的名称状态回溯历史",
    ],
)
class StockListNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return StockListInput

    @classmethod
    def output_model(cls):
        return StockListOutput

    def run(self, input: BaseModel) -> BaseModel | None:
        from backend.data import qmt_client

        if input.sector.strip():
            stocks = qmt_client.get_sector_stocks(input.sector.strip())
        else:
            # 留空 → 全市场 A 股（聚合各市场 A 股板块并集）
            stocks = qmt_client.get_all_a_stocks()

        stocks = self._apply_filters(
            stocks,
            exclude_st=input.exclude_st,
            exclude_new=input.exclude_new,
            min_list_days=input.min_list_days,
            include_bj=input.include_bj,
            exclude_delisting=input.exclude_delisting,
        )
        return StockListOutput(
            stock_list=stocks[0],
            count=len(stocks[0]),
            excluded_counts=stocks[1].stats.get("excluded_last_date_by_reason", {}),
            assumptions=stocks[1].warnings,
        )

    @staticmethod
    def _apply_filters(
        stocks: list[str],
        *,
        exclude_st: bool,
        exclude_new: bool,
        min_list_days: int,
        include_bj: bool,
        exclude_delisting: bool,
    ):
        """按今天的最新快照过滤静态股票列表，返回 (保留列表, mask result)。

        注意：这是“当前选股”口径；历史回测必须用逐日 mask，不能把今天的
        ST/退市状态回溯到整段历史。
        """
        if not stocks:
            from backend.services.universe_policy import UniverseMaskResult

            policy = UniversePolicy(
                exclude_st=exclude_st,
                exclude_new=exclude_new,
                min_list_days=min_list_days,
                include_bj=include_bj,
                exclude_delisting=exclude_delisting,
            )
            return [], UniverseMaskResult(
                mask=pd.DataFrame(), policy=policy, warnings=[]
            )
        policy = UniversePolicy(
            exclude_st=exclude_st,
            exclude_new=exclude_new,
            min_list_days=min_list_days,
            include_bj=include_bj,
            exclude_delisting=exclude_delisting,
        )
        return filter_codes_today(stocks, policy)
