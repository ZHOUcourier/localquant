"""工作流路由"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.models.schemas import WorkflowCreate, WorkflowUpdate
from backend.services import workflow_service

router = APIRouter()


class FromTemplateRequest(BaseModel):
    template_id: str


class SweepRequest(BaseModel):
    """参数扫描：param_grid = {"<node_uuid>.<param>": [值列表]}"""

    param_grid: dict[str, list]
    note: str = ""


@router.get("/templates")
async def list_templates():
    return await workflow_service.list_templates()


@router.post("/from-template")
async def create_from_template(body: FromTemplateRequest):
    wf = await workflow_service.create_from_template(body.template_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Template not found")
    return wf


@router.post("/import")
async def import_workflow(data: dict[str, Any]):
    """导入工作流：接受 JSON 数据创建新工作流"""
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON 格式错误，需要对象类型")
    wf = await workflow_service.import_workflow(data)
    return wf


@router.get("/")
async def list_workflows(
    tab: str = Query("my", description="Tab filter: preset/my/favorite"),
    search: str = Query("", description="Search by name"),
):
    return await workflow_service.list_workflows(tab=tab, search=search)


@router.post("/")
async def create_or_update_workflow(body: WorkflowCreate):
    # 如果 body.id 存在，则为更新；否则为创建
    if body.id:
        wf = await workflow_service.update_workflow(
            body.id,
            name=body.name,
            description=body.description,
            nodes=[n.model_dump() for n in body.nodes],
            links=[l.model_dump() for l in body.links],
        )
        if not wf:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return wf
    return await workflow_service.create_workflow(
        name=body.name,
        description=body.description,
        nodes=[n.model_dump() for n in body.nodes],
        links=[l.model_dump() for l in body.links],
        is_favorite=body.is_favorite,
    )


@router.get("/runs/{run_id}/nodes/{node_uuid}/output")
async def get_node_output(run_id: str, node_uuid: str):
    """获取单个节点的运行输出预览（表格/曲线/指标/图片）"""
    result = await workflow_service.get_node_output_preview(run_id, node_uuid)
    if result is None:
        raise HTTPException(status_code=404, detail="节点输出不存在，请先运行工作流")
    return result


@router.get("/node-report/{workflow_id}/{node_uuid}")
async def get_node_report(
    workflow_id: str,
    node_uuid: str,
    run_id: str = Query(
        "", description="指定运行 id；缺省取该工作流最近一次含报告的运行"
    ),
):
    """读取因子分析节点的完整综合报告（节点输出 pkl 中的 report 字段）

    供工作流编辑器节点上的「显示分析结果」按钮使用，报告与因子研究页同构。
    """
    import pickle

    from backend.config import settings
    from backend.database import get_db

    candidates: list[str] = [run_id] if run_id else []
    if not candidates:
        # 该工作流最近的运行记录（新 → 旧）
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT id FROM workflow_runs WHERE workflow_id = ? "
                "ORDER BY started_at DESC LIMIT 50",
                (workflow_id,),
            )
            candidates = [row["id"] for row in await cursor.fetchall()]
        finally:
            await db.close()

    for rid in candidates:
        pkl = settings.output_dir / rid / f"{node_uuid}.pkl"
        if not pkl.exists():
            continue
        try:
            with open(pkl, "rb") as f:
                output = pickle.load(f)
        except Exception:
            continue
        report = output.get("report") if isinstance(output, dict) else None
        if report:
            return {"run_id": rid, "report": report}

    raise HTTPException(
        status_code=404,
        detail="未找到该节点的分析报告，请先运行工作流（旧版本产出的运行需重新执行一次）",
    )


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    wf = await workflow_service.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.put("/{workflow_id}/favorite")
async def toggle_favorite(workflow_id: str):
    result = await workflow_service.toggle_favorite(workflow_id)
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return result


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, body: WorkflowUpdate):
    wf = await workflow_service.update_workflow(
        workflow_id,
        name=body.name,
        description=body.description,
        nodes=[n.model_dump() for n in body.nodes] if body.nodes else None,
        links=[l.model_dump() for l in body.links] if body.links else None,
    )
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    ok = await workflow_service.delete_workflow(workflow_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"ok": True}


@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str):
    """运行工作流（同步等待完成，返回全部结果）"""
    result = await workflow_service.run(workflow_id)
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return result


@router.post("/{workflow_id}/run/stream")
async def run_workflow_stream(workflow_id: str, use_cache: bool = Query(True)):
    """
    运行工作流（SSE 流式返回进度）

    SSE 事件类型：
    - execution_order: 执行顺序
    - node_start: 节点开始执行
    - node_complete: 节点执行完成（含 cached 标志）
    - node_failed: 节点执行失败
    - workflow_complete: 整体完成
    - workflow_failed: 整体失败
    use_cache: 默认启用节点缓存；传 false 忽略缓存强制重跑。
    """
    # 先验证工作流存在
    wf = await workflow_service.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    async def event_generator():
        async for event in workflow_service.run_stream(
            workflow_id, use_cache=use_cache
        ):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@router.post("/{workflow_id}/sweep")
async def run_sweep(workflow_id: str, body: SweepRequest):
    """参数扫描（网格搜索）：逐组合执行并写入实验，返回每组指标与 experiment_id"""
    result = await workflow_service.run_sweep(
        workflow_id, body.param_grid, note=body.note
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return result


@router.post("/cache/clear")
async def clear_cache():
    """清空节点级输出缓存"""
    from backend.engine.runner import clear_node_cache

    removed = clear_node_cache()
    return {"ok": True, "removed": removed}


@router.get("/{workflow_id}/runs")
async def list_workflow_runs(workflow_id: str):
    return await workflow_service.list_runs(workflow_id)


@router.post("/runs/{run_id}/cancel")
async def cancel_workflow_run(run_id: str):
    """请求取消正在运行的工作流（在下一个节点边界生效，当前节点会执行完）"""
    from backend.engine.runner import request_cancel

    request_cancel(run_id)
    return {"ok": True, "run_id": run_id}
