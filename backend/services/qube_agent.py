"""QUBE Agent 内核 — 移植 pi（earendil-works/pi）的 agent-core 架构

对标 @earendil-works/pi-agent-core 的设计（Python 版）：
- Tool：name + description + JSON Schema 参数 + async 执行器
- Agent loop：LLM(带 tools, 流式) → 有 tool_calls 则执行并把结果回填消息，
  继续下一轮；直到模型不再调工具或达到 max_turns
- 事件流（供 SSE 透传，语义对齐 pi 的 agent 事件）：
    {"type": "delta",       "text": ...}                 增量文本
    {"type": "tool_call",   "name": ..., "args": {...}}  工具开始执行
    {"type": "tool_result", "name": ..., "result": ...}  工具执行结果（摘要）
    {"type": "done",        "content": ...}              最终助手文本
    {"type": "error",       "message": ...}

QUBE 注册的平台原生工具：本地数据概况 / 运行回测 / 保存策略到策略库。
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

import httpx
from loguru import logger

MAX_TURNS = 8  # 单条用户消息允许的最大 LLM 轮数（防失控循环）


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable[[dict], Awaitable[Any]]

    def spec(self) -> dict:
        """OpenAI 兼容 tools 声明"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentConfig:
    base_url: str
    api_key: str
    model: str
    system: str
    tools: list[Tool] = field(default_factory=list)
    temperature: float = 0.4
    effort: str = "medium"  # 推理强度 minimal/low/medium/high


async def run_agent_loop(cfg: AgentConfig, messages: list[dict]) -> AsyncIterator[dict]:
    """pi 风格 agent loop：流式 LLM + 工具调用循环，产出事件流

    messages 为不含 system 的历史（[{role, content}, ...]），本函数会
    原地追加 assistant/tool 消息（调用方可用于持久化轨迹）。
    """
    tool_map = {t.name: t for t in cfg.tools}
    convo: list[dict] = [{"role": "system", "content": cfg.system}, *messages]
    final_parts: list[str] = []

    for _turn in range(MAX_TURNS):
        payload: dict[str, Any] = {
            "model": cfg.model,
            "messages": convo,
            "stream": True,
            "temperature": cfg.temperature,
        }
        if cfg.tools:
            payload["tools"] = [t.spec() for t in cfg.tools]
        if cfg.effort and cfg.effort != "medium":
            payload["reasoning_effort"] = cfg.effort

        content_parts: list[str] = []
        # 累积流式 tool_calls：index → {id, name, arguments}
        calls: dict[int, dict] = {}

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    f"{cfg.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {cfg.api_key}"},
                ) as resp:
                    if resp.status_code != 200:
                        text = (await resp.aread()).decode(errors="replace")[:300]
                        yield {
                            "type": "error",
                            "message": f"AI 服务返回错误 (HTTP {resp.status_code}): {text}",
                        }
                        return
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = line[5:].strip()
                        if not chunk or chunk == "[DONE]":
                            continue
                        try:
                            delta = json.loads(chunk)["choices"][0]["delta"]
                        except Exception:
                            continue
                        text = delta.get("content") or ""
                        if text:
                            content_parts.append(text)
                            yield {"type": "delta", "text": text}
                        for tc in delta.get("tool_calls") or []:
                            idx = tc.get("index", 0)
                            slot = calls.setdefault(
                                idx, {"id": "", "name": "", "arguments": ""}
                            )
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                slot["name"] += fn["name"]
                            if fn.get("arguments"):
                                slot["arguments"] += fn["arguments"]
        except httpx.HTTPError as e:
            yield {"type": "error", "message": f"AI 服务请求失败: {e}"}
            return

        content = "".join(content_parts)
        if content:
            final_parts.append(content)

        if not calls:
            # 无工具调用 → 本轮即最终回复
            convo.append({"role": "assistant", "content": content})
            yield {"type": "done", "content": "\n".join(p for p in final_parts if p)}
            return

        # 有工具调用：回填 assistant(tool_calls) 消息，逐个执行
        ordered = [calls[i] for i in sorted(calls)]
        for c in ordered:
            if not c["id"]:
                c["id"] = f"call_{uuid.uuid4().hex[:8]}"
        convo.append(
            {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": c["arguments"]},
                    }
                    for c in ordered
                ],
            }
        )
        for c in ordered:
            name = c["name"]
            try:
                args = json.loads(c["arguments"] or "{}")
            except Exception:
                args = {}
            yield {"type": "tool_call", "name": name, "args": args}
            tool = tool_map.get(name)
            if tool is None:
                result: Any = {"error": f"未知工具: {name}"}
            else:
                started = time.time()
                try:
                    result = await tool.handler(args)
                except Exception as e:  # 工具失败回传给模型自行修正
                    logger.warning(f"QUBE 工具 {name} 执行失败: {e}")
                    result = {"error": str(e)[:500]}
                logger.info(f"QUBE 工具 {name} 耗时 {time.time() - started:.1f}s")
            result_str = json.dumps(result, ensure_ascii=False, default=str)[:4000]
            yield {"type": "tool_result", "name": name, "result": result_str}
            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": c["id"],
                    "content": result_str,
                }
            )

    yield {
        "type": "done",
        "content": "\n".join(p for p in final_parts if p)
        or "（已达到最大工具调用轮数，请继续追问）",
    }


