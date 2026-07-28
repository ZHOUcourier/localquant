"""工作流路由"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.models.schemas import WorkflowCreate, WorkflowUpdate
from backend.services import workflow_service

router = APIRouter()


class FromTemplateRequest(BaseModel):
    template_id: str


@router.get("/templates")
async def list_templates():
    return await workflow_service.list_templates()


@router.post("/from-template")
async def create_from_template(body: FromTemplateRequest):
    wf = await workflow_service.create_from_template(body.template_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Template not found")
    return wf


@router.get("/")
async def list_workflows():
    return await workflow_service.list_workflows()


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
    )


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    wf = await workflow_service.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


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
async def run_workflow_stream(workflow_id: str):
    """
    运行工作流（SSE 流式返回进度）

    SSE 事件类型：
    - execution_order: 执行顺序
    - node_start: 节点开始执行
    - node_complete: 节点执行完成
    - node_failed: 节点执行失败
    - workflow_complete: 整体完成
    - workflow_failed: 整体失败
    """
    # 先验证工作流存在
    wf = await workflow_service.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    async def event_generator():
        async for event in workflow_service.run_stream(workflow_id):
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


@router.get("/{workflow_id}/runs")
async def list_workflow_runs(workflow_id: str):
    return await workflow_service.list_runs(workflow_id)
