"""QUBE 上下文/用量/压缩（tokenize / stats / compress）回归测试

覆盖：估算器、模型窗口映射、assistant 消息 usage 持久化、
上下文统计（已用 vs 窗口 + 构成）、上下文压缩（摘要+边界，不删历史）。
复用临时数据库，压缩时以 monkeypatch 的假 LLM 摘要代替真实模型请求。
"""

import asyncio
import json
import time
import uuid

import pytest

import backend.database as database
from backend.routes import qube as qube_routes
from backend.services import tokenize


@pytest.fixture()
def qube_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())
    return tmp_path / "test.db"


def _mk_session(title="测试会话") -> str:
    async def _create():
        sid = str(uuid.uuid4())
        now = int(time.time())
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO qube_sessions (id, title, created_at, updated_at, pinned) "
                "VALUES (?, ?, ?, ?, 0)",
                (sid, title, now, now),
            )
            await db.commit()
        finally:
            await db.close()
        return sid

    return asyncio.run(_create())


def _add_msg(sid, role, content, usage=None) -> int:
    async def _insert():
        now = int(time.time())
        db = await database.get_db()
        try:
            cur = await db.execute(
                "INSERT INTO qube_messages (session_id, role, content, created_at, "
                "usage_json) VALUES (?, ?, ?, ?, ?)",
                (sid, role, content, now, json.dumps(usage) if usage else ""),
            )
            await db.commit()
            return cur.lastrowid
        finally:
            await db.close()

    return asyncio.run(_insert())


def _count(sid):
    async def _q():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT COUNT(*) n FROM qube_messages WHERE session_id = ?", (sid,)
            )
            return (await cur.fetchone())["n"]
        finally:
            await db.close()

    return asyncio.run(_q())


# ---------------------------------------------------------------------------
# 估算器 / 窗口
# ---------------------------------------------------------------------------


def test_estimate_tokens_nonzero_and_cjk_heavy():
    ascii_t = tokenize.estimate_tokens("hello world this is a test")
    cjk_t = tokenize.estimate_tokens("你好世界这是一段中文投研对话内容")
    assert ascii_t > 0
    assert cjk_t > 0
    # 中文字符多 → 估算量不应小于纯短英文
    assert cjk_t > ascii_t


def test_model_context_window_mapping_and_default():
    assert tokenize.model_context_window("qwen3-max") == 131_072
    assert tokenize.model_context_window("gpt-4o") == 128_000
    assert tokenize.model_context_window("gpt-4.1-nano") == 1_000_000
    assert tokenize.model_context_window("claude-sonnet-4") == 200_000
    assert tokenize.model_context_window("totally-unknown-model") == tokenize.DEFAULT_CONTEXT_WINDOW


# ---------------------------------------------------------------------------
# usage 持久化
# ---------------------------------------------------------------------------


def test_save_message_persists_usage(qube_db):
    sid = _mk_session()
    asyncio.run(
        qube_routes._save_message(
            sid,
            "assistant",
            "已完成",
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "reasoning_tokens": 5,
                "total_tokens": 120,
                "estimated": True,
            },
        )
    )

    async def _usage():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT usage_json FROM qube_messages WHERE session_id = ?", (sid,)
            )
            return json.loads((await cur.fetchone())["usage_json"])
        finally:
            await db.close()

    u = asyncio.run(_usage())
    assert u["prompt_tokens"] == 100
    assert u["completion_tokens"] == 20
    assert u["estimated"] is True


# ---------------------------------------------------------------------------
# 上下文统计
# ---------------------------------------------------------------------------


def test_session_stats_composition(qube_db):
    sid = _mk_session()
    _add_msg(sid, "user", "写一个动量策略")
    _add_msg(
        sid,
        "assistant",
        "已完成，请查看",
        usage={
            "prompt_tokens": 300,
            "completion_tokens": 45,
            "reasoning_tokens": 12,
            "total_tokens": 345,
            "estimated": False,
        },
    )
    stats = asyncio.run(qube_routes.session_stats(sid))
    assert stats["context_used"] >= 300
    # 用真实 usage 的 prompt 作上下文
    assert stats["context_used"] == 300 or stats["context_used"] > 300
    assert stats["completion_tokens"] == 45
    assert stats["reasoning_tokens"] == 12
    assert stats["context_window"] > 0
    assert 0 < stats["context_pct"] <= 1.0
    bd = stats["breakdown"]
    assert bd["system"] > 0
    assert bd["completion"] == 45
    # 压缩前 compacted=False
    assert stats["compacted"] is False


