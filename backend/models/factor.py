"""因子研究 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional


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


class NeutralizeRequest(BaseModel):
    """中性化请求"""
    factor_data: dict
    industry_data: dict
    market_cap_data: dict


class CorrelationRequest(BaseModel):
    """相关性分析请求"""
    factors: dict[str, dict]  # {factor_name: {date: {code: value}}}
