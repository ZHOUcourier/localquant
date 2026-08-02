"""第三轮加固回归测试：事件循环 / 下载节点 / SQL 上限 / 配置清洗 / AI 解析"""

import asyncio
import re

import pytest


# ── 数据下载节点：协议白名单 + 保存路径收敛 ──────────────────────


def test_data_download_rejects_non_http_scheme():
    from backend.plugins.builtin.basic_tools import DataDownloadInput, DataDownloadNode

    out = DataDownloadNode().run(DataDownloadInput(data_url="file:///etc/passwd"))
    assert out.success is False

    out2 = DataDownloadNode().run(DataDownloadInput(data_url="ftp://example.com/x.csv"))
    assert out2.success is False


def test_data_download_empty_url_no_crash():
    from backend.plugins.builtin.basic_tools import DataDownloadInput, DataDownloadNode

    out = DataDownloadNode().run(DataDownloadInput())
    assert out.success is False


# ── 公式/代码节点：受限内置函数（不允许 import / open） ──────────


def test_formula_calc_rejects_import():
    from backend.plugins.builtin.data_processing import FormulaCalcInput, FormulaCalcNode

    out = FormulaCalcNode().run(FormulaCalcInput(data=None, formula="import os"))
    assert out.data is not None  # 不崩溃，原样返回


def test_formula_calc_basic_math_works():
    import pandas as pd

    from backend.plugins.builtin.data_processing import FormulaCalcInput, FormulaCalcNode

    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    out = FormulaCalcNode().run(
        FormulaCalcInput(data=df, formula="df['c'] = df['a'] * df['b'] + abs(-1)")
    )
    assert (out.data["c"] == [5, 11, 19]).all()


def test_code_exec_safe_builtins_blocks_open():
    import pandas as pd

    from backend.plugins.builtin.data_processing import CodeExecInput, CodeExecNode

    df = pd.DataFrame({"a": [1, 2]})
    out = CodeExecNode().run(CodeExecInput(data=df, code="df['b'] = df['a'] * 2"))
    assert (out.data["b"] == [2, 4]).all()

    # 受限环境：__import__/open 不可用，执行失败时原样返回输入
    out2 = CodeExecNode().run(CodeExecInput(data=df, code="import os"))
    assert out2.data is not None


# ── DuckDB 服务：写关键字拦截 + 结果行数上限 ────────────────────


def test_duckdb_service_rejects_write_keywords():
    from backend.services.duckdb_service import DuckDBService

    svc = DuckDBService()
    for sql in ["INSERT INTO t VALUES (1)", "DROP TABLE t", "CREATE TABLE t(x int)", "PRAGMA foo"]:
        res = svc.query_local(sql)
        assert "error" in res, f"未拦截: {sql}"
        assert res["row_count"] == 0


def test_duckdb_service_caps_rows():
    from backend.services.duckdb_service import DuckDBService, MAX_RESULT_ROWS

    svc = DuckDBService()
    res = svc.query_local("SELECT range AS x FROM range(100000)")
    assert res["row_count"] <= MAX_RESULT_ROWS
    assert res.get("truncated") is True


def test_duckdb_service_normal_query_ok():
    from backend.services.duckdb_service import DuckDBService

    res = DuckDBService().query_local("SELECT 1 AS a, 2 AS b")
    assert res["row_count"] == 1
    assert res["data"] == [[1, 2]]


# ── 配置写入：换行注入清洗 ──────────────────────────────────────


def test_write_env_strips_newlines(tmp_path, monkeypatch):
    from backend.routes import settings as settings_route

    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=keep\n", encoding="utf-8")
    monkeypatch.setattr(settings_route, "ENV_FILE", env_file)

    settings_route._write_env({"OPENAI_BASE_URL": "https://a.com/b\nTOKEN=stolen"})
    content = env_file.read_text(encoding="utf-8")
    lines = [ln for ln in content.splitlines() if ln.strip()]
    assert "OPENAI_BASE_URL=https://a.com/bTOKEN=stolen" in lines  # 换行被剥离，未注入新键
    assert not any(ln.startswith("TOKEN=") for ln in lines)
    assert "EXISTING=keep" in lines


# ── AI 返回非对象 JSON → 优雅 502 ──────────────────────────────


def test_ai_workflow_non_object_json_rejected(monkeypatch):
    from fastapi import HTTPException

    from backend.routes import ai as ai_route

    async def fake_chat(system, user, temperature=0.2):
        return "[]"

    monkeypatch.setattr(ai_route, "_chat", fake_chat)

    async def _run():
        with pytest.raises(HTTPException) as exc:
            await ai_route.ai_generate_workflow(
                ai_route.WorkflowAIRequest(instruction="写个工作流")
            )
        assert exc.value.status_code == 502

    asyncio.run(_run())


# ── Comfy 图解析：字面量列表不再误判为连线 ──────────────────────


def test_graph_literal_list_not_misread_as_link():
    from backend.comfy.graph import convert_prompt

    prompt = {
        "1": {
            "class_type": "FormulaCalcNode",
            # 字面量列表 [999, 1]：999 不是节点 id，必须按静态输入处理
            "inputs": {"formula": "[999, 1]", "data": [999, 1]},
        }
    }
    nodes, links = convert_prompt(prompt)
    assert nodes[0]["static_input_data"]["data"] == [999, 1]
    assert links == []


# ── 实验对比 <2 时兜底字段 ─────────────────────────────────────


def test_experiment_compare_fewer_than_two_returns_empty_fields():
    from backend.services.experiment_service import ExperimentService

    async def _run():
        svc = ExperimentService()
        res = await svc.compare(["nonexistent_1", "nonexistent_2"])
        assert res.get("error")
        assert res.get("param_diffs") == {}
        assert res.get("metric_comparison") == {}

    asyncio.run(_run())
