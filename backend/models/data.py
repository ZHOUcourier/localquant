"""数据相关 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional


class DataDownloadRequest(BaseModel):
    """数据下载请求"""
    codes: list[str]
    period: str = "1d"
    start_time: str = ""
    end_time: str = ""


class DataStatusResponse(BaseModel):
    """数据状态响应"""
    qmt_connected: bool
    qmt_message: str
    cache_stats: dict
    cache_dir: str


class MarketScanRequest(BaseModel):
    """全市场扫描请求"""
    date: str
    conditions: list[str] = Field(default_factory=list)  # 如 ["pe<15", "roe>15"]


class CrossSectionRequest(BaseModel):
    """横截面分析请求"""
    date: str
    field: str
    codes: Optional[list[str]] = None


class AnomalyRequest(BaseModel):
    """异常检测请求"""
    code: str
    field: str
    window: int = 20
    threshold: float = 2.0


class QualityCheckRequest(BaseModel):
    """数据质量检查请求"""
    codes: list[str]
    period: str = "1d"
