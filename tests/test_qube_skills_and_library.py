"""QUBE 技能本地仓与因子入库回归测试

覆盖：
- docs/ref/skills 参考资料中的 QuantSkills 技能已全部进入内置 seed
- use_skill 本地优先链路（手册 + 本地原文快照，零网络等待；缺快照时安排后台补抓）
- 原文本地仓：抓取失败保留 last-known-good、sweeper 回填、全失败标记
- save_factor_to_library 工具 / save-to-library 路由（快照入库、同名版本累加）
- search_factor_library 检索、run_research_code 进程内实验通道

复用临时数据库，不发真实模型请求、不访问网络。
"""

import asyncio
import time
import uuid

import pandas as pd
import pytest

from backend import database
from backend.routes import qube as qube_routes
from backend.services import qube_agent, qube_skills
from backend.services.qube_skill_repo import (
    _fetch_repo_payload,
    get_skill_repo,
    read_skill_repo,
    refresh_stale_skill_repos,
)

# docs/ref/skills 收录、应已入库的参考技能（seed 名 → 仓库）
REF_SKILL_NAMES = {
    "qs-factor-evaluate": "https://github.com/quantskills/skill-factor-evaluate",
    "qs-factor-mine": "https://github.com/quantskills/skill-factor-mine",
    "qs-factor-blend": "https://github.com/quantskills/skill-factor-blend",
    "qs-factor-optimize": "https://github.com/quantskills/skill-factor-optimize",
    "qs-risk-pattern-alpha": (
        "https://github.com/quantskills/skill-quant-factor-risk-pattern-alpha"
    ),
    "qs-factor-factory": (
        "https://github.com/quantskills/skill-quant-factor-skill-factory"
    ),
    "qs-factor-orthogonalize": (
        "https://github.com/quantskills/skill-factor-orthogonalize"
    ),
    "qs-backtest-overfit": "https://github.com/quantskills/skill-backtest-overfit",
}


@pytest.fixture()
def qube_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())
    return tmp_path / "test.db"


@pytest.fixture()
def offline_repo(monkeypatch):
    """本地仓离线桩：无任何原文快照；后台补抓被记录但不真正联网"""
    calls: list[tuple[str, str]] = []

    async def _fake_read(skill_name):
        return None

    def _fake_schedule(skill_name, repo_url):
        calls.append((skill_name, repo_url))

    from backend.services import qube_skill_repo

    monkeypatch.setattr(qube_skill_repo, "read_skill_repo", _fake_read)
    monkeypatch.setattr(qube_skill_repo, "schedule_refresh", _fake_schedule)
    return calls


def _seed():
    asyncio.run(qube_skills.seed_builtin_skills())


def _mk_factor(session_id: str, name="测试因子", code="close/DELAY(close,20)-1") -> str:
    async def _insert():
        fid = str(uuid.uuid4())
        now = int(time.time())
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO qube_factors (id, session_id, name, description, "
                "code_type, code, created_at, updated_at) "
                "VALUES (?, ?, ?, '', 'formula', ?, ?, ?)",
                (fid, session_id, name, code, now, now),
            )
            await db.commit()
            return fid
        finally:
            await db.close()

    return asyncio.run(_insert())


def _mk_session() -> str:
    async def _create():
        sid = str(uuid.uuid4())
        now = int(time.time())
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO qube_sessions (id, title, created_at, updated_at, pinned) "
                "VALUES (?, ?, ?, ?, 0)",
                (sid, "测试会话", now, now),
            )
            await db.commit()
            return sid
        finally:
            await db.close()

    return asyncio.run(_create())


def _bind_session(session_id: str, factor_id: str):
    asyncio.run(qube_agent._bind_session(session_id, "factor", factor_id))


# ── seed 与技能发现 ───────────────────────────────────────


