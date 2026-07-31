"""因子研究 Pydantic 模型"""

from typing import Optional

from pydantic import BaseModel, Field


class FactorCreate(BaseModel):
    """注册因子"""

    name: str
    description: str = ""
    category: str = ""  # momentum/value/quality/volatility/technical
    formula: str = ""
    code: str = ""


class FactorResponse(BaseModel):
    """因子响应"""

    id: str
    name: str
    description: str
    category: str
    formula: str
    code: str
    version: int
    created_at: int
    updated_at: int

    class Config:
        from_attributes = True


class ICAnalysisRequest(BaseModel):
    """IC 分析请求"""

    factor_data: dict  # {date: {code: value}}
    return_data: dict  # {date: {code: return}}
    periods: list[int] = Field(default=[1, 5, 10, 20])


class QuantileRequest(BaseModel):
    """分层分析请求"""

    factor_data: dict
    return_data: dict
    n_groups: int = 5


class AlphaLensRequest(BaseModel):
    """AlphaLens 因子分析请求（调用 alphalens-reloaded 计算）"""

    factor_data: dict
    return_data: dict
    periods: list[int] = [1, 5, 10]
    quantiles: int = 5
    sector_map: dict = {}  # {股票代码: 行业名}；空则不做行业分组


class NeutralizeRequest(BaseModel):
    """中性化请求"""

    factor_data: dict
    industry_data: dict
    market_cap_data: dict


class CorrelationRequest(BaseModel):
    """相关性分析请求"""

    factors: dict[str, dict]  # {factor_name: {date: {code: value}}}
