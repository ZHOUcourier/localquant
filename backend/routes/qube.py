"""QUBE — 策略研究 AI Agent 路由（与设置页 AI 配置完全独立）

- 会话/消息持久化（qube_sessions / qube_messages，含结构化工具轨迹 tool_calls_json）
- POST /chat：SSE 流式对话；事件集对齐参考站协议：
    delta / thinking / tool_start / tool / done / error
- 技能库（qube_skills）、因子画板（qube_factors + factor_analyses）、
  系统提示词（data/qube_system_prompt.md 可编辑，空回退内置 QUBE_SYSTEM）
- 独立配置持久化到 .env 的 QUBE_* 键；模型从供应商 models 清单下拉选择
"""

import asyncio
import json
import pathlib
import time
import urllib.parse
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from loguru import logger
from pydantic import BaseModel

from backend.config import settings
from backend.database import get_db
from backend.routes.settings import _write_env
from backend.services.ai_providers import (
    PROVIDER_PRESETS,
    apply_effort,
    list_cli_tools,
    list_providers,
    resolve_provider,
    run_cli,
    stream_cli,
)
from backend.services.qube_agent import AgentConfig, build_qube_tools, run_agent_loop
from backend.services.tokenize import estimate_tokens, model_context_window

router = APIRouter()

QUBE_SYSTEM = """职责：通过多轮对话帮助用户设计、验证、迭代 A 股量化策略与因子。

你拥有平台工具（优先用工具拿真实结果，不要臆想数据）：
【查询】get_data_status 本地数据范围 / read_doc 因子编写指南 /
        query_market_data 行情表格 / list_strategies / list_factors
【策略】generate_stock_strategy_code 写策略代码进画板 /
        list_strategy_versions · get_strategy_version · revert_strategy_to_version 版本管理
【回测】set_backtest_params 推参数给画板 / run_backtest 真实回测 / get_backtest_result 诊断
【因子】generate_stock_factor_code 写因子进画板 / run_factor_analysis IC+分组分析
【其它】bind_chat_target 切换画板绑定 / remember 记录用户长期偏好 /
        list_skills 查看技能库 / use_skill 加载指定技能的操作手册

技能库：内置大量来自开源社区的量化技能（因子衰减分析、A股个股尽调、主力资金画像、
因子挖掘、LLMQuant 各类研究框架等）。当用户请求契合某个技能时，先 list_skills 确认技能名，
再 use_skill 加载其操作手册并严格按手册流程执行（手册会指引你调用上述平台工具取真实数据）。

推荐工作流：
- 策略：read_doc/get_data_status 对齐约定 → generate_stock_strategy_code 写入画板 →
  run_backtest 验证 → 根据指标/报错迭代（改代码时传 strategy_id）
- 因子：read_doc 查算子 → generate_stock_factor_code（优先用 formula 公式）→
  run_factor_analysis 拿 IC/分组结果 → 解读并给出改进建议

硬性约定：
1. 用中文回答，结论先行；缺失关键信息（股票池/区间/风险偏好）时先追问。
2. 平台数据全部来自本地 QMT 日线行情（open/high/low/close/volume/amount 面板），
   不要引用外部数据源；面板 index=交易日、columns=股票代码。
3. 策略代码必须定义 generate_signals(prices, **kwargs)，返回同形状持仓权重/信号 DataFrame；
   代码在沙箱隔离执行，已预装 pandas/numpy。
4. 代码一律通过 generate_stock_strategy_code / generate_stock_factor_code 写入画板，
   不要把大段代码直接贴在回复里（回复只写结论、指标解读与下一步建议）。
5. 回测/分析失败时根据错误信息修正代码重试，不要把错误直接丢给用户。"""

# 用户可编辑的系统提示词（侧栏「系统提示词」弹窗；remember 工具也追加到这里）
SYSTEM_PROMPT_PATH = pathlib.Path("data/qube_system_prompt.md")


def get_system_prompt() -> str:
    """生效的系统提示词：文件存在且非空用文件，否则用内置默认"""
    try:
        if SYSTEM_PROMPT_PATH.exists():
            text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
            if text:
                return text
    except Exception as e:
        logger.warning(f"读取自定义系统提示词失败，回退内置: {e}")
    return QUBE_SYSTEM


# 工具 → 对话卡片展示名（前端工具卡标题）
TOOL_DISPLAY_NAMES = {
    "get_data_status": "查询本地数据概况",
    "read_doc": "阅读平台文档",
    "query_market_data": "查询行情数据",
    "generate_stock_strategy_code": "已写入策略代码",
    "list_strategies": "查看策略列表",
    "list_strategy_versions": "查看策略版本列表",
    "get_strategy_version": "读取策略版本",
    "revert_strategy_to_version": "回滚策略版本",
    "set_backtest_params": "已更新回测参数",
    "run_backtest": "运行策略回测",
    "get_backtest_result": "读取回测结果",
    "generate_stock_factor_code": "已创建股票因子",
    "run_factor_analysis": "运行因子分析",
    "list_factors": "查看因子列表",
    "bind_chat_target": "绑定对话目标",
    "remember": "记录长期记忆",
    "list_skills": "查看技能库",
    "use_skill": "加载技能手册",
}


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

QUBE_ENV_KEYS = {
    "QUBE_PROVIDER": "qube_provider",
    "QUBE_MODEL": "qube_model",
    "QUBE_EFFORT": "qube_effort",
    "QUBE_API_KEY": "qube_api_key",
    "QUBE_BASE_URL": "qube_base_url",
    "QUBE_ENGINE": "qube_engine",
    "QUBE_CLI": "qube_cli",
    "QUBE_CLI_MODEL": "qube_cli_model",
    "QUBE_CLI_EFFORT": "qube_cli_effort",
}


