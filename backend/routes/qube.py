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
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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
            "SELECT * FROM qube_sessions ORDER BY updated_at DESC LIMIT 100"
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
            "INSERT INTO qube_sessions (id, title, created_at, updated_at) VALUES (?, '新对话', ?, ?)",
            (sid, now, now),
        )
        await db.commit()
    finally:
        await db.close()
    return {"id": sid, "title": "新对话", "created_at": now, "updated_at": now}


class SessionUpdate(BaseModel):
    title: str


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, body: SessionUpdate):
    """重命名会话"""
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE qube_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title[:60], int(time.time()), session_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="会话不存在")
    finally:
        await db.close()
    return {"ok": True, "title": title[:60]}


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
            "SELECT role, content, created_at, tool_calls_json FROM qube_messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        messages = []
        for r in await cursor.fetchall():
            item = {
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
                "tool_calls": None,
            }
            if r["tool_calls_json"]:
                try:
                    item["tool_calls"] = json.loads(r["tool_calls_json"])
                except Exception:
                    item["tool_calls"] = None
            messages.append(item)

        cursor = await db.execute(
            "SELECT bound_type, bound_id FROM qube_sessions WHERE id = ?",
            (session_id,),
        )
        sess = await cursor.fetchone()
        resume = None
        if sess and sess["bound_type"]:
            resume = {"kind": sess["bound_type"], "id": sess["bound_id"]}
        return {"messages": messages, "workspace_resume": resume}
    finally:
        await db.close()


async def _save_message(
    session_id: str, role: str, content: str, tool_calls: Optional[dict] = None
) -> None:
    now = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO qube_messages (session_id, role, content, created_at, tool_calls_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                session_id,
                role,
                content,
                now,
                json.dumps(tool_calls, ensure_ascii=False) if tool_calls else "",
            ),
        )
        # 首条用户消息作为会话标题
        await db.execute(
            "UPDATE qube_sessions SET updated_at = ?, "
            "title = CASE WHEN title = '新对话' AND ? = 'user' THEN ? ELSE title END "
            "WHERE id = ?",
            (now, role, content[:40], session_id),
        )
        await db.commit()
    finally:
        await db.close()


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
    return base_url, settings.qube_api_key, model


async def _load_history(session_id: str, limit: int = 30) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role, content FROM qube_messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = list(await cursor.fetchall())[::-1]
        return [{"role": r["role"], "content": r["content"]} for r in rows]
    finally:
        await db.close()


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


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


@router.post("/chat")
async def qube_chat(body: ChatRequest):
    """QUBE 多轮对话（SSE），事件集对齐参考站协议：

    api 引擎：{type: delta|thinking|tool_start|tool|done|error}
      tool 事件携带结构化 call（name/args/result/display_name/各类 id）
    cli 引擎：{delta} 增量 + {done}（CLI 自身即 agent，无工具事件）
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    history = await _load_history(body.session_id)
    await _save_message(body.session_id, "user", body.message)

    engine = settings.qube_engine
    # api 引擎的配置错误要在响应开始前抛 400（SSE 开始后无法再改状态码）
    api_cfg = _resolve_qube_api() if engine != "cli" else None

    async def api_stream():
        base_url, api_key, model = api_cfg
        cfg = AgentConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system=get_system_prompt(),
            tools=build_qube_tools(body.session_id),
            effort=settings.qube_effort,
        )
        messages = [*history, {"role": "user", "content": body.message}]
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
            if kind == "delta":
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
                        "display_name": TOOL_DISPLAY_NAMES.get(
                            event["name"], event["name"]
                        ),
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
                    "display_name": TOOL_DISPLAY_NAMES.get(
                        event["name"], event["name"]
                    ),
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
                    await _save_message(
                        body.session_id, "assistant", final.strip(), tool_calls
                    )
                yield _sse(event)
            elif kind == "error":
                yield _sse(event)
                return
            else:
                yield _sse(event)

    async def cli_stream():
        # CLI 无会话记忆：把系统提示 + 近几轮对话拼进一次性提示词
        parts = [get_system_prompt(), ""]
        for m in history[-10:]:
            parts.append(f"{'用户' if m['role'] == 'user' else 'QUBE'}：{m['content']}")
        parts.append(f"用户：{body.message}")
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
            await _save_message(body.session_id, "assistant", content)
        yield _sse({"type": "done", "done": True, "content": content})

    generator = cli_stream() if engine == "cli" else api_stream()
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
