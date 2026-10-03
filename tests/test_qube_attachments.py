"""QUBE 会话附件 回归测试

覆盖：
- 附件解析服务：csv/xlsx 表格（规范 CSV + shape/列名元数据）、txt 文本、超限报错
- 上传路由（UploadFile → 落库 + 落盘）、下载路由、删除路由
- 消息附件引用：_save_message 落 attachments_json、_load_history 带出全量行
- read_attachment 工具：offset 分页 / keyword 定位 / 越界
- run_research_code 附件注入（进程内降级路径，验证 attachments 命名空间变量）
- build_manifest 清单注入内容

复用临时数据库与临时数据目录，不发真实模型请求、不启动容器。
"""

import asyncio
import io
import json
import time
import uuid

import pandas as pd
import pytest
from fastapi import HTTPException

from backend import database
from backend.config import settings as app_settings
from backend.routes import qube as qube_routes
from backend.services import qube_attachments
from backend.services.qube_agent import _tool_read_attachment


@pytest.fixture()
def qube_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    asyncio.run(database.init_db())
    return tmp_path / "test.db"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "data_dir", tmp_path, raising=False)
    return tmp_path


def _mk_session() -> str:
    async def _create():
        sid = str(uuid.uuid4())
        now = int(time.time())
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO qube_sessions (id, title, created_at, updated_at, pinned) "
                "VALUES (?, '测试', ?, ?, 0)",
                (sid, now, now),
            )
            await db.commit()
        finally:
            await db.close()
        return sid

    return asyncio.run(_create())


def _upload(sid: str, filename: str, data: bytes) -> dict:
    from fastapi import UploadFile

    uf = UploadFile(file=io.BytesIO(data), filename=filename)
    res = asyncio.run(qube_routes.upload_attachment(sid, uf))
    return res["attachment"]


# ── 解析服务 ──────────────────────────────────────────────────


def test_parse_upload_csv_table(data_dir):
    row = qube_attachments.parse_upload(
        "s1", "signals.csv", b"code,v\n000001,1.0\n000002,2.0\n"
    )
    assert row["kind"] == "table"
    meta = json.loads(row["table_meta_json"])
    assert meta["rows"] == 2 and meta["cols"] == 2
    assert meta["columns"] == ["code", "v"]
    assert "signals" not in row["preview"] or "2 行" in row["preview"]
    # 规范 CSV 落盘，可被 load_table_frame 读回
    frame = qube_attachments.load_table_frame(row)
    assert frame is not None and len(frame) == 2


def test_parse_upload_xlsx_table(data_dir):
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_excel(buf, index=False)
    row = qube_attachments.parse_upload("s1", "报表.xlsx", buf.getvalue())
    assert row["kind"] == "table"
    meta = json.loads(row["table_meta_json"])
    assert meta["rows"] == 3 and meta["columns"] == ["a", "b"]


def test_parse_upload_text_document(data_dir):
    row = qube_attachments.parse_upload("s1", "笔记.md", "第一段内容\n第二段内容".encode())
    assert row["kind"] == "text"
    assert row["extracted_chars"] > 0
    assert "第一段内容" in row["preview"]
    # 提取全文落盘
    assert "第二段内容" in qube_attachments.load_extract_text(row)


def test_parse_upload_oversize_rejected(data_dir):
    with pytest.raises(ValueError, match="过大"):
        qube_attachments.parse_upload("s1", "big.csv", b"x" * (26 * 1024 * 1024))


def test_parse_upload_bad_table_rejected(data_dir):
    with pytest.raises(ValueError):
        qube_attachments.parse_upload("s1", "bad.xlsx", b"not-an-excel")


# ── 上传/下载/删除路由 ────────────────────────────────────────


def test_upload_and_download_route(qube_db, data_dir):
    sid = _mk_session()
    att = _upload(sid, "signals.csv", b"code,v\n000001,1.0\n")

    assert att["kind"] == "table" and att["filename"] == "signals.csv"

    resp = asyncio.run(qube_routes.download_attachment(att["id"]))
    with open(resp.path, "rb") as f:
        assert b"000001,1.0" in f.read()

    # 删除后 404
    asyncio.run(qube_routes.delete_attachment(att["id"]))
    with pytest.raises(HTTPException) as e:
        asyncio.run(qube_routes.download_attachment(att["id"]))
    assert e.value.status_code == 404


def test_upload_rejects_foreign_session(qube_db, data_dir):
    from fastapi import UploadFile

    uf = UploadFile(file=io.BytesIO(b"x"), filename="a.txt")
    with pytest.raises(HTTPException) as e:
        asyncio.run(qube_routes.upload_attachment("no-such-session", uf))
    assert e.value.status_code == 404


def test_resolve_attachments_rejects_cross_session(qube_db, data_dir):
    sid = _mk_session()
    att = _upload(sid, "a.csv", b"v\n1\n")
    with pytest.raises(HTTPException) as e:
        asyncio.run(qube_routes._resolve_attachments("other-session", [att["id"]]))
    assert e.value.status_code == 400


# ── 消息附件引用与历史重建 ────────────────────────────────────


def test_message_attachments_persist_and_reload(qube_db, data_dir):
    sid = _mk_session()
    att = _upload(sid, "数据.csv", b"v\n1\n2\n")
    rows = asyncio.run(qube_routes._resolve_attachments(sid, [att["id"]]))

    asyncio.run(
        qube_routes._save_message(sid, "user", "请分析", attachments=rows)
    )
    history = asyncio.run(qube_routes._load_history(sid))
    assert history[-1]["attachments"][0]["filename"] == "数据.csv"
    assert history[-1]["attachments"][0]["kind"] == "table"

    # 消息列表接口也返回轻量附件引用
    messages = asyncio.run(qube_routes.list_messages(sid))["messages"]
    assert messages[-1]["attachments"][0]["id"] == att["id"]


