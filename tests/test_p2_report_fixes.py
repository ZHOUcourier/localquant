"""P2 审查清单回归：IC 分析输入错误返回 400（原为 500）

直接调用路由协程（项目测试约定：不起 TestClient，服务/路由层直测），
面板日期错开的无效输入应触发 ValueError → HTTPException(400)。
"""

import asyncio

import pytest
from fastapi import HTTPException

from backend.models.factor import ICAnalysisRequest
from backend.routes.factor import ic_analysis


def test_ic_analysis_input_error_returns_400():
    req = ICAnalysisRequest(
        factor_data={"2024-01-01": {"A": 1.0}, "2024-01-02": {"A": 1.1}},
        return_data={"2024-02-01": {"A": 0.01}, "2024-02-02": {"A": -0.02}},
        periods=[1],
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(ic_analysis(req))
    assert ei.value.status_code == 400
    assert "无共同日期" in str(ei.value.detail) or "无共同" in str(ei.value.detail)
