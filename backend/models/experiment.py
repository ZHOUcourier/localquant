"""实验记录 Pydantic 模型"""
from pydantic import BaseModel, Field
from typing import Optional


class ExperimentCreate(BaseModel):
    """创建实验记录"""
    source: str  # workflow/factor/backtest/explore
    source_id: str = ""
    name: str = ""
    note: str = ""
    tags: list[str] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    """实验记录响应"""
    id: str
    source: str
    source_id: str
    name: str
    note: str
    tags: list[str]
    params: dict
    metrics: dict
    status: str
    created_at: int

    class Config:
        from_attributes = True


class ExperimentCompareRequest(BaseModel):
    """实验对比请求"""
    experiment_ids: list[str]


class ExperimentCompareResponse(BaseModel):
    """实验对比响应"""
    experiments: list[ExperimentResponse]
    param_diffs: dict = Field(default_factory=dict)
    metric_comparison: dict = Field(default_factory=dict)