def test_delete_session_cleans_attachment_files(qube_db, data_dir):
    sid = _mk_session()
    _upload(sid, "a.csv", b"v\n1\n")
    att_dir = qube_attachments.attachment_dir(sid)
    assert att_dir.exists()

    asyncio.run(qube_routes.delete_session(sid))
    assert not att_dir.exists()


# ── read_attachment 工具 ─────────────────────────────────────


def _seed_text_attachment(sid: str, text: str) -> dict:
    row = qube_attachments.parse_upload(sid, "长文.txt", text.encode())
    async def _insert():
        db = await database.get_db()
        try:
            await db.execute(
                "INSERT INTO qube_attachments (id, session_id, filename, kind, mime, "
                "size, extracted_chars, preview, table_meta_json, created_at) "
                "VALUES (?, ?, ?, ?, '', ?, ?, ?, '{}', ?)",
                (row["id"], sid, row["filename"], row["kind"], row["size"],
                 row["extracted_chars"], row["preview"], int(time.time())),
            )
            await db.commit()
        finally:
            await db.close()
    asyncio.run(_insert())
    return row


def test_read_attachment_paging_and_keyword(qube_db, data_dir):
    sid = _mk_session()
    text = "前文" + "甲" * 4000 + "关键词在这里" + "乙" * 4000
    row = _seed_text_attachment(sid, text)

    page1 = asyncio.run(
        _tool_read_attachment({"attachment_id": row["id"]}, sid)
    )
    assert page1["total_chars"] == len(text)
    assert page1["has_more"] is True
    assert len(page1["text"]) == 3000

    page2 = asyncio.run(
        _tool_read_attachment(
            {"attachment_id": row["id"], "offset": page1["next_offset"]}, sid
        )
    )
    assert page2["text"].startswith("甲" * 1000)

    hit = asyncio.run(
        _tool_read_attachment({"attachment_id": row["id"], "keyword": "关键词"}, sid)
    )
    assert hit["match_offset"] == 4002
    assert "关键词在这里" in hit["text"]

    miss = asyncio.run(
        _tool_read_attachment({"name": "长文.txt", "keyword": "不存在词"}, sid)
    )
    assert "未命中" in miss["note"]


def test_read_attachment_rejects_foreign_session(qube_db, data_dir):
    sid = _mk_session()
    row = _seed_text_attachment(sid, "内容")
    with_no_access = "another-session"
    result = asyncio.run(
        _tool_read_attachment({"attachment_id": row["id"]}, with_no_access)
    )
    assert "error" in result


# ── run_research_code 附件注入（进程内路径） ──────────────────


def test_run_research_code_injects_attachments(monkeypatch):
    from backend.services import sandbox

    monkeypatch.setattr(sandbox, "sandbox_available", lambda: False)
    panels = {"close": pd.DataFrame({"000001": [10.0, 11.0]}, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))}
    att = pd.DataFrame({"signal": [0.5, -0.5]})
    code = """
def run_experiment(data):
    return {
        "n": int(len(attachments["mysig"])),
        "sum": float(attachments["mysig"]["signal"].sum()),
        "cols": sorted(data.keys()),
    }
"""
    result, _stdout, sandboxed = asyncio.run(
        sandbox.run_research_code(code, panels, {"mysig": att})
    )
    assert sandboxed is False
    assert result["n"] == 2
    assert result["sum"] == 0.0
    assert result["cols"] == ["close"]


def test_run_research_code_without_attachments_keeps_behavior(monkeypatch):
    from backend.services import sandbox

    monkeypatch.setattr(sandbox, "sandbox_available", lambda: False)
    panels = {"close": pd.DataFrame({"000001": [1.0]}, index=pd.to_datetime(["2024-01-01"]))}
    code = """
def run_experiment(data):
    return {"ok": True, "has_att": "attachments" in dir()}
"""
    result, _stdout, _sandboxed = asyncio.run(sandbox.run_research_code(code, panels))
    assert result["ok"] is True


# ── LLM 清单注入 ─────────────────────────────────────────────


def test_build_manifest_lists_files_and_ids(qube_db, data_dir):
    sid = _mk_session()
    att = _upload(sid, "笔记.md", "研报要点：低波动因子".encode())
    att2 = _upload(sid, "数据.csv", b"v\n1\n")
    rows = asyncio.run(qube_routes._resolve_attachments(sid, [att["id"], att2["id"]]))

    manifest = qube_attachments.build_manifest(rows)
    assert "笔记.md" in manifest and att["id"] in manifest
    assert "数据.csv" in manifest and att2["id"] in manifest
    assert "read_attachment" in manifest and "attachments" in manifest
    # 无附件返回空串（不注入任何清单）
    assert qube_attachments.build_manifest([]) == ""


def test_message_llm_content_appends_manifest(qube_db, data_dir):
    sid = _mk_session()
    att = _upload(sid, "a.csv", b"v\n1\n")
    rows = asyncio.run(qube_routes._resolve_attachments(sid, [att["id"]]))

    out = qube_routes._message_llm_content("帮我分析", rows)
    assert out.startswith("帮我分析")
    assert "a.csv" in out
    # 无附件时原样返回
    assert qube_routes._message_llm_content("原文", []) == "原文"
