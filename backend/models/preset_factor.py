"""预置因子数据模型 - 对应参考网站 pandaaiquant.com 的因子数据"""

from typing import Optional

from pydantic import BaseModel, Field


class PresetFactorCategoryResponse(BaseModel):
    """因子分类响应模型"""

    id: Optional[int] = None
    category_code: str = Field(..., alias="categoryCode", description="分类代码")
    category_name: str = Field(..., alias="categoryName", description="分类名称")
    color_hex: Optional[str] = Field(None, alias="colorHex", description="分类颜色")
    factor_count: int = Field(0, alias="factorCount", description="该分类下因子数量")

    model_config = {"populate_by_name": True}


class PresetFactorResponse(BaseModel):
    """单个因子响应模型"""

    id: Optional[int] = None
    factor_code: str = Field(..., alias="factorCode", description="因子代码")
    factor_name: str = Field(..., alias="factorName", description="因子名称")
    category_id: Optional[int] = Field(None, alias="categoryId")
    category_code: Optional[str] = Field(None, alias="categoryCode")
    category_name: Optional[str] = Field(None, alias="categoryName")
    category_color_hex: Optional[str] = Field(None, alias="categoryColorHex")
    description: Optional[str] = Field(None, description="因子描述（含公式）")
    ic_mean: Optional[float] = Field(None, alias="icMean")
    rank_ic: Optional[float] = Field(None, alias="rankIc")
    ic_ir: Optional[float] = Field(None, alias="icIr")
    ic_std: Optional[float] = Field(None, alias="icStd")
    annualized_return: Optional[float] = Field(None, alias="annualizedReturn")
    maximum_drawdown: Optional[float] = Field(None, alias="maximumDrawdown")
    sharpe_ratio: Optional[float] = Field(None, alias="sharpeRatio")
    turnover_rate: Optional[float] = Field(None, alias="turnoverRate")
    start_date: Optional[str] = Field(None, alias="startDate")
    data_date: Optional[str] = Field(None, alias="dataDate")
    stock_pool: Optional[str] = Field(None, alias="stockPool")
    is_preset: bool = Field(True, description="是否为预置因子")

    model_config = {"populate_by_name": True}


class PresetFactorListResponse(BaseModel):
    """因子分页列表响应"""

    total: int = 0
    page: int = 1
    page_size: int = 30
    items: list[PresetFactorResponse] = Field(default_factory=list)