# ---------------------------------------------------------------------------
# QUBE 平台原生工具
# ---------------------------------------------------------------------------


async def _tool_get_data_status(_args: dict) -> dict:
    """本地行情数据概况（股票数/列/日期区间），供 agent 决定可行的回测区间"""
    from backend.routes.explorer import list_tables

    tables = (await list_tables()).get("tables", [])
    return (
        {"tables": tables} if tables else {"tables": [], "note": "本地暂无缓存行情数据"}
    )


# 可供 QUBE 阅读的平台文档（只读，白名单）
_DOC_FILES = {
    "因子编写指南": "docs/因子编写指南.md",
}


async def _tool_read_doc(args: dict) -> dict:
    """读取平台文档（因子编写指南：字段/算子/数据层完整参考），可按关键词检索段落"""
    import pathlib

    name = str(args.get("name") or "因子编写指南")
    rel = _DOC_FILES.get(name)
    if not rel:
        return {"error": f"未知文档: {name}（可选: {', '.join(_DOC_FILES)}）"}
    try:
        text = pathlib.Path(rel).read_text(encoding="utf-8")
    except Exception as e:
        return {"error": f"文档读取失败: {e}"}
    keyword = str(args.get("keyword") or "").strip()
    if keyword:
        # 按关键词定位，返回命中前后的段落窗口（控制上下文体量）
        lines = text.splitlines()
        hits = [i for i, ln in enumerate(lines) if keyword.lower() in ln.lower()]
        if not hits:
            return {
                "name": name,
                "keyword": keyword,
                "note": "未命中，返回文档开头",
                "excerpt": text[:2500],
            }
        blocks = ["\n".join(lines[max(0, i - 3) : i + 20]) for i in hits[:6]]
        return {
            "name": name,
            "keyword": keyword,
            "excerpt": "\n---\n".join(blocks)[:4000],
        }
    return {"name": name, "excerpt": text[:4000], "truncated": len(text) > 4000}


async def _tool_preview_data(args: dict) -> dict:
    """读取真实行情样本（收盘价面板尾部几行），供 agent 对齐字段名/量级后再写代码"""
    from backend.services import market_data

    codes = list(args.get("stock_pool") or [])
    try:
        panels = market_data.load_price_panels(
            codes=codes,
            start_date=str(args.get("start_date") or ""),
            end_date=str(args.get("end_date") or ""),
        )
    except ValueError as e:
        return {"error": str(e)}
    close = panels.get("close")
    if close is None or close.empty:
        return {"error": "行情为空"}
    tail = close.tail(3).iloc[:, :5]
    return {
        "fields": list(panels.keys()),
        "stock_count": int(close.shape[1]),
        "date_range": [str(close.index[0].date()), str(close.index[-1].date())],
        "close_sample": {
            str(d.date()): {c: round(float(v), 3) for c, v in row.items() if v == v}
            for d, row in tail.iterrows()
        },
    }


async def _tool_run_backtest(args: dict) -> dict:
    """执行信号代码回测（复用 /api/backtest/run-strategy 核心），返回绩效摘要"""
    from fastapi import HTTPException

    from backend.routes.backtest import RunStrategyRequest, run_strategy

    req = RunStrategyRequest(
        signal_code=str(args.get("signal_code") or ""),
        stock_pool=list(args.get("stock_pool") or []),
        start_date=str(args.get("start_date") or ""),
        end_date=str(args.get("end_date") or ""),
        initial_capital=float(args.get("initial_capital") or 1_000_000),
        commission_rate=float(args.get("commission_rate") or 0.001),
        slippage=float(args.get("slippage") or 0.001),
    )
    try:
        result = await run_strategy(req)
    except HTTPException as e:
        return {"error": e.detail}
    # 只回传指标摘要与首尾净值，避免大曲线撑爆上下文
    eq = result.get("equity_curve", {})
    keys = sorted(eq)
    return {
        "tear_sheet": result.get("tear_sheet", {}),
        "equity_start": {keys[0]: eq[keys[0]]} if keys else {},
        "equity_end": {keys[-1]: eq[keys[-1]]} if keys else {},
        "n_days": len(keys),
    }