def test_seed_contains_all_ref_skills(qube_db):
    """docs/ref/skills 参考资料中的 8 个技能全部进入内置 seed，手册自包含"""
    _seed()
    _seed()  # 幂等：重复 seed 不报错、不重复

    async def _q():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT name, display_name, prompt, repo_url FROM qube_skills "
                "WHERE builtin = 1"
            )
            return {r["name"]: r for r in await cur.fetchall()}
        finally:
            await db.close()

    rows = asyncio.run(_q())
    for name, repo in REF_SKILL_NAMES.items():
        assert name in rows, f"缺少参考技能: {name}"
        assert rows[name]["repo_url"] == repo
        # 手册自包含：离线抓不到 GitHub 原文时 agent 仅凭手册也能执行
        assert len(rows[name]["prompt"]) >= 300


def test_tool_list_skills_returns_seeded(qube_db):
    _seed()
    result = asyncio.run(qube_agent._tool_list_skills({}))
    names = {s["name"] for s in result["skills"]}
    assert set(REF_SKILL_NAMES) <= names


# ── use_skill 本地优先 ────────────────────────────────────


def test_tool_use_skill_loads_manual_offline(qube_db, offline_repo):
    """无本地快照时：手册照常返回 + 安排后台补抓，不阻塞、不联网"""
    _seed()
    result = asyncio.run(qube_agent._tool_use_skill({"name": "qs-factor-evaluate"}))
    assert result["ok"] is True
    assert result["name"] == "qs-factor-evaluate"
    assert "六步体检流程" in result["manual"]
    assert result["origin"] == "missing"
    assert offline_repo == [
        ("qs-factor-evaluate", "https://github.com/quantskills/skill-factor-evaluate")
    ]


def test_tool_use_skill_serves_local_snapshot(qube_db, monkeypatch):
    """有本地快照时：readme/skill_md 来自本地仓（skill_md 注入上限 12000），零补抓"""
    _seed()
    snapshot = {
        "ok": True,
        "repo_url": "https://github.com/quantskills/skill-factor-evaluate",
        "readme": "R" * 100,
        "skill_md": "S" * 20000,
        "fetched_at": int(time.time()),
    }

    async def _fake_read(skill_name):
        return snapshot

    scheduled: list[tuple[str, str]] = []

    def _fake_schedule(name, url):
        scheduled.append((name, url))

    from backend.services import qube_skill_repo

    monkeypatch.setattr(qube_skill_repo, "read_skill_repo", _fake_read)
    monkeypatch.setattr(qube_skill_repo, "schedule_refresh", _fake_schedule)

    result = asyncio.run(qube_agent._tool_use_skill({"name": "qs-factor-evaluate"}))
    assert result["origin"] == "local-cache"
    assert result["readme"] == "R" * 100
    assert len(result["skill_md"]) == 12_000
    assert scheduled == []


def test_tool_use_skill_by_display_name(qube_db, offline_repo):
    _seed()
    result = asyncio.run(
        qube_agent._tool_use_skill({"name": "多因子合并（去冗余→加权→合成信号）"})
    )
    assert result["ok"] is True
    assert result["name"] == "qs-factor-blend"


def test_tool_use_skill_unknown_name(qube_db, offline_repo):
    _seed()
    result = asyncio.run(qube_agent._tool_use_skill({"name": "不存在的技能"}))
    assert "技能不存在" in result["error"]


# ── 原文本地仓行为 ────────────────────────────────────────


def test_failed_fetch_keeps_last_good_snapshot(qube_db, monkeypatch):
    """联网刷新失败时保留 last-known-good，并附 refresh_error"""
    good = {
        "ok": True,
        "repo_url": "https://github.com/quantskills/x",
        "readme": "好快照",
        "skill_md": "SKILL",
        "meta": {},
        "fetched_at": int(time.time()) - 7200,
    }

    async def _fake_fetch(repo_url):
        return {"ok": False, "error": "网络不可达", "repo_url": repo_url}

    from backend.services.qube_skill_repo import _persist_repo_payload

    asyncio.run(_persist_repo_payload("qs-x", good))
    monkeypatch.setattr(
        "backend.services.qube_skill_repo._fetch_repo_payload", _fake_fetch
    )

    result = asyncio.run(
        get_skill_repo("qs-x", "https://github.com/quantskills/x", force=True)
    )
    assert result["readme"] == "好快照"
    assert result["stale"] is True
    assert "网络不可达" in result["refresh_error"]
    # 本地快照未被失败结果覆盖
    assert asyncio.run(read_skill_repo("qs-x"))["readme"] == "好快照"


