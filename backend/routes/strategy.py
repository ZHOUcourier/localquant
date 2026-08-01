"""策略库路由 — 工作中（working）/ 已保存（saved）两态管理

规则（产品约定）：
- QUBE 对话产出的策略、工作流，默认都归类为「工作中」
- 只有用户手动「设为已保存」后才进入「已保存」，AI/系统不得自动提升
- 工作流以虚拟条目（id = wf:{workflow_id}）出现在工作中列表；
  提升为已保存时落为 strategies 表快照行（保留 workflow_id 关联）
"""

import re
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import get_db

router = APIRouter()


class StrategyCreate(BaseModel):
    name: str
    description: str = ""
    content: str = ""
    code: str = ""  # 可回测的 generate_signals 代码；空则从 content 的「实现:」段提取
    source: str = "chat"  # chat / workflow
    workflow_id: str = ""
    session_id: str = ""


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    code: Optional[str] = None  # 更新代码时自动记录一条版本
    version_note: Optional[str] = None  # 本次代码变更的版本备注
    status: Optional[str] = None  # working / saved（仅允许用户操作触发）


def _extract_code(content: str) -> str:
    """从策略正文提取「实现:」段的 python 代码（剥离代码围栏）"""
    m = re.search(r"实现[:：]\s*\n?([\s\S]+)$", content or "")
    if not m:
        return ""
    code = m.group(1).strip()
    fence = re.match(r"^```[a-zA-Z0-9]*\n([\s\S]*?)\n?```", code)
    return (fence.group(1) if fence else code).strip()


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "status": row["status"],
        "source": row["source"],
        "content": row["content"],
        "code": row["code"] if "code" in row.keys() else "",
        "workflow_id": row["workflow_id"],
        "session_id": row["session_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


async def _add_version(
    db, strategy_id: str, code: str, content: str, note: str
) -> None:
    await db.execute(
        "INSERT INTO strategy_versions (strategy_id, code, content, note, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (strategy_id, code, content, note, int(time.time())),
    )


@router.get("/")
async def list_strategies(
    status: str = Query("working", description="working / saved"),
):
    """列出策略：working 额外合并未提升为已保存的工作流（虚拟条目 wf:{id}）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM strategies WHERE status = ? ORDER BY updated_at DESC",
            (status,),
        )
        items = [_row_to_dict(r) for r in await cursor.fetchall()]

        if status == "working":
            # 已经以任意状态入库的工作流不再重复出现在虚拟条目里
            cursor = await db.execute(
                "SELECT workflow_id FROM strategies WHERE workflow_id != ''"
            )
            promoted = {r["workflow_id"] for r in await cursor.fetchall()}
            cursor = await db.execute(
                "SELECT id, name, description, updated_at, created_at FROM workflows "
                "ORDER BY updated_at DESC"
            )
            for wf in await cursor.fetchall():
                if wf["id"] in promoted:
                    continue
                items.append(
                    {
                        "id": f"wf:{wf['id']}",
                        "name": wf["name"],
                        "description": wf["description"] or "",
                        "status": "working",
                        "source": "workflow",
                        "content": "",
                        "code": "",
                        "workflow_id": wf["id"],
                        "session_id": "",
                        "created_at": wf["created_at"],
                        "updated_at": wf["updated_at"],
                    }
                )
            items.sort(key=lambda x: x["updated_at"] or 0, reverse=True)
        return {"strategies": items}
    finally:
        await db.close()


@router.post("/")
async def create_strategy(body: StrategyCreate):
    """新建策略（默认工作中；QUBE 对话保存策略走这里），同时记录初始版本"""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="策略名称不能为空")
    now = int(time.time())
    sid = str(uuid.uuid4())
    code = body.code or _extract_code(body.content)
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO strategies (id, name, description, status, source, content, "
            "code, workflow_id, session_id, created_at, updated_at) "
            "VALUES (?, ?, ?, 'working', ?, ?, ?, ?, ?, ?, ?)",
            (
                sid,
                body.name.strip(),
                body.description,
                body.source,
                body.content,
                code,
                body.workflow_id,
                body.session_id,
                now,
                now,
            ),
        )
        await _add_version(db, sid, code, body.content, "初始版本")
        await db.commit()
    finally:
        await db.close()
    return {"id": sid, "status": "working"}


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str):
    """策略详情（含可回测代码）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="策略不存在")
        return _row_to_dict(row)
    finally:
        await db.close()


