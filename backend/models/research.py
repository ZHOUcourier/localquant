"""本地研究预注册请求；不联网、不推断或翻转研究员指定的因子方向。"""

import re
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def normalize_codes(codes: list[str]) -> list[str]:
    """规范化普通 A 股代码（裸六码可推断市场），去重并保留首次出现顺序。"""
    # 对外统一 ValueError，供 Pydantic 和主路由映射请求错误。
    if not isinstance(codes, list):
        raise ValueError("codes must be a list of A-share codes")  # noqa: TRY004
    result = []
    seen = set()
    for value in codes:
        if not isinstance(value, str):
            raise ValueError("codes must contain strings")  # noqa: TRY004
        code = value.strip().upper()
        match = re.fullmatch(r"([0-9]{6})(?:\.(SH|SZ|BJ))?", code)
        if not match:
            raise ValueError(f"Invalid A-share code: {value!r}")
        number, supplied_market = match.groups()
        if number.startswith(("600", "601", "603", "605", "688", "689")):
            market = "SH"
        elif number.startswith(("000", "001", "002", "003", "300", "301", "302")):
            market = "SZ"
        elif number.startswith(("4", "8", "92")):
            market = "BJ"
        else:
            raise ValueError(f"Not an ordinary A-share code: {value!r}")
        if supplied_market is not None and supplied_market != market:
            raise ValueError(f"A-share exchange mismatch: {value!r}")
        normalized = f"{number}.{market}"
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


class ResearchProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    start_date: str
    train_end: str
    validation_end: str
    end_date: str
    codes: list[str] = Field(default_factory=list)
    horizon: int = Field(default=5, ge=1, le=60)
    top_n: int = Field(default=20, ge=1, le=1000)
    rebalance_days: int = Field(default=5, ge=1, le=252)
    alpha: float = Field(default=0.05, gt=0, le=0.2)
    trial_budget: int = Field(default=20, ge=1, le=1000)
    min_dates: int = Field(default=60, ge=20, le=1000)
    min_stocks: int = Field(default=30, ge=10, le=10000)
    commission_rate: float = Field(default=0.001, ge=0, le=0.1)
    slippage: float = Field(default=0.001, ge=0, le=0.1)
    stamp_tax: float = Field(default=0.0005, ge=0, le=0.1)
    initial_capital: float = Field(default=1_000_000, gt=0)
    baseline_formulas: list[NonEmptyText] = Field(default_factory=list, max_length=10)
    candidate_weight: float = Field(default=0.25, gt=0, le=1)
    monitor_window: int = Field(default=60, ge=20)
    review_every: int = Field(default=20, ge=1)
    # 每日成本后相对收益的最小实用增量，不是 IC 阈值；允许有限负数。
    minimum_effect: float = 0
    regime_index: str = "000300.SH"
    regime_shrinkage: int = Field(default=60, ge=1)

    @field_validator("start_date", "train_end", "validation_end", "end_date")
    @classmethod
    def validate_iso_date(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Dates must use YYYY-MM-DD")
        date.fromisoformat(value)
        return value

    @field_validator("codes")
    @classmethod
    def validate_codes(cls, value: list[str]) -> list[str]:
        return normalize_codes(value)

    @field_validator("regime_index")
    @classmethod
    def validate_regime_index(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"(?:000[0-9]{3}\.SH|399[0-9]{3}\.SZ|899[0-9]{3}\.BJ)", value):
            raise ValueError("regime_index must be a QMT index code")
        return value

    @model_validator(mode="after")
    def validate_date_order(self) -> Self:
        if not self.start_date < self.train_end < self.validation_end < self.end_date:
            raise ValueError(
                "Require start_date < train_end < validation_end < end_date"
            )
        return self


class StudyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonEmptyText = Field(max_length=160)
    hypothesis: NonEmptyText = Field(max_length=4000)
    sources: list[NonEmptyText] = Field(min_length=1, max_length=20)
    protocol: ResearchProtocol


class TrialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula: NonEmptyText = Field(max_length=4000)
    direction: Literal[-1, 1] = 1
    rationale: NonEmptyText = Field(max_length=4000)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: Literal["validation", "holdout", "monitor"] = "validation"


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: Literal["active", "watch", "dormant", "retired"]
    note: NonEmptyText