def test_refresh_stale_skill_repos_backfills(qube_db, monkeypatch):
    """sweeper 回填：为缺失快照的技能联网抓取并落库（此处为离线桩）"""
    _seed()

    async def _fake_fetch(repo_url):
        return {
            "ok": True,
            "repo_url": repo_url,
            "readme": "README",
            "skill_md": "SKILLMD",
            "meta": {"stars": 1},
            "fetched_at": int(time.time()),
        }

    monkeypatch.setattr(
        "backend.services.qube_skill_repo._fetch_repo_payload", _fake_fetch
    )
    results = asyncio.run(refresh_stale_skill_repos())
    assert len(results) >= 32  # 14 QuantSkills + 18 LLMQuant 均有仓库地址
    assert all(r["ok"] for r in results)
    snap = asyncio.run(read_skill_repo("qs-factor-evaluate"))
    assert snap["skill_md"] == "SKILLMD"


def test_fetch_payload_marks_total_failure(monkeypatch):
    """正文与元数据全空时视为失败，不再伪装 ok=True 缓存 6 小时"""

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            class _R:
                status_code = 404
                text = ""

            return _R()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    payload = asyncio.run(
        _fetch_repo_payload("https://github.com/quantskills/not-exist-xyz")
    )
    assert payload["ok"] is False
    assert payload["error"]


# ── save_factor_to_library ────────────────────────────────


def test_save_factor_tool_uses_bound_factor_and_bumps_version(qube_db):
    """工具入库：默认绑定因子；同名重复入库版本号累加"""
    sid = _mk_session()
    fid = _mk_factor(sid, name="动量20")
    _bind_session(sid, fid)

    r1 = asyncio.run(qube_agent._tool_save_factor_to_library({}, sid))
    assert r1["ok"] is True
    assert r1["version"] == 1

    r2 = asyncio.run(qube_agent._tool_save_factor_to_library({}, sid))
    assert r2["ok"] is True
    assert r2["version"] == 2

    async def _q():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT name, category, formula, version FROM factors "
                "WHERE name = '动量20' ORDER BY version"
            )
            return [
                (r["category"], r["formula"], r["version"])
                for r in await cur.fetchall()
            ]
        finally:
            await db.close()

    rows = asyncio.run(_q())
    assert rows == [
        ("QUBE", "close/DELAY(close,20)-1", 1),
        ("QUBE", "close/DELAY(close,20)-1", 2),
    ]


def test_save_factor_tool_without_factor(qube_db):
    """无绑定因子时报错引导，而不是静默失败"""
    sid = _mk_session()
    result = asyncio.run(qube_agent._tool_save_factor_to_library({}, sid))
    assert "未指定因子" in result["error"]


def test_save_to_library_route(qube_db):
    """路由与工具共用快照逻辑；不存在的因子返回 404"""
    sid = _mk_session()
    fid = _mk_factor(sid, name="反转5", code="RANK(-returns)")
    result = asyncio.run(qube_routes.save_factor_to_library(fid))
    assert result["ok"] is True
    assert result["version"] == 1

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(qube_routes.save_factor_to_library("missing-id"))
    assert exc.value.status_code == 404


# ── search_factor_library ─────────────────────────────────


def _mk_library_factor(name, formula, category="QUBE"):
    async def _insert():
        now = int(time.time())
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO factors (id, name, description, category, formula, "
                "code, version, created_at, updated_at) "
                "VALUES (?, ?, '', ?, ?, '', 1, ?, ?)",
                (str(uuid.uuid4()), name, category, formula, now, now),
            )
            await db.commit()
        finally:
            await db.close()

    asyncio.run(_insert())


def _mk_preset_factor(code, name, desc, cat="动量"):
    async def _insert():
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO preset_factors (factor_code, factor_name, description, "
                "category_name, formula_status) VALUES (?, ?, ?, ?, 'formula_ok')",
                (code, name, desc, cat),
            )
            await db.commit()
        finally:
            await db.close()

    asyncio.run(_insert())