class QubeConfigUpdate(BaseModel):
    qube_provider: Optional[str] = None
    qube_model: Optional[str] = None
    qube_effort: Optional[str] = None
    qube_api_key: Optional[str] = None
    qube_base_url: Optional[str] = None
    qube_engine: Optional[str] = None  # api / cli
    qube_cli: Optional[str] = None
    qube_cli_model: Optional[str] = None
    qube_cli_effort: Optional[str] = None


def _mask(key: str) -> str:
    if not key:
        return ""
    return "****" if len(key) <= 8 else f"{key[:4]}****{key[-4:]}"


@router.get("/config")
async def get_qube_config():
    provider = resolve_provider(settings.qube_provider)
    preset = PROVIDER_PRESETS[provider]
    return {
        "qube_provider": provider,
        "qube_model": settings.qube_model or preset["model"],
        "qube_effort": settings.qube_effort,
        "qube_api_key_masked": _mask(settings.qube_api_key),
        "qube_api_key_set": bool(settings.qube_api_key),
        "qube_base_url": settings.qube_base_url,
        "qube_engine": settings.qube_engine,
        "qube_cli": settings.qube_cli,
        "qube_cli_model": settings.qube_cli_model,
        "qube_cli_effort": settings.qube_cli_effort or "default",
        "effort_levels": ["minimal", "low", "medium", "high"],
        "cli_effort_levels": ["default", "minimal", "low", "medium", "high"],
        "providers": list_providers(),
        "cli_tools": list_cli_tools(),
    }


@router.put("/config")
async def update_qube_config(body: QubeConfigUpdate):
    """QUBE 独立配置：写入 .env（QUBE_* 键）并同步内存 settings"""
    updates: dict[str, str] = {}
    for env_key, attr in QUBE_ENV_KEYS.items():
        value = getattr(body, attr)
        if value is None:
            continue
        updates[env_key] = str(value)
        setattr(settings, attr, str(value))
    if updates:
        _write_env(updates)
        logger.info(f"QUBE 配置已更新: {', '.join(updates.keys())}")
    return {"ok": True, "updated": list(updates.keys())}


# ---------------------------------------------------------------------------
# 会话 / 消息
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM qube_messages m WHERE m.session_id = s.id) "
            "AS message_count FROM qube_sessions s "
            "ORDER BY s.pinned DESC, s.updated_at DESC LIMIT 300"
        )
        return {
            "sessions": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "bound_type": r["bound_type"],
                    "bound_id": r["bound_id"],
                    "pinned": bool(r["pinned"]),
                    "message_count": r["message_count"] or 0,
                }
                for r in await cursor.fetchall()
            ]
        }
    finally:
        await db.close()


