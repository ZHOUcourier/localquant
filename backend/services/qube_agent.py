"""QUBE Agent 内核 — 移植 pi（earendil-works/pi）的 agent-core 架构

对标 @earendil-works/pi-agent-core 的设计（Python 版）：
- Tool：name + description + JSON Schema 参数 + async 执行器
- Agent loop：LLM(带 tools, 流式) → 有 tool_calls 则执行并把结果回填消息，
  继续下一轮；直到模型不再调工具或达到 max_turns
- 事件流（供 SSE 透传，语义对齐 pi 的 agent 事件）：
    {"type": "delta",       "text": ...}                 增量文本
    {"type": "thinking",    "text": ...}                 深度思考增量（reasoning_content）
    {"type": "tool_call",   "name": ..., "args": {...}}  工具开始执行
    {"type": "tool_result", "name": ..., "result": ...}  工具执行结果（摘要）
    {"type": "done",        "content": ...}              最终助手文本
    {"type": "error",       "message": ...}

QUBE 注册的平台原生工具与技能库（qube_skills 表 enabled=1 项）一一对应：
策略代码/版本/回测/因子/因子分析/行情查询/绑定目标/长期记忆。
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

    # 累计 usage（跨工具轮）：completion/reasoning 相加，prompt 取最后（最新）一次
    usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "estimated": False,
    }

    def _emit_done(content: str) -> AsyncIterator[dict]:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        yield {"type": "usage", "usage": {**usage}}
        yield {"type": "done", "content": content}

    for _turn in range(MAX_TURNS):
        payload: dict[str, Any] = {
            "model": cfg.model,
            "messages": convo,
            "stream": True,
            "temperature": cfg.temperature,
            "stream_options": {"include_usage": True},
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
                            parsed = json.loads(chunk)
                        except Exception:
                            continue
                        # include_usage 时末尾会带 usage（choices 可能为空）
                        u = parsed.get("usage")
                        if isinstance(u, dict):
                            pt = u.get("prompt_tokens") or 0
                            if pt:
                                usage["prompt_tokens"] = int(pt)
                                usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
                                details = u.get("completion_tokens_details") or {}
                                if isinstance(details, dict):
                                    usage["reasoning_tokens"] += int(
                                        details.get("reasoning_tokens") or 0
                                    )
                        choices = parsed.get("choices")
                        if not choices:
                            continue
                        try:
                            delta = choices[0]["delta"]
                        except Exception:
                            continue
                        text = delta.get("content") or ""
                        if text:
                            content_parts.append(text)
                            yield {"type": "delta", "text": text}
                        # 深度思考增量（DeepSeek/豆包等 reasoning 模型）
                        think = (
                            delta.get("reasoning_content")
                            or delta.get("reasoning")
                            or ""
                        )
                        if think:
                            yield {"type": "thinking", "text": think}
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
            async for ev in _emit_done("\n".join(p for p in final_parts if p)):
                yield ev
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

    async for ev in _emit_done(
        "\n".join(p for p in final_parts if p)
        or "（已达到最大工具调用轮数，请继续追问）"
    ):
        yield ev


# ---------------------------------------------------------------------------
# QUBE 平台原生工具（与技能库 enabled 项一一对应）
# ---------------------------------------------------------------------------

# 会话级回测参数（set_backtest_params 写入，run_backtest 合并使用；内存态）
_SESSION_BT_PARAMS: dict[str, dict] = {}


async def _bind_session(session_id: str, kind: str, target_id: str) -> None:
    """把会话绑定到画板工件（factor/strategy），切回会话时画板恢复"""
    from backend.database import get_db

    db = await get_db()
    try:
        await db.execute(
            "UPDATE qube_sessions SET bound_type = ?, bound_id = ? WHERE id = ?",
            (kind, target_id, session_id),
        )
        await db.commit()
    finally:
        await db.close()


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


async def _tool_query_market_data(args: dict) -> dict:
    """查询本地 A 股行情表格（只读）：指定标的/区间/字段，返回尾部样本"""
    from backend.services import market_data

    symbols = list(args.get("symbols") or [])
    fields = [f for f in (args.get("fields") or ["close"]) if isinstance(f, str)]
    try:
        panels = market_data.load_price_panels(
            codes=symbols,
            start_date=str(args.get("start_date") or ""),
            end_date=str(args.get("end_date") or ""),
        )
    except ValueError as e:
        return {"error": str(e)}
    close = panels.get("close")
    if close is None or close.empty:
        return {"error": "行情为空"}
    out: dict = {
        "fields": list(panels.keys()),
        "stock_count": int(close.shape[1]),
        "date_range": [str(close.index[0].date()), str(close.index[-1].date())],
        "tables": {},
    }
    for f in fields[:4]:
        panel = panels.get(f)
        if panel is None:
            continue
        tail = panel.tail(5).iloc[:, :8]
        out["tables"][f] = {
            str(d.date()): {c: round(float(v), 3) for c, v in row.items() if v == v}
            for d, row in tail.iterrows()
        }
    return out


async def _tool_generate_strategy_code(args: dict, session_id: str) -> dict:
    """生成/修改 A 股策略代码并写入画板：新建或更新会话绑定策略 + 记版本"""
    from backend.database import get_db

    name = str(args.get("name") or "").strip()
    code = str(args.get("code") or "")
    summary = str(args.get("summary") or "")
    if not name or not code.strip():
        return {"error": "name 与 code 不能为空"}
    now = int(time.time())
    strategy_id = str(args.get("strategy_id") or "").strip()
    db = await get_db()
    try:
        existing = None
        if strategy_id:
            cursor = await db.execute(
                "SELECT id FROM strategies WHERE id = ?", (strategy_id,)
            )
            existing = await cursor.fetchone()
        if existing:
            await db.execute(
                "UPDATE strategies SET name = ?, description = ?, code = ?, "
                "updated_at = ? WHERE id = ?",
                (name, summary, code, now, strategy_id),
            )
            note = f"AI 改：{summary[:60]}" if summary else "AI 改"
        else:
            strategy_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO strategies (id, name, description, status, source, "
                "content, code, workflow_id, session_id, created_at, updated_at) "
                "VALUES (?, ?, ?, 'working', 'chat', ?, ?, '', ?, ?, ?)",
                (strategy_id, name, summary, summary, code, session_id, now, now),
            )
            note = f"初始版本（QUBE 生成）：{summary[:60]}"
        await db.execute(
            "INSERT INTO strategy_versions (strategy_id, code, content, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (strategy_id, code, summary, note, now),
        )
        await db.commit()
    finally:
        await db.close()
    await _bind_session(session_id, "strategy", strategy_id)
    return {"ok": True, "strategy_id": strategy_id, "name": name, "status": "working"}


async def _tool_list_strategies(_args: dict) -> dict:
    """列出全部策略 + 最近一次成功回测的核心指标"""
    from backend.database import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, description, status, updated_at FROM strategies "
            "ORDER BY updated_at DESC LIMIT 50"
        )
        items = []
        for r in await cursor.fetchall():
            c2 = await db.execute(
                "SELECT metrics_json FROM backtest_runs WHERE strategy_id = ? "
                "AND status = 'done' ORDER BY created_at DESC LIMIT 1",
                (r["id"],),
            )
            bt = await c2.fetchone()
            metrics = json.loads(bt["metrics_json"]) if bt else {}
            items.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "description": r["description"],
                    "status": r["status"],
                    "last_backtest": {
                        "total_return": metrics.get("total_return"),
                        "sharpe_ratio": metrics.get("sharpe_ratio"),
                        "max_drawdown": metrics.get("max_drawdown"),
                    }
                    if metrics
                    else None,
                }
            )
        return {"strategies": items}
    finally:
        await db.close()


async def _tool_list_strategy_versions(args: dict) -> dict:
    from backend.database import get_db

    strategy_id = str(args.get("strategy_id") or "")
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, note, created_at FROM strategy_versions "
            "WHERE strategy_id = ? ORDER BY id DESC LIMIT 50",
            (strategy_id,),
        )
        return {
            "versions": [
                {"version": r["id"], "note": r["note"], "created_at": r["created_at"]}
                for r in await cursor.fetchall()
            ]
        }
    finally:
        await db.close()


async def _tool_get_strategy_version(args: dict) -> dict:
    from backend.database import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, code, content, note, created_at FROM strategy_versions "
            "WHERE strategy_id = ? AND id = ?",
            (str(args.get("strategy_id") or ""), int(args.get("version_number") or 0)),
        )
        r = await cursor.fetchone()
        if not r:
            return {"error": "版本不存在"}
        return {
            "version": r["id"],
            "note": r["note"],
            "code": r["code"],
            "created_at": r["created_at"],
        }
    finally:
        await db.close()


async def _tool_revert_strategy(args: dict) -> dict:
    """回滚到指定版本（复用策略库回滚逻辑，产生新版本记录）"""
    from fastapi import HTTPException

    from backend.routes.strategy import rollback_version

    try:
        result = await rollback_version(
            str(args.get("strategy_id") or ""), int(args.get("version_number") or 0)
        )
    except HTTPException as e:
        return {"error": e.detail}
    return {"ok": True, "code": result["code"][:1200]}


async def _tool_set_backtest_params(args: dict, session_id: str) -> dict:
    """把回测参数推给右侧画板（不立刻开跑）；同时存会话级参数供 run_backtest 合并"""
    keys = [
        "period_start",
        "period_end",
        "init_balance",
        "commission_rate",
        "slippage",
        "stamp_tax",
        "frequency",
        "stock_pool",
    ]
    params = {k: args[k] for k in keys if args.get(k) not in (None, "")}
    stored = _SESSION_BT_PARAMS.setdefault(session_id, {})
    stored.update(params)
    return {"ok": True, "params": stored}


async def _tool_run_backtest(args: dict, session_id: str) -> dict:
    """对策略提交真实回测（落库 backtest_runs，8 阶段进度），返回指标摘要"""
    from backend.database import get_db
    from backend.services.qube_research import (
        create_backtest_run,
        execute_backtest_run,
    )

    strategy_id = str(args.get("strategy_id") or "").strip()
    code = str(args.get("signal_code") or "")
    name = ""
    if strategy_id:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT name, code FROM strategies WHERE id = ?", (strategy_id,)
            )
            r = await cursor.fetchone()
        finally:
            await db.close()
        if not r:
            return {"error": f"策略不存在: {strategy_id}"}
        name = r["name"]
        code = code or r["code"]
    if not code.strip():
        return {"error": "策略代码为空：请先用 generate_stock_strategy_code 写入策略"}
    params = {**_SESSION_BT_PARAMS.get(session_id, {})}
    for k in (
        "period_start",
        "period_end",
        "init_balance",
        "commission_rate",
        "slippage",
        "stock_pool",
    ):
        if args.get(k) not in (None, ""):
            params[k] = args[k]
    run_id = await create_backtest_run(strategy_id, name, session_id, code, params)
    try:
        result = await execute_backtest_run(run_id)
    except Exception as e:
        return {"error": f"回测失败: {str(e)[:400]}", "backtest_run_id": run_id}
    m = result["metrics"]
    return {
        "ok": True,
        "backtest_run_id": run_id,
        "strategy_id": strategy_id,
        "metrics": {
            "total_return": m.get("total_return"),
            "annual_return": m.get("annual_return"),
            "sharpe_ratio": m.get("sharpe_ratio"),
            "max_drawdown": m.get("max_drawdown"),
            "trade_count": m.get("trade_count"),
        },
    }


async def _tool_get_backtest_result(args: dict) -> dict:
    """只读获取一次回测结果（诊断用：指标 + 尾部日志）"""
    from backend.database import get_db

    run_id = str(args.get("backtest_run_id") or "")
    db = await get_db()
    try:
        if run_id:
            cursor = await db.execute(
                "SELECT * FROM backtest_runs WHERE id = ?", (run_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM backtest_runs WHERE strategy_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (str(args.get("strategy_id") or ""),),
            )
        r = await cursor.fetchone()
    finally:
        await db.close()
    if not r:
        return {"error": "回测记录不存在"}
    return {
        "backtest_run_id": r["id"],
        "status": r["status"],
        "metrics": json.loads(r["metrics_json"] or "{}"),
        "error": r["error"],
        "log_tail": (r["log_text"] or "")[-1500:],
    }


async def _tool_generate_factor_code(args: dict, session_id: str) -> dict:
    """生成/修改 A 股因子并写入画板（qube_factors）"""
    from backend.database import get_db

    name = str(args.get("name") or "").strip()
    code = str(args.get("code") or "")
    if not name or not code.strip():
        return {"error": "name 与 code 不能为空"}
    code_type = str(args.get("code_type") or "formula")
    if code_type not in ("formula", "python"):
        code_type = "formula"
    now = int(time.time())
    factor_id = str(args.get("factor_id") or "").strip()
    db = await get_db()
    try:
        existing = None
        if factor_id:
            cursor = await db.execute(
                "SELECT id FROM qube_factors WHERE id = ?", (factor_id,)
            )
            existing = await cursor.fetchone()
        if existing:
            await db.execute(
                "UPDATE qube_factors SET name = ?, description = ?, code_type = ?, "
                "code = ?, updated_at = ? WHERE id = ?",
                (
                    name,
                    str(args.get("description") or ""),
                    code_type,
                    code,
                    now,
                    factor_id,
                ),
            )
        else:
            factor_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO qube_factors (id, session_id, name, description, "
                "code_type, code, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    factor_id,
                    session_id,
                    name,
                    str(args.get("description") or ""),
                    code_type,
                    code,
                    now,
                    now,
                ),
            )
        await db.commit()
    finally:
        await db.close()
    await _bind_session(session_id, "factor", factor_id)
    return {"ok": True, "factor_id": factor_id, "name": name, "code_type": code_type}


async def _tool_run_factor_analysis(args: dict, session_id: str) -> dict:
    """对因子做 IC 分析与分组回测（落库 factor_analyses，9 阶段进度），返回指标摘要"""
    from backend.database import get_db
    from backend.services.qube_research import (
        create_factor_analysis,
        execute_factor_analysis,
    )

    factor_id = str(args.get("factor_id") or "").strip()
    if not factor_id:
        # 默认用会话绑定的因子
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT bound_type, bound_id FROM qube_sessions WHERE id = ?",
                (session_id,),
            )
            r = await cursor.fetchone()
        finally:
            await db.close()
        if r and r["bound_type"] == "factor":
            factor_id = r["bound_id"]
    if not factor_id:
        return {"error": "未指定因子：请先用 generate_stock_factor_code 创建因子"}
    params = {
        k: args[k]
        for k in (
            "period_start",
            "period_end",
            "adjustment_cycle",
            "group_number",
            "factor_direction",
            "stock_pool",
        )
        if args.get(k) not in (None, "")
    }
    analysis_id = await create_factor_analysis(factor_id, session_id, params)
    try:
        result = await execute_factor_analysis(analysis_id)
    except Exception as e:
        return {
            "error": f"因子分析失败: {str(e)[:400]}",
            "factor_analysis_id": analysis_id,
        }
    s = result["summary"]
    return {
        "ok": True,
        "factor_id": factor_id,
        "factor_analysis_id": analysis_id,
        "summary": {
            "ic_mean": s.get("ic_mean"),
            "rank_ic": s.get("rank_ic"),
            "ic_ir": s.get("ic_ir"),
            "annual_return": s.get("annual_return"),
            "sharpe_ratio": s.get("sharpe_ratio"),
            "max_drawdown": s.get("max_drawdown"),
            "monotonicity": s.get("monotonicity"),
        },
    }


async def _tool_list_factors(_args: dict) -> dict:
    """列出对话产出的因子 + 最近一次分析的核心指标"""
    from backend.database import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name, code_type, code, updated_at FROM qube_factors "
            "ORDER BY updated_at DESC LIMIT 50"
        )
        items = []
        for r in await cursor.fetchall():
            c2 = await db.execute(
                "SELECT metrics_json FROM factor_analyses WHERE factor_id = ? "
                "AND status = 'done' ORDER BY created_at DESC LIMIT 1",
                (r["id"],),
            )
            a = await c2.fetchone()
            summary = (
                json.loads(a["metrics_json"] or "{}").get("summary", {}) if a else {}
            )
            items.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "code_type": r["code_type"],
                    "code": r["code"][:200],
                    "last_analysis": {
                        "ic_mean": summary.get("ic_mean"),
                        "ic_ir": summary.get("ic_ir"),
                        "monotonicity": summary.get("monotonicity"),
                    }
                    if summary
                    else None,
                }
            )
        return {"factors": items}
    finally:
        await db.close()


async def _tool_bind_chat_target(args: dict, session_id: str) -> dict:
    """切换当前对话绑定的画板工件（factor/strategy）"""
    kind = str(args.get("kind") or "")
    target = str(args.get("id") or "")
    if kind not in ("factor", "strategy") or not target:
        return {"error": "kind 需为 factor/strategy 且 id 不能为空"}
    await _bind_session(session_id, kind, target)
    return {"ok": True, "kind": kind, "id": target}


async def _tool_remember(args: dict) -> dict:
    """把长期偏好/事实追加到可编辑的系统提示词文件（侧栏可查看/编辑）"""
    import pathlib

    content = str(args.get("content") or "").strip()
    kind = str(args.get("kind") or "preference")
    if not content:
        return {"error": "content 不能为空"}
    path = pathlib.Path("data/qube_system_prompt.md")
    from backend.routes.qube import QUBE_SYSTEM  # 避免循环导入：延迟到调用时

    text = path.read_text(encoding="utf-8") if path.exists() else QUBE_SYSTEM
    if content in text:
        return {"ok": True, "note": "已存在相同记忆，未重复保存"}
    label = "偏好" if kind == "preference" else "事实"
    if "## 长期记忆" not in text:
        text += "\n\n## 长期记忆\n"
    text += f"- [{label}] {content}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"ok": True, "kind": kind}


async def _tool_list_skills(_args: dict) -> dict:
    """列出技能库中已启用的技能（名称、一句话说明、分类、来源）"""
    from backend.database import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT name, display_name, description, category, source, repo_url "
            "FROM qube_skills WHERE enabled = 1 ORDER BY category_id, id"
        )
        rows = await cursor.fetchall()
        return {
            "skills": [
                {
                    "name": r["name"],
                    "display_name": r["display_name"],
                    "description": r["description"],
                    "category": r["category"],
                    "source": r["source"],
                    "repo_url": r["repo_url"],
                }
                for r in rows
            ]
        }
    finally:
        await db.close()


async def _tool_use_skill(args: dict) -> dict:
    """加载技能库中某个技能，返回其完整操作手册 + GitHub README 供 agent 遵循执行"""
    name = str(args.get("name") or "").strip()
    if not name:
        return {"error": "name 不能为空（技能名，见 list_skills）"}
    from backend.database import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT name, display_name, description, prompt, url, repo_url "
            "FROM qube_skills WHERE enabled = 1 AND (name = ? OR display_name = ?)",
            (name, name),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    if not row:
        return {"error": f"技能不存在: {name}（可用 list_skills 查看全部技能）"}

    payload: dict = {
        "ok": True,
        "name": row["name"],
        "display_name": row["display_name"],
        "description": row["description"],
        "url": row["url"],
        "manual": row["prompt"],
    }
    # 附带 GitHub README（若可获取），让 agent 掌握技能原文细节
    if row["repo_url"]:
        try:
            from backend.services.qube_skill_repo import get_skill_repo

            repo = await get_skill_repo(row["name"], row["repo_url"])
            if repo.get("ok"):
                payload["repo_url"] = repo.get("repo_url")
                payload["readme"] = (repo.get("readme") or "")[:6000]
                payload["skill_md"] = (repo.get("skill_md") or "")[:4000]
        except Exception as e:  # 仓库抓取失败不阻断技能使用
            from loguru import logger

            logger.warning(f"技能 {row['name']} 仓库抓取失败: {e}")
    return payload


def build_qube_tools(session_id: str) -> list[Tool]:
    """QUBE 平台工具集（与技能库 enabled 项对应；会话相关工具自动带上归属）"""

    def with_session(fn):
        async def _wrapped(args: dict) -> Any:
            return await fn(args, session_id)

        return _wrapped

    _date = {"type": "string", "description": "YYYY-MM-DD，可空=自动"}
    _pool = {
        "type": "array",
        "items": {"type": "string"},
        "description": "股票代码列表，空=全部本地缓存",
    }
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
            name="query_market_data",
            description="查询本地 A 股行情表格（只读）：指定标的/区间/字段（open/high/low/close/volume/amount），返回尾部样本。写代码前用它核对字段名与数值量级，避免臆测。",
            parameters={
                "type": "object",
                "properties": {
                    "symbols": _pool,
                    "start_date": _date,
                    "end_date": _date,
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "字段列表，默认 [close]",
                    },
                },
                "required": [],
            },
            handler=_tool_query_market_data,
        ),
        Tool(
            name="generate_stock_strategy_code",
            description=(
                "生成或修改完整的 A 股策略代码并写入右侧画板（策略库状态=工作中，自动记版本）。"
                "code 必须定义 generate_signals(prices, **kwargs)，prices 为收盘价面板 "
                "DataFrame(index=交易日, columns=股票代码)，返回同形状持仓权重/信号 DataFrame。"
                "修改已有策略时传 strategy_id。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "generate_signals 完整 python 代码",
                    },
                    "name": {"type": "string", "description": "策略名"},
                    "summary": {
                        "type": "string",
                        "description": "一句话核心逻辑/本次改动说明",
                    },
                    "strategy_id": {
                        "type": "string",
                        "description": "修改已有策略时传",
                    },
                },
                "required": ["code", "name", "summary"],
            },
            handler=with_session(_tool_generate_strategy_code),
        ),
        Tool(
            name="list_strategies",
            description="列出当前用户所有策略，以及每条策略最近一次成功回测的总收益、夏普与回撤。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_tool_list_strategies,
        ),
        Tool(
            name="list_strategy_versions",
            description="列出策略的历史版本：版本号、改动说明、时间。",
            parameters={
                "type": "object",
                "properties": {"strategy_id": {"type": "string"}},
                "required": ["strategy_id"],
            },
            handler=_tool_list_strategy_versions,
        ),
        Tool(
            name="get_strategy_version",
            description="读取某个历史版本的源码与说明（只读，不改画板）。",
            parameters={
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "version_number": {
                        "type": "integer",
                        "description": "版本号（list_strategy_versions 返回的 version）",
                    },
                },
                "required": ["strategy_id", "version_number"],
            },
            handler=_tool_get_strategy_version,
        ),
        Tool(
            name="revert_strategy_to_version",
            description="把策略回滚到某个历史版本：将该版代码复制成新版本并写回画板，历史不会丢。",
            parameters={
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "version_number": {"type": "integer"},
                },
                "required": ["strategy_id", "version_number"],
            },
            handler=_tool_revert_strategy,
        ),
        Tool(
            name="set_backtest_params",
            description="调整右侧画板的回测参数（起止日期、初始资金、成本等），不立刻开跑。",
            parameters={
                "type": "object",
                "properties": {
                    "period_start": _date,
                    "period_end": _date,
                    "init_balance": {
                        "type": "number",
                        "description": "初始资金，默认 1000000",
                    },
                    "commission_rate": {
                        "type": "number",
                        "description": "手续费率，默认 0.001",
                    },
                    "slippage": {"type": "number", "description": "滑点，默认 0.001"},
                    "frequency": {
                        "type": "string",
                        "description": "频率，本地仅支持 1d",
                    },
                    "stock_pool": _pool,
                },
                "required": [],
            },
            handler=with_session(_tool_set_backtest_params),
        ),
        Tool(
            name="run_backtest",
            description=(
                "对策略提交真实回测（落库可在回测记录中查看），返回总收益/年化/夏普/最大回撤等指标。"
                "优先传 strategy_id（用已写入画板的策略）；也可直传 signal_code 即时验证。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "signal_code": {
                        "type": "string",
                        "description": "不传 strategy_id 时必填",
                    },
                    "period_start": _date,
                    "period_end": _date,
                    "init_balance": {"type": "number"},
                    "commission_rate": {"type": "number"},
                    "slippage": {"type": "number"},
                    "stock_pool": _pool,
                },
                "required": [],
            },
            handler=with_session(_tool_run_backtest),
        ),
        Tool(
            name="get_backtest_result",
            description="只读获取一次真实回测结果，用于诊断无成交、失败原因或异常指标。",
            parameters={
                "type": "object",
                "properties": {
                    "backtest_run_id": {"type": "string"},
                    "strategy_id": {
                        "type": "string",
                        "description": "不传 run_id 时取该策略最近一次",
                    },
                },
                "required": [],
            },
            handler=_tool_get_backtest_result,
        ),
        Tool(
            name="generate_stock_factor_code",
            description=(
                "生成或修改 A 股因子并写入右侧画板。code_type=formula 时 code 为公式表达式"
                "（如 close/DELAY(close,20)-1，可用 RANK/DELAY/STD 等算子，见因子编写指南）；"
                "code_type=python 时 code 需定义 compute_factor(close, volume) 或 factor_data 变量。"
                "修改已有因子时传 factor_id。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "code_type": {"type": "string", "enum": ["formula", "python"]},
                    "factor_id": {"type": "string", "description": "修改已有因子时传"},
                },
                "required": ["code", "name"],
            },
            handler=with_session(_tool_generate_factor_code),
        ),
        Tool(
            name="run_factor_analysis",
            description=(
                "对因子做 IC 分析与分组回测（落库，画板展示 9 阶段进度与完整图表），"
                "返回 IC_mean/Rank_IC/IC_IR/年化/夏普/回撤/单调性摘要。不传 factor_id 时用会话绑定因子。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "factor_id": {"type": "string"},
                    "period_start": _date,
                    "period_end": _date,
                    "adjustment_cycle": {
                        "type": "integer",
                        "description": "调仓周期（天），默认 5",
                    },
                    "group_number": {
                        "type": "integer",
                        "description": "分组数，默认 5",
                    },
                    "factor_direction": {
                        "type": "integer",
                        "description": "因子方向 1/-1",
                    },
                    "stock_pool": _pool,
                },
                "required": [],
            },
            handler=with_session(_tool_run_factor_analysis),
        ),
        Tool(
            name="list_factors",
            description="列出用户所有因子，附带最近一次分析的 IC_mean / IC_IR / 分组单调性。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_tool_list_factors,
        ),
        Tool(
            name="bind_chat_target",
            description="切换当前对话绑定的画板工件（kind=factor/strategy，id 为对应工件 id）。",
            parameters={
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["factor", "strategy"]},
                    "id": {"type": "string"},
                },
                "required": ["kind", "id"],
            },
            handler=with_session(_tool_bind_chat_target),
        ),
        Tool(
            name="remember",
            description=(
                "把用户的一条长期、稳定偏好或事实保存为跨会话记忆（写入可编辑的系统提示词）。"
                "适合记录投资风格、可接受回撤、资金规模、经验水平；不要记录本次回测区间、"
                "临时参数或中间步骤；已有相同文本不要重复保存。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "kind": {"type": "string", "enum": ["preference", "fact"]},
                },
                "required": ["content"],
            },
            handler=_tool_remember,
        ),
        Tool(
            name="list_skills",
            description="列出技能库中所有已启用的技能（名称、一句话说明、分类、来源仓库）。当用户需求契合某个技能时（如因子挖掘、个股尽调、主力资金画像、特定分析框架），先用它确认可用技能名。",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_tool_list_skills,
        ),
        Tool(
            name="use_skill",
            description=(
                "加载技能库中指定技能，返回该技能的完整操作手册（方法论、步骤、约束）"
                "以及其 GitHub 仓库 README/SKILL.md。随后严格按手册流程执行："
                "先读手册→按步骤调用平台工具取真实数据→完成产出。name 取 list_skills 中的技能名。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名（list_skills 返回的 name，如 qs-stock-dossier）",
                    }
                },
                "required": ["name"],
            },
            handler=_tool_use_skill,
        ),
    ]
