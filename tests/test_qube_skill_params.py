"""QUBE 技能参数表单 回归测试

覆盖：
- validate_skill_params 校验（空/正常/超量/非法名/重名/select 缺 options）
- 技能 CRUD 携带 params（创建落 params_json、更新改写、_skill_row 解析返回）
- create_skill agent 工具（新建 + 同名覆盖更新）
- renderSkillPrompt 对应的后端模板占位符约定（{{name}}）

复用临时数据库，不发真实模型请求、不访问网络。
"""

import asyncio
import json

import pytest
from fastapi import HTTPException

from backend import database
from backend.routes import qube as qube_routes
from backend.routes.qube import SkillCreate, SkillParam, validate_skill_params
from backend.services.qube_agent import _tool_create_skill


@pytest.fixture()
def qube_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())
    return tmp_path / "test.db"


GOOD_PARAMS = [
    {"name": "code", "label": "股票代码", "type": "text", "required": True, "default": "000001.SZ"},
    {"name": "level", "label": "置信水平", "type": "select", "options": ["0.9", "0.95"]},
]


# ── 校验 ─────────────────────────────────────────────────────


def test_validate_params_empty_ok():
    assert validate_skill_params([]) == ([], "")


def test_validate_params_roundtrip_and_defaults():
    out, err = validate_skill_params(GOOD_PARAMS)
    assert err == ""
    assert [p["name"] for p in out] == ["code", "level"]
    assert out[0]["required"] is True
    assert out[1]["options"] == ["0.9", "0.95"]
    assert out[1]["type"] == "select" and out[0]["type"] == "text"


def test_validate_params_rejects_bad_name():
    out, err = validate_skill_params([{"name": "1bad", "label": "x"}])
    assert out == [] and "非法" in err


def test_validate_params_rejects_duplicate():
    out, err = validate_skill_params(
        [{"name": "a", "label": "x"}, {"name": "a", "label": "y"}]
    )
    assert out == [] and "重复" in err


def test_validate_params_rejects_select_without_options():
    out, err = validate_skill_params([{"name": "a", "label": "x", "type": "select"}])
    assert out == [] and "options" in err


def test_validate_params_rejects_over_12():
    raw = [{"name": f"p{i}", "label": f"参数{i}"} for i in range(13)]
    out, err = validate_skill_params(raw)
    assert out == [] and "12" in err


def test_validate_params_accepts_skillparam_models():
    params = [SkillParam(name="code", label="代码"), SkillParam(name="n", label="数量")]
    out, err = validate_skill_params(params)
    assert err == "" and len(out) == 2


# ── CRUD 携带 params ─────────────────────────────────────────


def _skill_by_id(skill_id: int) -> dict:
    async def _get():
        db = await database.get_db()
        try:
            cur = await db.execute("SELECT * FROM qube_skills WHERE id = ?", (skill_id,))
            row = await cur.fetchone()
            return qube_routes._skill_row(row) if row else None
        finally:
            await db.close()

    return asyncio.run(_get())


def test_create_skill_with_params_roundtrip(qube_db):
    body = SkillCreate(
        display_name="压力测试",
        description="按参数做压力测试",
        category="回测",
        prompt="对 {{code}} 做压力测试，置信水平 {{level}}。",
        params=[SkillParam(**p) for p in GOOD_PARAMS],
    )
    res = asyncio.run(qube_routes.create_skill(body))
    skill = _skill_by_id(res["id"])

    assert skill["display_name"] == "压力测试"
    assert [p["name"] for p in skill["params"]] == ["code", "level"]
    assert skill["params"][1]["options"] == ["0.9", "0.95"]
    assert skill["builtin"] is False


def test_update_skill_params(qube_db):
    body = SkillCreate(display_name="t", prompt="p")
    res = asyncio.run(qube_routes.create_skill(body))

    upd = qube_routes.SkillUpdate(params=[SkillParam(name="w", label="窗口")])
    asyncio.run(qube_routes.update_skill(res["id"], upd))
    skill = _skill_by_id(res["id"])
    assert [p["name"] for p in skill["params"]] == ["w"]

    # 非法参数更新被拒
    bad = qube_routes.SkillUpdate(params=[SkillParam(name="Bad Name", label="x")])
    with pytest.raises(HTTPException):
        asyncio.run(qube_routes.update_skill(res["id"], bad))


# ── create_skill agent 工具 ──────────────────────────────────


def test_tool_create_skill_creates_and_updates(qube_db):
    res = asyncio.run(
        _tool_create_skill(
            {
                "display_name": "我的挖掘流程",
                "description": "五步挖掘",
                "category": "因子",
                "prompt": "对 {{pool}} 执行五步挖掘，窗口 {{window}}。",
                "params": [
                    {"name": "pool", "label": "股票池", "required": True},
                    {"name": "window", "label": "窗口", "type": "number", "default": "20"},
                ],
            }
        )
    )
    assert res["ok"] is True and res["updated"] is False and res["n_params"] == 2

    # 同名 → 覆盖更新
    res2 = asyncio.run(
        _tool_create_skill(
            {
                "display_name": "我的挖掘流程",
                "prompt": "对 {{pool}} 执行六步挖掘。",
                "params": [{"name": "pool", "label": "股票池"}],
            }
        )
    )
    assert res2["ok"] is True and res2["updated"] is True

    async def _count_and_check():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT COUNT(*) AS n, prompt FROM qube_skills WHERE builtin = 0 "
                "AND display_name = '我的挖掘流程'"
            )
            row = await cur.fetchone()
            cur2 = await db.execute(
                "SELECT params_json FROM qube_skills WHERE builtin = 0 "
                "AND display_name = '我的挖掘流程'"
            )
            params = json.loads((await cur2.fetchone())["params_json"])
            return row["n"], row["prompt"], params
        finally:
            await db.close()

    n, prompt, params = asyncio.run(_count_and_check())
    assert n == 1  # 不堆积
    assert "六步" in prompt
    assert [p["name"] for p in params] == ["pool"]


def test_tool_create_skill_rejects_bad_params(qube_db):
    res = asyncio.run(
        _tool_create_skill(
            {
                "display_name": "坏技能",
                "prompt": "x",
                "params": [{"name": "Bad-Name", "label": "x"}],
            }
        )
    )
    assert "error" in res

    res2 = asyncio.run(_tool_create_skill({"display_name": "坏技能2", "prompt": ""}))
    assert "error" in res2
