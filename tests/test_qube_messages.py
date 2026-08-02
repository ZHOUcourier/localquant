"""QUBE 会话消息操作（编辑/重新生成/删除/导出/置顶）回归测试

覆盖路由层的新增逻辑：编辑截断、重新生成定位最后一条用户消息、
删除并截断、导出 Markdown、置顶、消息计数。复用临时数据库，不发真实模型请求。
"""

import asyncio
import json
import time
import uuid

import pytest

import backend.database as database
from backend.routes import qube as qube_routes


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


def _add_msg(sid: str, role: str, content: str, tool_calls=None) -> int:
    async def _insert():
        now = int(time.time())
        db = await database.get_db()
        try:
            cur = await db.execute(
                "INSERT INTO qube_messages (session_id, role, content, created_at, "
                "tool_calls_json) VALUES (?, ?, ?, ?, ?)",
                (sid, role, content, now, json.dumps(tool_calls) if tool_calls else ""),
            )
            await db.commit()
            return cur.lastrowid
        finally:
            await db.close()

    return asyncio.run(_insert())


def _list_ids(sid: str):
    async def _q():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT id FROM qube_messages WHERE session_id = ? ORDER BY id", (sid,)
            )
            return [r["id"] for r in await cur.fetchall()]
        finally:
            await db.close()

    return asyncio.run(_q())


def test_truncate_after_removes_followups(qube_db):
    sid = _mk_session()
    m1 = _add_msg(sid, "user", "一")
    m2 = _add_msg(sid, "assistant", "二")
    _add_msg(sid, "user", "三")
    _add_msg(sid, "assistant", "四")
    asyncio.run(qube_routes._truncate_after(sid, m2))
    assert _list_ids(sid) == [m1, m2]


def test_delete_message_truncates(qube_db):
    sid = _mk_session()
    m1 = _add_msg(sid, "user", "一")
    m2 = _add_msg(sid, "assistant", "二")
    result = asyncio.run(qube_routes.delete_message(session_id=sid, message_id=m2))
    assert result == {"ok": True}
    assert _list_ids(sid) == [m1]


def test_regenerate_locates_last_user_and_truncates(qube_db):
    sid = _mk_session()
    m1 = _add_msg(sid, "user", "一")
    m2 = _add_msg(sid, "assistant", "二")
    m3 = _add_msg(sid, "user", "三")
    m4 = _add_msg(sid, "assistant", "四")
    history = asyncio.run(qube_routes._load_history(sid))
    user_idx = max((i for i, m in enumerate(history) if m["role"] == "user"))
    assert history[user_idx]["id"] == m3
    asyncio.run(qube_routes._truncate_after(sid, m3))
    # 截断后：m1/m2/m3 保留，m4 被删
    assert _list_ids(sid) == [m1, m2, m3]


def test_edit_updates_content_and_truncates(qube_db):
    sid = _mk_session()
    m1 = _add_msg(sid, "user", "老问题")
    _add_msg(sid, "assistant", "答复")
    asyncio.run(qube_routes._truncate_after(sid, m1))

    async def _update():
        db = await database.get_db()
        try:
            await db.execute(
                "UPDATE qube_messages SET content = ? WHERE id = ?", ("新问题", m1)
            )
            await db.commit()
        finally:
            await db.close()

    asyncio.run(_update())
    assert _list_ids(sid) == [m1]

    async def _check_content():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT content FROM qube_messages WHERE id = ?", (m1,)
            )
            return (await cur.fetchone())["content"]
        finally:
            await db.close()

    assert asyncio.run(_check_content()) == "新问题"


def test_rename_session_does_not_bump_time_on_pin_only(qube_db):
    b = _mk_session("B")

    async def _updated_at(sid):
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT updated_at FROM qube_sessions WHERE id = ?", (sid,)
            )
            return (await cur.fetchone())["updated_at"]
        finally:
            await db.close()

    t0 = asyncio.run(_updated_at(b))
    asyncio.run(
        qube_routes.rename_session(
            session_id=b, body=qube_routes.SessionUpdate(pinned=True)
        )
    )
    asyncio.run(
        qube_routes.rename_session(
            session_id=b, body=qube_routes.SessionUpdate(pinned=False)
        )
    )

    async def _check():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT updated_at, pinned FROM qube_sessions WHERE id = ?", (b,)
            )
            r = await cur.fetchone()
            return r["pinned"], r["updated_at"]
        finally:
            await db.close()

    pinned, updated_at = asyncio.run(_check())
    assert pinned == 0
    # 纯置顶切换不改 updated_at，避免排序/时间被跳动
    assert updated_at == t0


def test_list_sessions_orders_pinned_first(qube_db):
    a = _mk_session("A")
    b = _mk_session("B")
    asyncio.run(
        qube_routes.rename_session(
            session_id=b, body=qube_routes.SessionUpdate(pinned=True)
        )
    )

    async def _list():
        db = await database.get_db()
        try:
            cur = await db.execute(
                "SELECT id, pinned FROM qube_sessions ORDER BY pinned DESC, updated_at DESC"
            )
            return [(r["id"], r["pinned"]) for r in await cur.fetchall()]
        finally:
            await db.close()

    rows = asyncio.run(_list())
    assert rows[0] == (b, 1)
    assert rows[1] == (a, 0)


def test_export_session_markdown(qube_db):
    sid = _mk_session("我的策略")
    _add_msg(sid, "user", "帮我写动量策略")
    _add_msg(
        sid,
        "assistant",
        "已完成，请查看画板。",
        {"calls": [{"name": "run_backtest", "display_name": "运行策略回测"}]},
    )
    resp = asyncio.run(qube_routes.export_session(sid))
    text = resp.body.decode()
    assert "# 我的策略" in text
    assert "帮我写动量策略" in text
    assert "已完成，请查看画板。" in text
    assert "运行策略回测" in text