@router.post("/sessions")
async def create_session():
    now = int(time.time())
    sid = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO qube_sessions (id, title, created_at, updated_at, pinned) "
            "VALUES (?, '新对话', ?, ?, 0)",
            (sid, now, now),
        )
        await db.commit()
    finally:
        await db.close()
    return {"id": sid, "title": "新对话", "created_at": now, "updated_at": now}


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, body: SessionUpdate):
    """重命名会话 / 切换置顶"""
    fields: dict[str, object] = {}
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空")
        fields["title"] = title[:120]
    if body.pinned is not None:
        fields["pinned"] = 1 if body.pinned else 0
    if not fields:
        return {"ok": True}
    # 仅修改标题时更新时间（置顶/取消置顶不改动会话时间，保证归回原位）
    if "title" in fields:
        fields["updated_at"] = int(time.time())
    db = await get_db()
    try:
        keys = ", ".join(f"{k} = ?" for k in fields)
        cursor = await db.execute(
            f"UPDATE qube_sessions SET {keys} WHERE id = ?",  # noqa: S608
            (*fields.values(), session_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
    finally:
        await db.close()
    if "title" in fields:
        return {"ok": True, "title": fields["title"]}
    return {"ok": True}


@router.delete("/sessions")
async def clear_sessions():
    """清空全部对话（侧栏「清空全部对话」，前端二次确认后调用）"""
    db = await get_db()
    try:
        await db.execute("DELETE FROM qube_messages")
        cursor = await db.execute("DELETE FROM qube_sessions")
        await db.commit()
        return {"ok": True, "deleted": cursor.rowcount}
    finally:
        await db.close()


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM qube_messages WHERE session_id = ?", (session_id,)
        )
        cursor = await db.execute(
            "DELETE FROM qube_sessions WHERE id = ?", (session_id,)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
    finally:
        await db.close()
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: str):
    """历史消息（含结构化工具轨迹）+ workspace_resume（画板焦点恢复）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, role, content, created_at, tool_calls_json, usage_json "
            "FROM qube_messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        messages = []
        for r in await cursor.fetchall():
            item = {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
                "tool_calls": None,
                "usage": None,
            }
            if r["tool_calls_json"]:
                try:
                    item["tool_calls"] = json.loads(r["tool_calls_json"])
                except Exception:
                    item["tool_calls"] = None
            if r["usage_json"]:
                try:
                    item["usage"] = json.loads(r["usage_json"])
                except Exception:
                    item["usage"] = None
            messages.append(item)

        cursor = await db.execute(
            "SELECT bound_type, bound_id, context_summary FROM qube_sessions WHERE id = ?",
            (session_id,),
        )
        sess = await cursor.fetchone()
        resume = None
        if sess and sess["bound_type"]:
            resume = {"kind": sess["bound_type"], "id": sess["bound_id"]}
        return {
            "messages": messages,
            "workspace_resume": resume,
            "context_summary": sess["context_summary"] if sess else "",
        }
    finally:
        await db.close()


async def _save_message(  # noqa: PLR0913
    session_id: str,
    role: str,
    content: str,
    tool_calls: Optional[dict] = None,
    is_first_user: bool = False,
    usage: Optional[dict] = None,
) -> None:
    now = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO qube_messages (session_id, role, content, created_at, "
            "tool_calls_json, usage_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                now,
                json.dumps(tool_calls, ensure_ascii=False) if tool_calls else "",
                json.dumps(usage, ensure_ascii=False) if usage else "",
            ),
        )
        # 首条用户消息作为会话标题（若 AI 自动标题可用会稍后覆盖）
        await db.execute(
            "UPDATE qube_sessions SET updated_at = ?, "
            "title = CASE WHEN title = '新对话' AND ? = 'user' THEN ? ELSE title END "
            "WHERE id = ?",
            (now, role, content[:40], session_id),
        )
        await db.commit()
    finally:
        await db.close()
    # 首次用户消息：后台尝试 AI 生成更贴切的短标题（best-effort，失败保留截断标题）
    if is_first_user and role == "user":
        t = asyncio.create_task(_auto_title(session_id, content))
        _TITLE_TASKS.add(t)
        t.add_done_callback(_TITLE_TASKS.discard)  # 完成后即释放引用，防内存累积


# 后台标题生成任务引用（避免 task 被 GC + FastAPI 关停时警告）
_TITLE_TASKS: set[asyncio.Task] = set()

# 因子分析等重后台任务的并发上限（懒创建，防 import 时绑定事件循环）
_research_sem_obj: asyncio.Semaphore | None = None


def _research_sem() -> asyncio.Semaphore:
    global _research_sem_obj
    if _research_sem_obj is None:
        _research_sem_obj = asyncio.Semaphore(2)
    return _research_sem_obj


async def _auto_title(session_id: str, content: str) -> None:
    """用 QUBE 引擎把首条用户消息压缩成一个 ≤12 字标题，若已手动改名则不覆盖"""
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT title FROM qube_sessions WHERE id = ?", (session_id,)
            )
            row = await cursor.fetchone()
            if not row or row["title"] != content[:40]:
                return  # 已被手动重命名/标题不是默认截断值，跳过
        finally:
            await db.close()
        title = await qube_complete(
            "你是对话标题生成器。请把下面这条量化投研对话的首条用户消息，"
            "压缩成不超过 12 个汉字的简洁标题。只输出标题本身，"
            "不要引号、冒号，不要任何解释。",
            content,
        )
        title = title.strip().strip('"“” ').splitlines()[0].strip()[:40]
        if not title or title.lower() in ("好的", "是", "标题"):
            return
        db = await get_db()
        try:
            await db.execute(
                "UPDATE qube_sessions SET title = ? WHERE id = ? AND title = ?",
                (title, session_id, content[:40]),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception as e:
        logger.debug(f"QUBE 自动标题失败（保留默认标题）: {e}")


# ---------------------------------------------------------------------------
# 对话（SSE 流式）
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    session_id: str
    message: str


def _resolve_qube_api() -> tuple[str, str, str]:
    """QUBE api 引擎配置：(base_url, api_key, model)；未配置抛 400"""
    if not settings.qube_api_key:
        raise HTTPException(
            status_code=400, detail="未配置 QUBE API Key，请点击右上角「配置」填写"
        )
    provider = resolve_provider(settings.qube_provider)
    preset = PROVIDER_PRESETS[provider]
    base_url = (
        (settings.qube_base_url or "") if provider == "custom" else preset["base_url"]
    ).rstrip("/")
    model = settings.qube_model or preset["model"]
    if not base_url:
        raise HTTPException(status_code=400, detail="自定义（BYOK）需要填写 Base URL")
    if not model:
        raise HTTPException(status_code=400, detail="未配置模型名称")
    scheme = urllib.parse.urlsplit(base_url).scheme.lower()
    if scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="QUBE Base URL 仅支持 http/https 协议")
    return base_url, settings.qube_api_key, model


async def _count_messages(session_id: str) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) AS n FROM qube_messages WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        return row["n"] if row else 0
    finally:
        await db.close()


async def _load_history(session_id: str, limit: int = 40) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, role, content FROM qube_messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = list(await cursor.fetchall())[::-1]
        return [
            {"id": r["id"], "role": r["role"], "content": r["content"]} for r in rows
        ]
    finally:
        await db.close()


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _get_compaction(session_id: str) -> dict:
    """读取会话的上下文压缩状态（摘要 + 压缩边界消息 id）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT context_summary, compact_upto, compact_at FROM qube_sessions "
            "WHERE id = ?",
            (session_id,),
        )
        r = await cursor.fetchone()
        if not r:
            return {"summary": "", "compact_upto": 0, "compact_at": 0}
        return {
            "summary": r["context_summary"] or "",
            "compact_upto": r["compact_upto"] or 0,
            "compact_at": r["compact_at"] or 0,
        }
    finally:
        await db.close()


def _system_with_summary(summary: str) -> str:
    """把压缩得到的早期会话摘要注入系统提示词（Claude Code 式 compaction）"""
    base = get_system_prompt()
    if not summary:
        return base
    return f"{base}\n\n[早期会话摘要（已压缩）— 仅作背景，勿重复追问]\n{summary}"