# ---------------------------------------------------------------------------
# 上下文压缩
# ---------------------------------------------------------------------------


def test_compress_noop_when_short(qube_db):
    sid = _mk_session()
    _add_msg(sid, "user", "一")
    _add_msg(sid, "assistant", "二")
    result = asyncio.run(qube_routes.compress_session(sid))
    assert result["noop"] is True


def test_compress_builds_summary_and_keeps_history(qube_db, monkeypatch):
    sid = _mk_session()
    for i in range(24):  # > KEEP=16 → 应触发压缩
        _add_msg(sid, "user" if i % 2 == 0 else "assistant", f"消息 {i}")

    async def fake_complete(system, user):
        return "已压缩的策略要点摘要"

    monkeypatch.setattr(qube_routes, "qube_complete", fake_complete)

    result = asyncio.run(qube_routes.compress_session(sid))
    assert result["ok"] is True
    assert result.get("noop", False) is False
    assert result["summary"] == "已压缩的策略要点摘要"
    assert result["kept"] == 16
    assert result["dropped"] == 8
    # 不删历史行
    assert _count(sid) == 24

    compact = asyncio.run(qube_routes._get_compaction(sid))
    assert compact["summary"] == "已压缩的策略要点摘要"
    assert compact["compact_upto"] > 0

    stats = asyncio.run(qube_routes.session_stats(sid))
    assert stats["compacted"] is True


# ---------------------------------------------------------------------------
# 断网重试幂等去重
# ---------------------------------------------------------------------------


def test_is_retry_detects_idempotent_replay():
    assert qube_routes._is_retry("你好", [{"role": "user", "content": "你好"}]) is True
    # 最后一条是助手回复 → 同一文本再次输入是新消息，不算重试
    assert (
        qube_routes._is_retry(
            "你好", [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "在"}]
        )
        is False
    )
    # 文本不同 → 不算重试
    assert (
        qube_routes._is_retry("在吗", [{"role": "user", "content": "你好"}]) is False
    )
    # 空历史 → 不算重试
    assert qube_routes._is_retry("你好", []) is False


def test_retry_does_not_duplicate_saved_user_message(qube_db, monkeypatch):
    """断网重试场景：最后一条=该用户消息且无回复 → qu_chat 不重复落库用户消息"""

    # 拦截落库与模型解析，仅观察 qu_chat 的保存行为
    saved: list[str] = []

    async def fake_save(session_id, role, *_a, **_k):
        saved.append(role)

    async def fake_stream(*_a, **_k):
        yield {"type": "done", "content": "x"}

    monkeypatch.setattr(qube_routes, "_save_message", fake_save)
    monkeypatch.setattr(qube_routes, "_stream_reply", fake_stream)
    monkeypatch.setattr(
        qube_routes, "_resolve_qube_api", lambda: ("http://x", "k", "m")
    )

    sid = _mk_session()
    _add_msg(sid, "user", "写个动量策略")  # 后端历史里已存这条，且无回复

    # 断网重试：同一条文本再次 POST → 幂等，不再落库用户消息
    asyncio.run(
        qube_routes.qube_chat(
            qube_routes.ChatRequest(session_id=sid, message="写个动量策略")
        )
    )
    assert "user" not in saved  # 未重复插入用户消息

    # 正常情况下（最后一条是助手回复）同一文本是新消息 → 正常落库
    _add_msg(sid, "assistant", "回复")
    asyncio.run(
        qube_routes.qube_chat(
            qube_routes.ChatRequest(session_id=sid, message="写个动量策略")
        )
    )
    assert saved.count("user") == 1