async def _tool_save_strategy(args: dict) -> dict:
    """把策略存入策略库（status=working；只有用户能手动设为已保存）"""
    from backend.database import get_db

    name = str(args.get("name") or "").strip()
    if not name:
        return {"error": "策略名称不能为空"}
    now = int(time.time())
    sid = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO strategies (id, name, description, status, source, content, "
            "code, workflow_id, session_id, created_at, updated_at) "
            "VALUES (?, ?, ?, 'working', 'chat', ?, ?, '', ?, ?, ?)",
            (
                sid,
                name,
                str(args.get("description") or ""),
                str(args.get("content") or ""),
                str(args.get("code") or ""),
                str(args.get("session_id") or ""),
                now,
                now,
            ),
        )
        await db.execute(
            "INSERT INTO strategy_versions (strategy_id, code, content, note, created_at) "
            "VALUES (?, ?, ?, '初始版本（QUBE 生成）', ?)",
            (sid, str(args.get("code") or ""), str(args.get("content") or ""), now),
        )
        await db.commit()
    finally:
        await db.close()
    return {"ok": True, "strategy_id": sid, "status": "working"}


def build_qube_tools(session_id: str) -> list[Tool]:
    """QUBE 的平台工具集（save_strategy 自动带上会话归属）"""

    async def save_with_session(args: dict) -> Any:
        return await _tool_save_strategy({**args, "session_id": session_id})

    return [
        Tool(
            name="get_data_status",
            description="查询本地 QMT 缓存行情数据概况：股票数量、可用列、日期区间。设计策略或回测前先调用，确定可行的股票池与时间区间。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_tool_get_data_status,
        ),
        Tool(
            name="read_doc",
            description=(
                "阅读平台文档，写因子/信号代码前务必查阅以对齐平台约定。"
                "name 目前支持「因子编写指南」（数据层形态、可用字段、内置算子清单）；"
                "keyword 可选，按关键词返回相关段落，避免整篇过长。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "文档名，默认「因子编写指南」",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "检索关键词，如 RANK、close、中性化",
                    },
                },
                "required": [],
            },
            handler=_tool_read_doc,
        ),
        Tool(
            name="preview_data",
            description="读取真实行情样本（收盘价面板尾部几行 + 可用字段 + 日期区间），写代码前用它核对字段名与数值量级，避免臆测。",
            parameters={
                "type": "object",
                "properties": {
                    "stock_pool": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "股票代码列表，空=全部本地缓存",
                    },
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": [],
            },
            handler=_tool_preview_data,
        ),
        Tool(
            name="run_backtest",
            description=(
                "对信号代码执行真实回测并返回绩效指标（年化/夏普/最大回撤等）。"
                "signal_code 必须定义 generate_signals(prices, **kwargs) 函数，"
                "prices 为收盘价面板 DataFrame(index=交易日, columns=股票代码)，"
                "返回同形状的持仓权重/信号 DataFrame。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "signal_code": {"type": "string", "description": "python 信号代码"},
                    "stock_pool": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "股票代码列表，空=全部本地缓存",
                    },
                    "start_date": {"type": "string", "description": "YYYY-MM-DD，可空"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD，可空"},
                    "initial_capital": {"type": "number"},
                    "commission_rate": {"type": "number"},
                    "slippage": {"type": "number"},
                },
                "required": ["signal_code"],
            },
            handler=_tool_run_backtest,
        ),
        Tool(
            name="save_strategy",
            description=(
                "把设计好的策略保存到平台策略库（状态=工作中）。"
                "content 为策略完整说明（名称/思路/因子/规则/风控/参数），"
                "code 为可回测的 generate_signals python 代码。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string", "description": "一句话概述"},
                    "content": {"type": "string"},
                    "code": {"type": "string"},
                },
                "required": ["name", "content", "code"],
            },
            handler=save_with_session,
        ),
    ]
