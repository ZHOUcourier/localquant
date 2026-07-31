"""QUBE — 策略研究 AI Agent 路由（与设置页 AI 配置完全独立）

- 会话/消息持久化（qube_sessions / qube_messages）
- POST /chat：SSE 流式对话；引擎二选一
    api：pi 风格 agent loop（services/qube_agent，工具调用循环：
         查本地数据 / 跑回测 / 存策略），事件流 delta/tool_call/tool_result/done
    cli：本机 CLI 工具（Claude Code / Codex / OpenCode / Pi 等）流式转发 stdout
         （CLI 自身就是 agent，不叠加工具循环）
- 独立配置持久化到 .env 的 QUBE_* 键；模型从供应商 models 清单下拉选择
- Agent 产出的完整策略要求包裹在 ```strategy 代码块中，或直接调
  save_strategy 工具存入策略库（默认「工作中」，只有用户能设为「已保存」）
"""

import json
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

QUBE_SYSTEM = """你是 QUBE，LocalQuant 本地量化投研平台的策略研究 Agent。
你的职责：通过多轮对话帮助用户设计、验证、迭代 A 股量化策略（选股/因子/择时/风控）。

你拥有平台工具（优先用工具拿真实结果，不要臆想数据）：
- read_doc：阅读「因子编写指南」（数据层形态/可用字段/内置算子），写代码前必查
- preview_data：看真实行情样本（字段名/量级/日期区间），对齐后再写代码
- get_data_status：查本地数据范围（确定可用区间）
- run_backtest：对策略代码真实回测，拿到年化/夏普/回撤等指标
- save_strategy：把成型策略存入平台策略库（状态=工作中）

推荐工作流：read_doc/preview_data 对齐平台约定 → 写 generate_signals 代码 →
run_backtest 验证 → 根据指标/报错迭代 → save_strategy 存库。
注意：代码在 OpenSandbox 容器中隔离执行（Docker 不可用时降级为进程内），
已预装 pandas/numpy；信号函数入参 prices 为收盘价面板。

要求：
1. 用中文回答，结论先行，追问必要的缺失信息（股票池、频率、风险偏好等）。
2. 平台数据全部来自本地 QMT 日线行情（open/high/low/close/volume/amount 面板），
   不要引用外部数据源；因子/信号使用 pandas 面板（index=交易日, columns=股票代码）。
3. 策略代码必须定义 generate_signals(prices, **kwargs)，prices 为收盘价面板
   DataFrame，返回同形状的持仓权重/信号 DataFrame（可直接回测）。
4. 设计出完整策略后：先用 run_backtest 验证，再用 save_strategy 存库，
   并在回复中把策略正文包裹在 ```strategy 代码块中，格式：
```strategy
名称: <策略名>
思路: <一句话核心逻辑>
因子: <所用因子及公式>
买入规则: <...>
卖出规则: <...>
风控: <...>
参数: <...>
实现:
<generate_signals 完整 python 代码>
```
5. 回测失败时根据错误信息修正代码重试，不要把错误直接丢给用户。"""


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
}


class QubeConfigUpdate(BaseModel):
    qube_provider: Optional[str] = None
    qube_model: Optional[str] = None
    qube_effort: Optional[str] = None
    qube_api_key: Optional[str] = None
    qube_base_url: Optional[str] = None
    qube_engine: Optional[str] = None  # api / cli
    qube_cli: Optional[str] = None


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
        "effort_levels": ["minimal", "low", "medium", "high"],
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
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role, content, created_at FROM qube_messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        return {
            "messages": [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "created_at": r["created_at"],
                }
                for r in await cursor.fetchall()
            ]
        }
    finally:
        await db.close()


async def _save_message(session_id: str, role: str, content: str) -> None:
    now = int(time.time())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO qube_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
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
            return await run_cli(settings.qube_cli, f"{system}\n\n{user}")
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
    """QUBE 多轮对话（SSE）

    api 引擎：pi 风格 agent loop 事件流：
      {type: delta|tool_call|tool_result|done|error, ...}
    cli 引擎：{delta} 增量 + {done} 结束（兼容旧格式）
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
            system=QUBE_SYSTEM,
            tools=build_qube_tools(body.session_id),
            effort=settings.qube_effort,
        )
        messages = [*history, {"role": "user", "content": body.message}]
        trace: list[str] = []  # 工具轨迹（持久化进消息，刷新后可见）
        final = ""
        async for event in run_agent_loop(cfg, messages):
            if event["type"] == "tool_call":
                trace.append(f"🔧 调用工具 {event['name']}")
            elif event["type"] == "tool_result":
                trace.append(f"✓ {event['name']} 完成")
            elif event["type"] == "done":
                final = event.get("content", "")
            elif event["type"] == "error":
                yield _sse(event)
                return
            yield _sse(event)
        content = ("\n".join(trace) + "\n\n" if trace else "") + final
        if content.strip():
            await _save_message(body.session_id, "assistant", content.strip())

    async def cli_stream():
        # CLI 无会话记忆：把系统提示 + 近几轮对话拼进一次性提示词
        parts = [QUBE_SYSTEM, ""]
        for m in history[-10:]:
            parts.append(f"{'用户' if m['role'] == 'user' else 'QUBE'}：{m['content']}")
        parts.append(f"用户：{body.message}")
        prompt = "\n".join(parts)
        full: list[str] = []
        try:
            async for chunk in stream_cli(settings.qube_cli, prompt):
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