@router.get("/{strategy_id}/versions")
async def list_versions(strategy_id: str):
    """策略版本历史（新 → 旧）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, note, code, created_at FROM strategy_versions "
            "WHERE strategy_id = ? ORDER BY id DESC",
            (strategy_id,),
        )
        return {
            "versions": [
                {
                    "id": r["id"],
                    "note": r["note"],
                    "code": r["code"],
                    "created_at": r["created_at"],
                }
                for r in await cursor.fetchall()
            ]
        }
    finally:
        await db.close()


@router.post("/{strategy_id}/versions/{version_id}/rollback")
async def rollback_version(strategy_id: str, version_id: int):
    """回滚到指定版本的代码（产生一条新版本记录）"""
    now = int(time.time())
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT code, content FROM strategy_versions WHERE id = ? AND strategy_id = ?",
            (version_id, strategy_id),
        )
        ver = await cursor.fetchone()
        if not ver:
            raise HTTPException(status_code=404, detail="版本不存在")
        await db.execute(
            "UPDATE strategies SET code = ?, updated_at = ? WHERE id = ?",
            (ver["code"], now, strategy_id),
        )
        await _add_version(
            db, strategy_id, ver["code"], ver["content"], f"回滚自版本 #{version_id}"
        )
        await db.commit()
    finally:
        await db.close()
    return {"ok": True, "code": ver["code"]}


class OptimizeRequest(BaseModel):
    code: str  # 当前编辑器中的代码（可能未保存）
    content: str = ""  # 策略说明（可选，给 AI 背景）
    metrics: dict = {}  # 最近一次回测指标（可选）
    instruction: str = ""  # 用户额外要求（可选）


OPTIMIZE_SYSTEM = """你是量化策略优化师。用户给出当前策略的 generate_signals 代码、
（可选的）策略说明与最近回测指标。请针对性改进策略（信号逻辑/参数/风控），目标是
提升风险调整后收益（夏普/回撤）而非过拟合。
输出要求：
1. 先用 1-3 句话说明改了什么、为什么（不要长篇大论）
2. 然后给出完整新代码，包在 ```python 代码块中；必须保留
   generate_signals(prices, **kwargs) 函数签名，prices 为收盘价面板 DataFrame"""


@router.post("/{strategy_id}/optimize")
async def optimize_strategy(strategy_id: str, body: OptimizeRequest):
    """AI 优化策略代码（用 QUBE 引擎）：返回新代码 + 说明，由用户确认后保存"""
    if not body.code.strip():
        raise HTTPException(status_code=400, detail="当前策略代码为空，无法优化")
    metrics_text = "\n".join(f"- {k}: {v}" for k, v in (body.metrics or {}).items())
    user = (
        (f"## 策略说明\n{body.content}\n\n" if body.content.strip() else "")
        + f"## 当前代码\n```python\n{body.code}\n```\n\n"
        + (f"## 最近回测指标\n{metrics_text}\n\n" if metrics_text else "")
        + (
            f"## 额外要求\n{body.instruction}"
            if body.instruction.strip()
            else "请优化该策略。"
        )
    )
    from backend.routes.qube import qube_complete

    text = await qube_complete(OPTIMIZE_SYSTEM, user)
    fence = re.search(r"```(?:python)?\n([\s\S]*?)\n?```", text)
    new_code = fence.group(1).strip() if fence else ""
    note = re.sub(r"```[\s\S]*?```", "", text).strip()[:500]
    if not new_code:
        raise HTTPException(status_code=502, detail=f"AI 未返回代码块: {text[:200]}")
    return {"code": new_code, "note": note or "AI 优化"}


# ── QMT 转写（导出方向：本平台 generate_signals → 迅投 QMT 实盘代码）──


EXPORT_QMT_SYSTEM = """你是量化策略转写专家，把 LocalQuant 平台的策略转写为
迅投 QMT（国金/国盛等券商 miniQMT，xtquant 库）可用的实盘/模拟盘策略代码。

源格式：generate_signals(prices, **kwargs)，prices 为日线收盘价面板
(index=交易日, columns=股票代码)，返回同形状持仓权重/信号 DataFrame。

目标格式：QMT 策略文件（python），结构要求：
- init(ContextInfo)：设股票池（ContextInfo.set_universe）、参数初始化
- handlebar(ContextInfo)：每根 K 线触发；用 ContextInfo.get_market_data_ex 取行情，
  复现原策略的信号逻辑，用 passorder 下单（注释标注买卖参数含义）
- 日线级别调仓；资金分配按目标权重折算股数（100 股整倍）
- 代码可直接粘进 QMT 编辑器运行，不依赖 QMT 之外的三方库（pandas/numpy 除外）

硬性要求：
1. 先用不超过 5 行说明转写思路；若两边能力差异导致无法等价实现（如截面排名
   需全市场数据、停牌处理、T+1 约束），明确列出：哪里不行、为什么、怎么降级。
2. 然后给出完整 QMT 代码，包在 ```python 代码块中，关键逻辑逐段中文注释。
3. 风控/参数保留原策略语义；不确定处用保守默认并注释说明。"""


@router.post("/{strategy_id}/export-qmt")
async def export_qmt(strategy_id: str):
    """策略转写为迅投 QMT 实盘代码（AI 转写，返回代码 + 说明/降级清单）"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT name, description, content, code FROM strategies WHERE id = ?",
            (strategy_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    if not row:
        raise HTTPException(status_code=404, detail="策略不存在")
    if not (row["code"] or "").strip():
        raise HTTPException(status_code=400, detail="策略无可转写代码")
    user = (
        f"## 策略名称\n{row['name']}\n\n"
        + (
            f"## 策略说明\n{row['description'] or row['content']}\n\n"
            if (row["description"] or row["content"])
            else ""
        )
        + f"## 平台策略代码\n```python\n{row['code']}\n```\n\n请转写为 QMT 策略。"
    )
    from backend.routes.qube import qube_complete

    text = await qube_complete(EXPORT_QMT_SYSTEM, user)
    fence = re.search(r"```(?:python)?\n([\s\S]*?)\n?```", text)
    qmt_code = fence.group(1).strip() if fence else ""
    note = re.sub(r"```[\s\S]*?```", "", text).strip()[:2000]
    if not qmt_code:
        raise HTTPException(status_code=502, detail=f"AI 未返回代码块: {text[:200]}")
    return {"code": qmt_code, "note": note, "filename": f"{row['name']}_qmt.py"}


@router.put("/{strategy_id}")
async def update_strategy(strategy_id: str, body: StrategyUpdate):
    """更新策略；status=saved 即用户手动「设为已保存」

    虚拟工作流条目（wf:{id}）提升时自动落为快照行。
    """
    if body.status is not None and body.status not in ("working", "saved"):
        raise HTTPException(status_code=400, detail="status 仅支持 working / saved")

    now = int(time.time())
    db = await get_db()
    try:
        # 工作流虚拟条目 → 建快照行
        if strategy_id.startswith("wf:"):
            wf_id = strategy_id[3:]
            cursor = await db.execute(
                "SELECT id, name, description, nodes_json, links_json FROM workflows WHERE id = ?",
                (wf_id,),
            )
            wf = await cursor.fetchone()
            if not wf:
                raise HTTPException(status_code=404, detail="工作流不存在")
            sid = str(uuid.uuid4())
            import json as _json

            content = _json.dumps(
                {
                    "nodes": _json.loads(wf["nodes_json"]),
                    "links": _json.loads(wf["links_json"]),
                },
                ensure_ascii=False,
            )
            await db.execute(
                "INSERT INTO strategies (id, name, description, status, source, content, "
                "workflow_id, session_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'workflow', ?, ?, '', ?, ?)",
                (
                    sid,
                    body.name or wf["name"],
                    body.description
                    if body.description is not None
                    else (wf["description"] or ""),
                    body.status or "working",
                    content,
                    wf_id,
                    now,
                    now,
                ),
            )
            await db.commit()
            return {"id": sid, "status": body.status or "working"}

        cursor = await db.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="策略不存在")

        fields, values = [], []
        for col, val in (
            ("name", body.name),
            ("description", body.description),
            ("content", body.content),
            ("code", body.code),
            ("status", body.status),
        ):
            if val is not None:
                fields.append(f"{col} = ?")
                values.append(val)
        if fields:
            fields.append("updated_at = ?")
            values.append(now)
            values.append(strategy_id)
            await db.execute(
                f"UPDATE strategies SET {', '.join(fields)} WHERE id = ?", values
            )
            # 代码变更 → 自动记录版本
            if body.code is not None and body.code != row["code"]:
                await _add_version(
                    db,
                    strategy_id,
                    body.code,
                    body.content if body.content is not None else row["content"],
                    body.version_note or "手动保存",
                )
            await db.commit()
        return {"id": strategy_id, "status": body.status or row["status"]}
    finally:
        await db.close()


@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: str):
    """删除策略行（虚拟工作流条目请到工作流页删除）"""
    if strategy_id.startswith("wf:"):
        raise HTTPException(status_code=400, detail="工作流条目请在「工作流」页面删除")
    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="策略不存在")
    finally:
        await db.close()
    return {"ok": True}