async def _load_compacted_history(session_id: str, limit: int = 40) -> list[dict]:
    """加载压缩边界之后的近期消息（压缩前的早前消息已并入 context_summary）"""
    compact = await _get_compaction(session_id)
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, role, content FROM qube_messages WHERE session_id = ? "
            "AND id > ? ORDER BY id DESC LIMIT ?",
            (session_id, compact["compact_upto"], limit),
        )
        rows = list(await cursor.fetchall())[::-1]
        return [
            {"id": r["id"], "role": r["role"], "content": r["content"]}
            for r in rows
        ]
    finally:
        await db.close()


async def _truncate_after(session_id: str, message_id: int) -> None:
    """删除某条消息之后的所有消息（编辑/删除/重新生成的共用以截断）"""
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM qube_messages WHERE session_id = ? AND id > ?",
            (session_id, message_id),
        )
        await db.commit()
    finally:
        await db.close()


@router.post("/messages/{message_id}/regenerate")
async def regenerate_chat(session_id: str, message_id: int):
    """重新生成：定位会话最后一条用户消息 → 截断其后 → 对其重新流式应答"""
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    history = await _load_compacted_history(session_id)  # (id, role, content) 升序
    # 只允许针对"倒二"的消息（紧邻最后一条 AI 回复的用户消息）重新生成
    user_idx = max(
        (i for i, m in enumerate(history) if m["role"] == "user"), default=-1
    )
    if user_idx < 0:
        raise HTTPException(status_code=400, detail="没有可重新生成的消息")
    last_user = history[user_idx]
    await _truncate_after(session_id, last_user["id"])
    prior = [{"role": m["role"], "content": m["content"]} for m in history[:user_idx]]
    engine = settings.qube_engine
    api_cfg = _resolve_qube_api() if engine != "cli" else None
    return StreamingResponse(
        _stream_reply(session_id, prior, last_user["content"], api_cfg),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


async def _load_history_before(session_id: str, before_id: int) -> list[dict]:
    """取 id < before_id 的消息（编辑场景：更新该条并截断后，作为重跑前史）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role, content FROM qube_messages WHERE session_id = ? AND id < ? "
            "ORDER BY id ASC",
            (session_id, before_id),
        )
        return [
            {"role": r["role"], "content": r["content"]} for r in await cursor.fetchall()
        ]
    finally:
        await db.close()


class MessageEdit(BaseModel):
    session_id: str
    message_id: int
    content: str


@router.post("/chat/edit")
async def edit_chat_message(body: MessageEdit):
    """编辑某条用户消息：更新内容 → 截断其后 → 对其重新流式应答"""
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息不能为空")
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role FROM qube_messages WHERE id = ? AND session_id = ?",
            (body.message_id, body.session_id),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="消息不存在")
        if row["role"] != "user":
            raise HTTPException(status_code=400, detail="只能编辑用户消息")
    finally:
        await db.close()
    await _truncate_after(body.session_id, body.message_id)
    db = await get_db()
    try:
        now = int(time.time())
        await db.execute(
            "UPDATE qube_messages SET content = ?, created_at = ? "
            "WHERE id = ? AND session_id = ?",
            (content, now, body.message_id, body.session_id),
        )
        await db.execute(
            "UPDATE qube_sessions SET updated_at = ? WHERE id = ?",
            (now, body.session_id),
        )
        await db.commit()
    finally:
        await db.close()
    history = await _load_history_before(body.session_id, body.message_id)
    engine = settings.qube_engine
    api_cfg = _resolve_qube_api() if engine != "cli" else None
    return StreamingResponse(
        _stream_reply(body.session_id, history, content, api_cfg),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.delete("/messages/{message_id}")
async def delete_message(session_id: str, message_id: int):
    """删除某条消息及其之后的所有消息（截断会话）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) AS n FROM qube_messages WHERE id = ? AND session_id = ?",
            (message_id, session_id),
        )
        row = await cursor.fetchone()
        if not row or row["n"] == 0:
            raise HTTPException(status_code=404, detail="消息不存在")
        before = await db.execute(
            "SELECT COUNT(*) AS n FROM qube_messages WHERE session_id = ? AND id < ?",
            (session_id, message_id),
        )
        cnt = await before.fetchone()
        await db.execute(
            "DELETE FROM qube_messages WHERE session_id = ? AND id >= ?",
            (session_id, message_id),
        )
        now = int(time.time())
        if cnt and cnt["n"] > 0:
            await db.execute(
                "UPDATE qube_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
        await db.commit()
    finally:
        await db.close()
    return {"ok": True}


@router.get("/sessions/{session_id}/export")
async def export_session(session_id: str):
    """导出会话为 Markdown（投研记录归档）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT title FROM qube_sessions WHERE id = ?", (session_id,)
        )
        sess = await cursor.fetchone()
        if not sess:
            raise HTTPException(status_code=404, detail="会话不存在")
        title = sess["title"]
        cursor = await db.execute(
            "SELECT id, role, content, created_at, tool_calls_json FROM qube_messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    lines = [
        f"# {title}",
        "",
        f"- 会话 ID：`{session_id}`",
        f"- 导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
    ]
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["created_at"]))
        if r["role"] == "user":
            lines.append(f"## 用户 · {ts}\n\n{r['content']}\n\n---\n")
        else:
            lines.append(f"## QUBE · {ts}\n\n{r['content'] or '*（无文本回复）*'}")
            if r["tool_calls_json"]:
                try:
                    tc = json.loads(r["tool_calls_json"])
                    names = [
                        c.get("display_name") or c.get("name")
                        for c in (tc.get("calls") or [])
                    ]
                    if names:
                        lines.append(f"\n> 工具调用：{' → '.join(names)}")
                except Exception:
                    pass
            lines.append("\n\n---\n")
    body = "\n".join(lines)
    filename = f"qube-{session_id[:8]}.md"
    return Response(
        content=body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def qube_complete(system: str, user: str) -> str:
    """用 QUBE 引擎做一次性文本补全（供策略 AI 优化等非对话场景复用）"""
    if settings.qube_engine == "cli":
        try:
            return await run_cli(
                settings.qube_cli,
                f"{system}\n\n{user}",
                model=settings.qube_cli_model,
                effort=settings.qube_cli_effort,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
    base_url, api_key, model = _resolve_qube_api()
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json=apply_effort(
                    {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0.3,
                    },
                    settings.qube_effort,
                ),
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"AI 服务请求失败: {e}")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"AI 服务返回错误 (HTTP {resp.status_code}): {resp.text[:300]}",
        )
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        raise HTTPException(
            status_code=502, detail=f"AI 响应格式异常: {resp.text[:300]}"
        )


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def _stream_reply(
    session_id: str,
    history: list[dict],
    user_content: str,
    api_cfg: Optional[tuple[str, str, str]],
):
    """共享流式应答生成器（chat / edit / regenerate 复用）。

    history 为不含本次 user 消息的前史（[{role, content}, ...]），
    user_content 为本次要应答的用户内容（已由调用方落库/截断）。
    api_cfg: (base_url, api_key, model)；cli 引擎传 None。
    """
    engine = settings.qube_engine
    compact = await _get_compaction(session_id)
    usage: dict[str, int] | None = None  # API usage；None 时在完成时本地估算

    def _finalize_usage(
        prompt: str, completion: str, reasoning: str = ""
    ) -> dict[str, int]:
        """拿到 usage 则原样补 estimated=False；缺失时用本地估算兜底"""
        if usage:
            return {**usage, "estimated": False}
        return {
            "prompt_tokens": estimate_tokens(prompt),
            "completion_tokens": estimate_tokens(completion),
            "reasoning_tokens": estimate_tokens(reasoning),
            "total_tokens": estimate_tokens(prompt + completion),
            "estimated": True,
        }

    if engine == "cli":
        # CLI 无会话记忆：把系统提示 + 压缩摘要 + 近几轮对话拼进一次性提示词
        parts = [_system_with_summary(compact["summary"]), ""]
        for m in history[-10:]:
            parts.append(f"{'用户' if m['role'] == 'user' else 'QUBE'}：{m['content']}")
        parts.append(f"用户：{user_content}")
        prompt = "\n".join(parts)
        full: list[str] = []
        try:
            async for chunk in stream_cli(
                settings.qube_cli,
                prompt,
                model=settings.qube_cli_model,
                effort=settings.qube_cli_effort,
            ):
                full.append(chunk)
                yield _sse({"type": "delta", "delta": chunk, "text": chunk})
        except RuntimeError as e:
            yield _sse({"type": "error", "error": str(e), "message": str(e)})
            return
        content = "".join(full).strip()
        if content:
            await _save_message(
                session_id,
                "assistant",
                content,
                usage={
                    "prompt_tokens": estimate_tokens(prompt),
                    "completion_tokens": estimate_tokens(content),
                    "reasoning_tokens": 0,
                    "total_tokens": estimate_tokens(prompt + content),
                    "estimated": True,  # CLI 无 usage 字段，本地估算
                },
            )
        yield _sse({"type": "done", "done": True, "content": content})
        return

    base_url, api_key, model = api_cfg
    cfg = AgentConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system=_system_with_summary(compact["summary"]),
        tools=build_qube_tools(session_id),
        effort=settings.qube_effort,
    )
    messages = [
        {"role": m["role"], "content": m["content"]} for m in history
    ] + [{"role": "user", "content": user_content}]
    # 结构化轨迹：text/tool 交替时间线 + 工具调用列表 + 思考文本
    calls: list[dict] = []
    timeline: list[dict] = []
    text_buf: list[str] = []
    thinking_buf: list[str] = []
    pending_args: dict[str, dict] = {}

    def flush_text():
        text = "".join(text_buf).strip()
        if text:
            timeline.append({"type": "text", "content": text})
        text_buf.clear()

    async for event in run_agent_loop(cfg, messages):
        kind = event["type"]
        if kind == "usage":
            usage = event.get("usage")
        elif kind == "delta":
            text_buf.append(event["text"])
            yield _sse(event)
        elif kind == "thinking":
            thinking_buf.append(event["text"])
            yield _sse(event)
        elif kind == "tool_call":
            flush_text()
            pending_args[event["name"]] = event.get("args") or {}
            yield _sse(
                {
                    "type": "tool_start",
                    "name": event["name"],
                    "display_name": TOOL_DISPLAY_NAMES.get(event["name"], event["name"]),
                    "args": event.get("args") or {},
                }
            )
        elif kind == "tool_result":
            try:
                result = json.loads(event.get("result") or "{}")
            except Exception:
                result = {"raw": event.get("result")}
            call = {
                "name": event["name"],
                "display_name": TOOL_DISPLAY_NAMES.get(event["name"], event["name"]),
                "args": pending_args.pop(event["name"], {}),
                "result": result,
            }
            # 结构化 id 提升到顶层，供前端工具卡直接取用
            for key in (
                "strategy_id",
                "factor_id",
                "backtest_run_id",
                "factor_analysis_id",
            ):
                if isinstance(result, dict) and result.get(key):
                    call[key] = result[key]
            calls.append(call)
            timeline.append({"type": "tool", "call_index": len(calls) - 1})
            yield _sse({"type": "tool", "call": call})
        elif kind == "done":
            flush_text()
            final = event.get("content", "")
            tool_calls = None
            if calls or thinking_buf:
                tool_calls = {
                    "calls": calls,
                    "display_timeline": timeline,
                    "thinking": "".join(thinking_buf),
                }
            if final.strip() or tool_calls:
                # 兜底估算：API 未返回 usage（如省略 include_usage 的代理）时本地估算
                prompt_text = "\n".join(
                    m["role"] + ":" + m["content"] for m in history
                ) + "\nuser:" + user_content
                used = _finalize_usage(prompt_text, final)
                await _save_message(
                    session_id, "assistant", final.strip(), tool_calls, usage=used
                )
            yield _sse(event)
        elif kind == "error":
            yield _sse(event)
            return
        else:
            yield _sse(event)


@router.get("/sessions/{session_id}/stats")
async def session_stats(session_id: str):
    """上下文/用量统计：已用上下文 vs 窗口、输入/输出/思考构成（供前端进度条）

    - context_used：最近一次 LLM 请求的 prompt（系统+摘要+会话），有真实 usage 用真实值
    - 构成近似拆分：系统/压缩摘要/最近对话（输入），输出、思考(tool 调用外显)
    """
    compact = await _get_compaction(session_id)
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role, content, usage_json FROM qube_messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    completion = 0
    reasoning = 0
    last_prompt: int | None = None
    history_tokens = 0
    assistant_text_est = 0
    for r in rows:
        history_tokens += estimate_tokens(r["content"])
        if r["role"] != "assistant":
            continue
        assistant_text_est += estimate_tokens(r["content"])
        u = None
        if r["usage_json"]:
            try:
                u = json.loads(r["usage_json"])
            except Exception:
                u = None
        if u:
            completion += int(u.get("completion_tokens") or 0)
            reasoning += int(u.get("reasoning_tokens") or 0)
            if u.get("prompt_tokens"):
                last_prompt = int(u["prompt_tokens"])

    sys_tokens = estimate_tokens(get_system_prompt())
    summary_tokens = estimate_tokens(compact["summary"])

    if last_prompt is not None:
        context_used = max(int(last_prompt), sys_tokens + summary_tokens)
    else:
        # 无真实 usage：用系统+摘要+近段估算（不加历史重复，避免虚高）
        context_used = sys_tokens + summary_tokens + min(history_tokens, 12_000)
    context_window = _qube_context_window()
    conv_prompt = max(0, context_used - sys_tokens - summary_tokens)
    completion = completion or assistant_text_est
    total = context_used + completion
    return {
        "context_window": context_window,
        "context_used": context_used,
        "context_pct": round(context_used / context_window, 4) if context_window else 0,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "total_tokens": total,
        "compacted": bool(compact["summary"]),
        "compacted_at": compact["compact_at"],
        "breakdown": {
            "system": sys_tokens,
            "summary": summary_tokens,
            "conversation": conv_prompt,
            "completion": completion,
            "reasoning": reasoning,
        },
    }


def _qube_context_window() -> int:
    """当前 QUBE 引擎所用模型的上下文窗口上限"""
    if settings.qube_engine == "cli":
        return model_context_window(settings.qube_cli_model or settings.qube_model)
    return model_context_window(
        settings.qube_model or resolve_provider(settings.qube_provider) and PROVIDER_PRESETS[
            resolve_provider(settings.qube_provider)
        ]["model"]
    )


_COMPACT_TRANSCRIPT_MAX = 1000
_COMPACT_SYSTEM = (
    "你是对话压缩器。把下面这段 QUBE 量化投研对话压缩成尽量简短的中文要点摘要。"
    "仅保留：当前讨论的策略/因子、关键参数、回测与分析指标、重要结论、未完成事项、"
    "以及用户明确说过的偏好约束。直接输出摘要本体，不要任何开场白或结尾语。"
)


@router.post("/sessions/{session_id}/compress")
async def compress_session(session_id: str):
    """Claude Code 式上下文压缩：把较早期对话压缩成摘要并入 context_summary，
    释放上下文（仅压缩 boundary 之前的消息，之后的仍按原文发送，不丢历史）。"""
    KEEP = 16
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, role, content FROM qube_messages WHERE session_id = ? "
            "ORDER BY id ASC",
            (session_id,),
        )
        msgs = await cursor.fetchall()
    finally:
        await db.close()

    if len(msgs) <= KEEP:
        compact = await _get_compaction(session_id)
        return {
            "ok": True,
            "noop": True,
            "summary": compact["summary"],
            "kept": len(msgs),
            "context_window": _qube_context_window(),
        }

    slice_msgs = msgs[: len(msgs) - KEEP]
    boundary = slice_msgs[-1]["id"] if slice_msgs else 0
    existing = await _get_compaction(session_id)

    lines = []
    if existing["summary"]:
        lines.append(f"已有摘要：\n{existing['summary']}\n")
    lines.append("下面为本次要压缩进摘要的早前对话：\n")
    for m in slice_msgs:
        text = (m["content"] or "").strip()
        if not text:
            continue
        who = "用户" if m["role"] == "user" else "QUBE 助手"
        lines.append(f"【{who}】{text[:_COMPACT_TRANSCRIPT_MAX]}")
    prompt = "\n".join(lines) or "（无实质内容）"

    try:
        summary = await qube_complete(_COMPACT_SYSTEM, prompt)
    except HTTPException as e:
        # 压缩失败（无 Key/服务异常）时保留现状，不破坏会话
        raise HTTPException(status_code=e.status_code, detail=f"压缩失败：{e.detail}")
    summary = (summary or "").strip()
    if not summary:
        summary = existing["summary"]

    db = await get_db()
    try:
        now = int(time.time())
        await db.execute(
            "UPDATE qube_sessions SET context_summary = ?, compact_upto = ?, "
            "compact_at = ? WHERE id = ?",
            (summary, boundary, now, session_id),
        )
        await db.commit()
    finally:
        await db.close()

    return {
        "ok": True,
        "summary": summary,
        "kept": len(msgs) - len(slice_msgs),
        "dropped": len(slice_msgs),
        "compact_upto": boundary,
        "context_window": _qube_context_window(),
    }


def _is_retry(message: str, history: list[dict]) -> bool:
    """断网重试幂等判断：最后一条正是本次用户文本且尚无回复 → 是真重试。

    此时前端断网后点「重试」重发同一条消息，后端不应重复落库这条用户消息
    （历史已存该条），直接基于它重新流式应答即可。
    """
    return bool(history) and history[-1]["role"] == "user" and history[-1]["content"] == message


@router.post("/chat")
async def qube_chat(body: ChatRequest):
    """QUBE 多轮对话（SSE），事件集对齐参考站协议：

    api 引擎：{type: delta|thinking|tool_start|tool|done|error}
      tool 事件携带结构化 call（name/args/result/display_name/各类 id）
    cli 引擎：{delta} 增量 + {done}（CLI 自身即 agent，无工具事件）
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    is_first = (await _count_messages(body.session_id)) == 0
    history = await _load_history(body.session_id)
    # 断网/后端未返回兜底：若最后一条正是本次文本且尚无回复，视为客户端
    # 重试，不再重复落库（避免重发后同一条用户消息出现在历史里两次）
    idempotent_retry = _is_retry(body.message, history)
    if not idempotent_retry:
        await _save_message(
            body.session_id, "user", body.message, is_first_user=is_first
        )

    engine = settings.qube_engine
    # api 引擎的配置错误要在响应开始前抛 400（SSE 开始后无法再改状态码）
    api_cfg = _resolve_qube_api() if engine != "cli" else None

    return StreamingResponse(
        _stream_reply(body.session_id, history, body.message, api_cfg),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# ---------------------------------------------------------------------------
# 系统提示词（侧栏展示/编辑，替代参考站的「长期记忆」）
# ---------------------------------------------------------------------------


@router.get("/system-prompt")
async def read_system_prompt():
    return {
        "prompt": get_system_prompt(),
        "default_prompt": QUBE_SYSTEM,
        "customized": SYSTEM_PROMPT_PATH.exists()
        and bool(SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()),
    }


class SystemPromptUpdate(BaseModel):
    prompt: str


@router.put("/system-prompt")
async def write_system_prompt(body: SystemPromptUpdate):
    """保存系统提示词；传空 = 恢复内置默认（删文件）"""
    text = body.prompt.strip()
    if not text or text == QUBE_SYSTEM.strip():
        SYSTEM_PROMPT_PATH.unlink(missing_ok=True)
        return {"ok": True, "customized": False}
    SYSTEM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYSTEM_PROMPT_PATH.write_text(text, encoding="utf-8")
    return {"ok": True, "customized": True}


# ---------------------------------------------------------------------------
# 技能库（内置 30 个与参考站一致；自定义技能 = prompt 模板插入输入框）
# ---------------------------------------------------------------------------


def _skill_row(r) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "display_name": r["display_name"],
        "description": r["description"],
        "category": r["category"],
        "category_id": r["category_id"],
        "params": json.loads(r["params_json"] or "[]"),
        "prompt": r["prompt"],
        "builtin": bool(r["builtin"]),
        "enabled": bool(r["enabled"]),
        "source": r["source"],
        "url": r["url"],
        "repo_url": r["repo_url"],
        "stars": r["stars"],
    }


@router.get("/skills/builtin")
async def list_builtin_skills():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM qube_skills WHERE builtin = 1 ORDER BY id ASC"
        )
        return {"skills": [_skill_row(r) for r in await cursor.fetchall()]}
    finally:
        await db.close()


