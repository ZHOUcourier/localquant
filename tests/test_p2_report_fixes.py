"""P2 审查清单回归：IC 分析输入错误返回 400（原为 500）；
节点综合报告 404 区分「节点类型不产报告」与「无运行记录」。

直接调用路由/辅助函数（项目测试约定：不起 TestClient，服务/路由层直测），
全部使用临时目录，不污染生产快照。
"""

import asyncio
import pickle

import pytest
from fastapi import HTTPException

from backend.models.factor import ICAnalysisRequest
from backend.routes.factor import ic_analysis
from backend.routes.workflow import _load_node_report


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


@pytest.fixture()
def report_outdir(tmp_path, monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "output_dir", tmp_path)
    return tmp_path


def test_node_report_found(report_outdir):
    run_dir = report_outdir / "run-1"
    run_dir.mkdir()
    with open(run_dir / "n9.pkl", "wb") as f:
        pickle.dump({"report": {"ic_mean": 0.03}}, f)
    report, found = _load_node_report(["run-1"], "n9")
    assert found and report == {"ic_mean": 0.03}


def test_node_report_pkl_without_report_is_flagged(report_outdir):
    """pkl 存在但无 report 字段（如 ICNode/GroupReturnNode）→ pkl_found=True，
    路由据此给出「该节点类型不产出报告」而非误导性的「旧版本运行需重跑」"""
    run_dir = report_outdir / "run-1"
    run_dir.mkdir()
    with open(run_dir / "n2.pkl", "wb") as f:
        pickle.dump({"ic_result": {"ic": 1}}, f)  # 无 report 键
    report, found = _load_node_report(["run-1"], "n2")
    assert report is None and found is True


def test_node_report_no_runs(report_outdir):
    report, found = _load_node_report(["ghost-run"], "n1")
    assert report is None and found is False
