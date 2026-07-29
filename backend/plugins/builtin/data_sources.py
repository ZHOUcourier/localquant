# QMT 数据获取节点
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field

from backend.plugins.base import BaseWorkNode
from backend.plugins.registry import work_node
from backend.plugins.ui_control import ui

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
    kline_data: dict = Field(default_factory=dict, title="K线数据")

    class Config:
        arbitrary_types_allowed = True


@work_node(
    name="QMT行情数据",
    group="01-数据获取",
    box_color="orange",
    description="获取QMT行情K线数据，支持日K/周K/月K/分钟K等多种周期，输出按股票代码组织的K线字典",
    example="QMT行情数据 → 因子构建 / 技术指标 / 回测",
    notes=[
        "需本地有 QMT 行情缓存或 QMT 客户端在线，否则返回空数据",
        "输出 kline_data 为 {股票代码: K线字典} 结构，只能通过连线传给下游",
        "股票代码用逗号分隔，如 000001.SZ,600000.SH",
    ],
)
class QMTKlineNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return QMTKlineInput

    @classmethod
    def output_model(cls):
        return QMTKlineOutput

    def run(self, input: BaseModel) -> Optional[BaseModel]:
        from backend.data import qmt_client

        codes = [c.strip() for c in input.code_list.split(",") if c.strip()]
        if not codes:
            return QMTKlineOutput(kline_data={})

        data = qmt_client.get_kline(
            codes,
            input.period,
            input.start_date,
            input.end_date,
            dividend_type=input.dividend_type,
        )
        result = {}
        for code, df in data.items():
            result[code] = df.to_dict()
        return QMTKlineOutput(kline_data=result)


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

    def run(self, input: BaseModel) -> Optional[BaseModel]:
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

    def run(self, input: BaseModel) -> Optional[BaseModel]:
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

    def run(self, input: BaseModel) -> Optional[BaseModel]:
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
        "placeholder": "留空获取全市场，填写板块名获取板块成分股",
    },
)
class StockListInput(BaseModel):
    sector: str = Field(default="", title="板块名称(可选)")


class StockListOutput(BaseModel):
    stock_list: list = Field(default_factory=list, title="股票列表")
    count: int = Field(default=0, title="数量")


@work_node(
    name="股票列表",
    group="01-数据获取",
    box_color="orange",
    description="获取股票列表：填写板块名返回板块成分股，留空时返回板块列表供筛选",
    example="股票列表 → QMT行情数据",
    notes=[
        "留空时当前实现返回的是板块列表（非全市场股票），建议填写板块名使用",
    ],
)
class StockListNode(BaseWorkNode):
    @classmethod
    def input_model(cls):
        return StockListInput

    @classmethod
    def output_model(cls):
        return StockListOutput

    def run(self, input: BaseModel) -> Optional[BaseModel]:
        from backend.data import qmt_client

        if input.sector.strip():
            stocks = qmt_client.get_sector_stocks(input.sector.strip())
        else:
            # 获取全市场：先获取所有板块再汇总去重，或直接返回板块列表
            # 这里使用板块列表作为 fallback
            sectors = qmt_client.get_sector_list()
            stocks = sectors  # 无板块筛选时返回板块列表供后续使用

        return StockListOutput(stock_list=stocks, count=len(stocks))