@router.get("/skills/{skill_id}/detail")
async def get_skill_detail(skill_id: int, refresh: bool = False):
    """技能详情：基础信息 + 关联 GitHub 仓库的 README / SKILL.md / 元数据"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM qube_skills WHERE id = ?", (skill_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="技能不存在")
        skill = _skill_row(row)
    finally:
        await db.close()

    from backend.services.qube_skill_repo import get_skill_repo

    repo = await get_skill_repo(skill["name"], skill["repo_url"], force=refresh)
    return {"skill": skill, "repo": repo}


@router.get("/skills/user")
async def list_user_skills():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM qube_skills WHERE builtin = 0 ORDER BY id DESC"
        )
        return {"skills": [_skill_row(r) for r in await cursor.fetchall()]}
    finally:
        await db.close()


class SkillCreate(BaseModel):
    display_name: str
    description: str = ""
    category: str = "对话"
    prompt: str = ""


_SKILL_CATEGORY_IDS = {
    "记忆": "memory",
    "策略": "strategy",
    "回测": "backtest",
    "调优": "optimization",
    "仿真交易": "live",
    "对话": "chat",
    "因子": "factor",
}


@router.post("/skills")
async def create_skill(body: SkillCreate):
    """新建自定义技能（prompt 模板，点击插入输入框）"""
    if not body.display_name.strip():
        raise HTTPException(status_code=400, detail="技能名称不能为空")
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt 模板不能为空")
    name = f"user_{uuid.uuid4().hex[:8]}"
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO qube_skills (name, display_name, description, category, "
            "category_id, params_json, prompt, builtin, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, '[]', ?, 0, 1, ?)",
            (
                name,
                body.display_name.strip(),
                body.description,
                body.category,
                _SKILL_CATEGORY_IDS.get(body.category, "chat"),
                body.prompt,
                int(time.time()),
            ),
        )
        await db.commit()
        return {"ok": True, "id": cursor.lastrowid}
    finally:
        await db.close()


class SkillUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    prompt: Optional[str] = None


async def _require_user_skill(db, skill_id: int):
    cursor = await db.execute("SELECT * FROM qube_skills WHERE id = ?", (skill_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="技能不存在")
    if row["builtin"]:
        raise HTTPException(status_code=403, detail="系统内置技能不可修改")
    return row


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: int, body: SkillUpdate):
    db = await get_db()
    try:
        await _require_user_skill(db, skill_id)
        fields = {}
        if body.display_name is not None:
            fields["display_name"] = body.display_name.strip()
        if body.description is not None:
            fields["description"] = body.description
        if body.category is not None:
            fields["category"] = body.category
            fields["category_id"] = _SKILL_CATEGORY_IDS.get(body.category, "chat")
        if body.prompt is not None:
            fields["prompt"] = body.prompt
        if fields:
            keys = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(
                f"UPDATE qube_skills SET {keys} WHERE id = ?",  # noqa: S608
                (*fields.values(), skill_id),
            )
            await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: int):
    db = await get_db()
    try:
        await _require_user_skill(db, skill_id)
        await db.execute("DELETE FROM qube_skills WHERE id = ?", (skill_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# 因子画板（qube_factors）+ 因子分析编排（factor_analyses）
# ---------------------------------------------------------------------------


def _factor_row(r) -> dict:
    return {
        "id": r["id"],
        "session_id": r["session_id"],
        "name": r["name"],
        "description": r["description"],
        "code_type": r["code_type"],
        "code": r["code"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


@router.get("/factors/{factor_id}")
async def get_qube_factor(factor_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM qube_factors WHERE id = ?", (factor_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="因子不存在")
        return _factor_row(row)
    finally:
        await db.close()


class QubeFactorUpdate(BaseModel):
    name: Optional[str] = None
    code_type: Optional[str] = None
    code: Optional[str] = None


@router.put("/factors/{factor_id}")
async def update_qube_factor(factor_id: str, body: QubeFactorUpdate):
    """画板编辑因子（改名/改代码/切换编写方式）"""
    fields = {}
    if body.name is not None and body.name.strip():
        fields["name"] = body.name.strip()
    if body.code_type in ("formula", "python"):
        fields["code_type"] = body.code_type
    if body.code is not None:
        fields["code"] = body.code
    if not fields:
        return {"ok": True}
    fields["updated_at"] = int(time.time())
    db = await get_db()
    try:
        keys = ", ".join(f"{k} = ?" for k in fields)
        cursor = await db.execute(
            f"UPDATE qube_factors SET {keys} WHERE id = ?",  # noqa: S608
            (*fields.values(), factor_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="因子不存在")
        return {"ok": True}
    finally:
        await db.close()


@router.post("/factors/{factor_id}/save-to-library")
async def save_factor_to_library(factor_id: str):
    """把画板因子存入因子库（factors 表快照）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM qube_factors WHERE id = ?", (factor_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="因子不存在")
        now = int(time.time())
        fid = str(uuid.uuid4())
        is_formula = (row["code_type"] or "formula") == "formula"
        await db.execute(
            "INSERT INTO factors (id, name, description, category, formula, code, "
            "version, created_at, updated_at) VALUES (?, ?, ?, 'QUBE', ?, ?, 1, ?, ?)",
            (
                fid,
                row["name"],
                row["description"] or "QUBE 对话产出",
                row["code"] if is_formula else "",
                "" if is_formula else row["code"],
                now,
                now,
            ),
        )
        await db.commit()
        return {"ok": True, "library_id": fid}
    finally:
        await db.close()


