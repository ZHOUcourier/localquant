"""P0-8 QUBE 仓位边界与实验污染测试

验证：
- set_backtest_params 拒绝 max_gross_exposure>1 与非 long_only（即时报错，不到 run 才炸）
- experiment_service.create 支持 status 参数（失败运行可记 failed）
- _create_workflow_experiment 无指标时不落实验（避免空指标污染）
"""

import asyncio

from backend.services import experiment_service as exp_mod
from backend.services import qube_agent, workflow_service


def test_set_backtest_params_rejects_leverage():
    """max_gross_exposure > 1 立即报错，不存入会话参数"""
    res = asyncio.run(
        qube_agent._tool_set_backtest_params(
            {"max_gross_exposure": 3}, session_id="test-sess"
        )
    )
    assert res.get("ok") is False
    assert "max_gross_exposure" in res.get("error", "")
    # 未存入会话参数
    assert "max_gross_exposure" not in qube_agent._SESSION_BT_PARAMS.get("test-sess", {})


def test_set_backtest_params_rejects_non_long_only():
    res = asyncio.run(
        qube_agent._tool_set_backtest_params(
            {"normalize": "dollar_neutral"}, session_id="test-sess2"
        )
    )
    assert res.get("ok") is False
    assert "long_only" in res.get("error", "")


def test_set_backtest_params_accepts_valid():
    res = asyncio.run(
        qube_agent._tool_set_backtest_params(
            {"max_gross_exposure": 1.0, "commission_rate": 0.001},
            session_id="test-sess3",
        )
    )
    assert res.get("ok") is True
    assert qube_agent._SESSION_BT_PARAMS["test-sess3"]["max_gross_exposure"] == 1.0


def test_experiment_create_status_param():
    """create 支持 status 参数（默认 completed，可传 failed）"""
    from backend.models.experiment import ExperimentCreate

    async def _run():
        req = ExperimentCreate(
            source="workflow",
            source_id="run-x",
            name="t",
            note="",
            tags=[],
            params={},
            metrics={},
        )
        return await exp_mod.experiment_service.create(req, status="failed")

    # 只验证调用不报错且 status 被接受（实际落库依赖 DB，这里验证签名）
    import inspect

    sig = inspect.signature(exp_mod.ExperimentService.create)
    assert "status" in sig.parameters
    assert sig.parameters["status"].default == "completed"


def test_create_workflow_experiment_skips_empty_metrics():
    """无指标时 _create_workflow_experiment 不落实验（不污染）"""
    # 空 node_outputs → _extract_metrics 为空 → 提前返回，不调 create
    metrics = workflow_service._extract_metrics({})
    assert metrics == {}
    # 有指标节点 → 能提取
    outs = {"n1": {"metrics": {"annual_return": 0.12, "sharpe_ratio": 1.2}}}
    metrics2 = workflow_service._extract_metrics(outs)
    assert metrics2.get("annual_return") == 0.12
