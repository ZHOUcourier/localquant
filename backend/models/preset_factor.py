"""预置因子数据模型 - 对应参考网站 pandaaiquant.com 的因子数据"""


from pydantic import BaseModel, Field


class PresetFactorCategoryResponse(BaseModel):
    """因子分类响应模型"""

    id: int | None = None
    category_code: str = Field(..., alias="categoryCode", description="分类代码")
    category_name: str = Field(..., alias="categoryName", description="分类名称")
    color_hex: str | None = Field(None, alias="colorHex", description="分类颜色")
    factor_count: int = Field(0, alias="factorCount", description="该分类下因子数量")

    model_config = {"populate_by_name": True}


class PresetFactorResponse(BaseModel):
    """单个因子响应模型"""

    id: int | None = None
    factor_code: str = Field(..., alias="factorCode", description="因子代码")
    factor_name: str = Field(..., alias="factorName", description="因子名称")
    category_id: int | None = Field(None, alias="categoryId")
    category_code: str | None = Field(None, alias="categoryCode")
    category_name: str | None = Field(None, alias="categoryName")
    category_color_hex: str | None = Field(None, alias="categoryColorHex")
    description: str | None = Field(None, description="因子描述（含公式）")
    ic_mean: float | None = Field(None, alias="icMean")
    rank_ic: float | None = Field(None, alias="rankIc")
    ic_ir: float | None = Field(None, alias="icIr")
    ic_std: float | None = Field(None, alias="icStd")
    annualized_return: float | None = Field(None, alias="annualizedReturn")
    maximum_drawdown: float | None = Field(None, alias="maximumDrawdown")
    sharpe_ratio: float | None = Field(None, alias="sharpeRatio")
    turnover_rate: float | None = Field(None, alias="turnoverRate")
    start_date: str | None = Field(None, alias="startDate")
    data_date: str | None = Field(None, alias="dataDate")
    stock_pool: str | None = Field(None, alias="stockPool")
    is_preset: bool = Field(True, description="是否为预置因子")

    model_config = {"populate_by_name": True}


class PresetFactorListResponse(BaseModel):
    """因子分页列表响应"""

    total: int = 0
    page: int = 1
    page_size: int = 30
    items: list[PresetFactorResponse] = Field(default_factory=list)