class FactorAnalysisRequest(BaseModel):
    factor_id: str
    session_id: str = ""
    period_start: str = ""
    period_end: str = ""
    adjustment_cycle: int = 5
    group_number: int = 5
    factor_direction: int = 1
    stock_pool: list[str] = []


@router.post("/factor-analysis")
async def start_factor_analysis(body: FactorAnalysisRequest):
    """画板「跑分析」：后台执行，前端轮询详情直至 done/error"""
    from backend.services.qube_research import (
        create_factor_analysis,
        execute_factor_analysis,
    )

    aid = await create_factor_analysis(
        body.factor_id,
        body.session_id,
        body.model_dump(exclude={"factor_id", "session_id"}),
    )

    async def _run():
        async with _research_sem():
            try:
                await execute_factor_analysis(aid)
            except Exception:
                pass  # 错误已落库（status=error），轮询侧展示

    asyncio.create_task(_run())
    return {"id": aid, "status": "running"}


@router.get("/factor-analysis")
async def list_factor_analyses(
    factor_id: str = "", session_id: str = "", limit: int = 20
):
    from backend.services.qube_research import analysis_row_to_dict

    db = await get_db()
    try:
        where, args = [], []
        if factor_id:
            where.append("factor_id = ?")
            args.append(factor_id)
        if session_id:
            where.append("session_id = ?")
            args.append(session_id)
        sql = "SELECT * FROM factor_analyses"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        cursor = await db.execute(sql, (*args, limit))  # noqa: S608
        return {"analyses": [analysis_row_to_dict(r) for r in await cursor.fetchall()]}
    finally:
        await db.close()


@router.get("/factor-analysis/{analysis_id}")
async def get_factor_analysis(analysis_id: str):
    from backend.services.qube_research import analysis_row_to_dict

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM factor_analyses WHERE id = ?", (analysis_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="分析记录不存在")
        return analysis_row_to_dict(row, with_detail=True)
    finally:
        await db.close()