def test_search_factor_library(qube_db):
    _mk_library_factor("动量20", "close/DELAY(close,20)-1")
    _mk_library_factor("波动率", "STD(returns, 20)", category="volatility")
    _mk_preset_factor("P001", "Alpha#1", "公式: close/DELAY(close,20)-1 的变体")

    # 关键词命中公式 → 用户库命中、预设库按描述命中
    r = asyncio.run(
        qube_agent._tool_search_factor_library({"keyword": "DELAY(close,20)"})
    )
    assert [f["name"] for f in r["user_factors"]] == ["动量20"]
    assert r["preset_factors"][0]["factor_code"] == "P001"

    # scope=preset 不含用户库
    r2 = asyncio.run(
        qube_agent._tool_search_factor_library({"keyword": "波动率", "scope": "preset"})
    )
    assert r2["user_factors"] == []

    # 无关键词返回最近条目
    r3 = asyncio.run(qube_agent._tool_search_factor_library({"scope": "user"}))
    assert len(r3["user_factors"]) == 2


# ── run_research_code（进程内降级路径）────────────────────


def _synth_panels() -> dict[str, pd.DataFrame]:
    idx = pd.bdate_range("2024-01-02", periods=30)
    cols = ["000001.SZ", "000002.SZ"]
    base = pd.DataFrame(
        [[10.0 + 0.1 * i + j for j in range(2)] for i in range(30)],
        index=idx,
        columns=cols,
    )
    return {"close": base, "volume": base * 100}


def test_run_research_code_in_process(qube_db, monkeypatch):
    """无沙箱时进程内执行 run_experiment；结果与数据范围回传"""
    from backend.services import market_data, sandbox

    monkeypatch.setattr(
        market_data, "load_price_panels", lambda codes, s, e: _synth_panels()
    )
    monkeypatch.setattr(sandbox, "sandbox_available", lambda: False)

    code = (
        "def run_experiment(data):\n"
        "    c = data['close']\n"
        "    momo = c / c.shift(5) - 1\n"
        "    return {'n_dates': int(len(c)), 'mean_momo': float(momo.mean().mean())}\n"
    )
    r = asyncio.run(qube_agent._tool_run_research_code({"code": code}, "s1"))
    assert r["ok"] is True
    assert r["sandboxed"] is False
    assert r["result"]["n_dates"] == 30
    assert abs(r["result"]["mean_momo"]) > 0
    assert r["data_scope"]["n_symbols"] == 2


def test_run_research_code_rejects_bad_code(qube_db, monkeypatch):
    """未定义 run_experiment/result → 明确报错；超大 result → 打回重写"""
    from backend.services import market_data, sandbox

    monkeypatch.setattr(
        market_data, "load_price_panels", lambda codes, s, e: _synth_panels()
    )
    monkeypatch.setattr(sandbox, "sandbox_available", lambda: False)

    r = asyncio.run(qube_agent._tool_run_research_code({"code": "x = 1"}, "s1"))
    assert "run_experiment" in r["error"]

    big = "def run_experiment(data):\n    return {'blob': 'x' * 40000}\n"
    r2 = asyncio.run(qube_agent._tool_run_research_code({"code": big}, "s1"))
    assert "result 过大" in r2["error"]


# ── 工具注册完整性 ────────────────────────────────────────


def test_build_qube_tools_registers_new_tools():
    names = {t.name for t in qube_agent.build_qube_tools("s1")}
    assert {
        "save_factor_to_library",
        "search_factor_library",
        "run_research_code",
        "read_attachment",
        "create_skill",
    } <= names
    assert len(names) == 23


def test_read_doc_whitelist_expanded(qube_db):
    r = asyncio.run(
        qube_agent._tool_read_doc({"name": "代码执行沙箱", "keyword": "降级"})
    )
    assert "error" not in r
    r2 = asyncio.run(qube_agent._tool_read_doc({"name": "不存在文档"}))
    assert "功能模块" in r2["error"]  # 报错信息列出全部可选文档
